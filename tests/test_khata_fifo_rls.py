"""
tests/test_khata_fifo_rls.py
Comprehensive test suite for Laptop 2 (Developer B):
1. Agent 4: Concurrency-Safe FIFO Inventory Depletion (Oldest-batch-first)
2. Stock Shortfall Graceful Handling (Zero Negative Stock Guarantee)
3. Customer Khata Credit (Udhaar Diya) & Repayment (Udhaar Chukaya) Math
4. End-to-End Counter Sale Atomic Inflow (Cash/UPI + Udhaar + FIFO Depletion)
5. PostgreSQL Multi-Tenant Row-Level Security (RLS) Isolation
"""
import uuid
from datetime import date, datetime, timedelta
import pytest
from sqlalchemy import select, text

from app.core.contracts import CounterItemSale, CounterSaleEvent, PaymentMethod
from app.db.fifo_engine import (
    deplete_inventory_fifo,
    get_stock_availability,
    restock_inventory_batch,
)
from app.db.khata_models import CashTransaction, CustomerKhata, InventoryBatch, KhataEntry
from app.db.khata_repository import (
    get_customer_khata,
    list_merchant_khatas,
    record_counter_sale,
    record_khata_entry,
)
from app.db.models import Merchant
from app.db.session import get_admin_session, get_rls_session


@pytest.fixture(scope="module")
def setup_test_merchants():
    """
    Creates two distinct merchants in Supabase for isolated multi-tenant tests.
    """
    m1_id = f"M_L2_A_{uuid.uuid4().hex[:6]}"
    m2_id = f"M_L2_B_{uuid.uuid4().hex[:6]}"

    with get_admin_session() as session:
        m1 = Merchant(id=m1_id, name="Kirana Test Store A", phone=f"91{uuid.uuid4().int % 10000000000}")
        m2 = Merchant(id=m2_id, name="Kirana Test Store B", phone=f"91{uuid.uuid4().int % 10000000000}")
        session.add_all([m1, m2])

    yield m1_id, m2_id

    # Cleanup test merchants & cascades
    with get_admin_session() as session:
        session.execute(text("DELETE FROM cash_transactions WHERE merchant_id IN (:m1, :m2)"), {"m1": m1_id, "m2": m2_id})
        session.execute(text("DELETE FROM khata_entries WHERE merchant_id IN (:m1, :m2)"), {"m1": m1_id, "m2": m2_id})
        session.execute(text("DELETE FROM customer_khata WHERE merchant_id IN (:m1, :m2)"), {"m1": m1_id, "m2": m2_id})
        session.execute(text("DELETE FROM inventory_batches WHERE merchant_id IN (:m1, :m2)"), {"m1": m1_id, "m2": m2_id})
        session.execute(text("DELETE FROM merchants WHERE id IN (:m1, :m2)"), {"m1": m1_id, "m2": m2_id})


def test_fifo_multi_batch_depletion(setup_test_merchants):
    """
    Verifies Agent 4 FIFO:
    - Depletes oldest expiry batch first.
    - If oldest batch doesn't cover required quantity, rolls over to next batch.
    """
    m1_id, _ = setup_test_merchants
    item_name = f"Fortune Sunflower Oil 1L - {uuid.uuid4().hex[:4]}"

    with get_rls_session(m1_id) as session:
        # Batch 1: 5 units, expires in 10 days, cost ₹140
        b1 = restock_inventory_batch(
            session=session,
            merchant_id=m1_id,
            item_name=item_name,
            quantity=5.0,
            cost_price=140.0,
            batch_number="BATCH-EARLY-01",
            expiry_date=date.today() + timedelta(days=10)
        )
        # Batch 2: 10 units, expires in 30 days, cost ₹147
        b2 = restock_inventory_batch(
            session=session,
            merchant_id=m1_id,
            item_name=item_name,
            quantity=10.0,
            cost_price=147.0,
            batch_number="BATCH-LATE-02",
            expiry_date=date.today() + timedelta(days=30)
        )

    # Now deplete 8 units: should deplete ALL 5 of b1, and 3 of b2.
    with get_rls_session(m1_id) as session:
        report = deplete_inventory_fifo(
            session=session,
            merchant_id=m1_id,
            item_name=item_name,
            quantity_to_deplete=8.0
        )

        assert report["total_depleted"] == 8.0
        assert report["shortfall"] == 0.0
        assert report["is_fully_fulfilled"] is True
        assert len(report["batches_depleted"]) == 2

        # First batch depleted to 0
        assert report["batches_depleted"][0]["batch_number"] == "BATCH-EARLY-01"
        assert report["batches_depleted"][0]["units_taken"] == 5.0
        assert report["batches_depleted"][0]["remaining_in_batch"] == 0.0

        # Second batch depleted by 3, leaving 7
        assert report["batches_depleted"][1]["batch_number"] == "BATCH-LATE-02"
        assert report["batches_depleted"][1]["units_taken"] == 3.0
        assert report["batches_depleted"][1]["remaining_in_batch"] == 7.0

    # Verify stock availability matches
    with get_rls_session(m1_id) as session:
        stock = get_stock_availability(session, m1_id, item_name)
        assert stock["total_available_units"] == 7.0
        assert stock["batch_count"] == 1


def test_fifo_zero_negative_stock_on_deficit(setup_test_merchants):
    """
    Verifies that when a merchant attempts to sell more stock than exists:
    - Depletes all available stock to 0.0.
    - Accurately reports shortfall.
    - NEVER sets inventory_batches.quantity_remaining to negative numbers.
    """
    m1_id, _ = setup_test_merchants
    item_name = f"Parle-G Biscuit 50g - {uuid.uuid4().hex[:4]}"

    with get_rls_session(m1_id) as session:
        restock_inventory_batch(
            session=session,
            merchant_id=m1_id,
            item_name=item_name,
            quantity=4.0,
            cost_price=5.0
        )

    with get_rls_session(m1_id) as session:
        # Request 10 units when only 4 exist
        report = deplete_inventory_fifo(
            session=session,
            merchant_id=m1_id,
            item_name=item_name,
            quantity_to_deplete=10.0
        )

        assert report["total_depleted"] == 4.0
        assert report["shortfall"] == 6.0
        assert report["is_fully_fulfilled"] is False
        assert report["batches_depleted"][0]["remaining_in_batch"] == 0.0

    # Ensure DB value is exactly 0.0, never negative
    with get_rls_session(m1_id) as session:
        stock = get_stock_availability(session, m1_id, item_name)
        assert stock["total_available_units"] == 0.0


def test_customer_khata_credit_and_repayment_math(setup_test_merchants):
    """
    Verifies Customer Khata arithmetic:
    1. GIVE_CREDIT: increases receivable balance.
    2. COLLECT_PAYMENT: decreases balance and logs CashTransaction inflow.
    """
    m1_id, _ = setup_test_merchants
    cust_name = f"Sharma Ji - {uuid.uuid4().hex[:4]}"

    with get_rls_session(m1_id) as session:
        # 1. Extend ₹500 credit
        k1 = record_khata_entry(
            session=session,
            merchant_id=m1_id,
            customer_name=cust_name,
            amount=500.0,
            action="GIVE_CREDIT",
            phone="9876543210",
            notes="Morning groceries credit"
        )
        assert k1.current_balance == 500.0
        assert k1.total_credit_given == 500.0
        assert k1.total_repaid == 0.0

    with get_rls_session(m1_id) as session:
        # 2. Sharma ji pays back ₹200 on Paytm
        k2 = record_khata_entry(
            session=session,
            merchant_id=m1_id,
            customer_name=cust_name,
            amount=200.0,
            action="COLLECT_PAYMENT",
            notes="Paid via Paytm QR"
        )
        assert k2.current_balance == 300.0
        assert k2.total_credit_given == 500.0
        assert k2.total_repaid == 200.0

        # Verify settled cash transaction logged
        cash_txns = session.execute(
            select(CashTransaction).where(
                CashTransaction.merchant_id == m1_id,
                CashTransaction.amount == 200.0
            )
        ).scalars().all()
        assert len(cash_txns) >= 1
        assert cash_txns[-1].payment_method == "PAYTM_UPI"


def test_atomic_counter_sale_inflow(setup_test_merchants):
    """
    Verifies the complete end-to-end atomic counter sale:
    - Settled Paytm payment (+₹300)
    - Udhaar credit extended (+₹150 to Suresh)
    - Stock depleted for items sold
    """
    m1_id, _ = setup_test_merchants
    item_name = f"Tata Salt 1kg - {uuid.uuid4().hex[:4]}"
    cust_name = f"Suresh Gupta - {uuid.uuid4().hex[:4]}"

    with get_rls_session(m1_id) as session:
        # Seed 10 packets of salt
        restock_inventory_batch(
            session=session,
            merchant_id=m1_id,
            item_name=item_name,
            quantity=10.0,
            cost_price=22.0
        )

    # Ingest counter sale
    sale_event = CounterSaleEvent(
        merchant_id=m1_id,
        amount_paid=300.0,
        payment_method=PaymentMethod.PAYTM_UPI,
        payment_reference="UPI_TXN_987654321",
        credit_amount=150.0,
        customer_name=cust_name,
        customer_phone="9988776655",
        items=[
            CounterItemSale(
                item_name=item_name,
                quantity=3.0,
                unit_retail_price=28.0,
                line_total=84.0
            )
        ]
    )

    with get_rls_session(m1_id) as session:
        result = record_counter_sale(session, m1_id, sale_event)

        assert result["status"] == "RECORDED"
        assert result["amount_settled"] == 300.0
        assert result["credit_amount"] == 150.0
        assert result["customer_current_balance"] == 150.0
        assert len(result["inventory_depletions"]) == 1
        assert result["inventory_depletions"][0]["total_depleted"] == 3.0

    # Verify inventory in DB decremented from 10 to 7
    with get_rls_session(m1_id) as session:
        stock = get_stock_availability(session, m1_id, item_name)
        assert stock["total_available_units"] == 7.0


def test_multi_tenant_rls_isolation(setup_test_merchants):
    """
    CRITICAL SECURITY TEST:
    Verifies that under PostgreSQL Row-Level Security:
    - Merchant B CANNOT view or deplete Merchant A's inventory batches.
    - Merchant B CANNOT view Merchant A's customer Khata records.
    """
    m1_id, m2_id = setup_test_merchants
    private_item = f"Secret Atta 10kg - {uuid.uuid4().hex[:4]}"
    private_customer = f"Confidential Customer - {uuid.uuid4().hex[:4]}"

    # Seed private records strictly under Merchant A
    with get_rls_session(m1_id) as session:
        restock_inventory_batch(
            session=session,
            merchant_id=m1_id,
            item_name=private_item,
            quantity=20.0,
            cost_price=350.0
        )
        record_khata_entry(
            session=session,
            merchant_id=m1_id,
            customer_name=private_customer,
            amount=1500.0,
            action="GIVE_CREDIT"
        )

    # Switch session context to Merchant B: verify complete invisibility
    with get_rls_session(m2_id) as session:
        # 1. Merchant B queries inventory: should see 0
        stock_m2 = get_stock_availability(session, m2_id, private_item)
        assert stock_m2["total_available_units"] == 0.0

        # 2. Merchant B attempts to deplete Merchant A's SKU: should deplete 0
        depletion_m2 = deplete_inventory_fifo(
            session=session,
            merchant_id=m2_id,
            item_name=private_item,
            quantity_to_deplete=5.0
        )
        assert depletion_m2["total_depleted"] == 0.0
        assert depletion_m2["shortfall"] == 5.0

        # 3. Merchant B queries Merchant A's Khata customer: should return None
        khata_m2 = get_customer_khata(session, m2_id, private_customer)
        assert khata_m2 is None

    # Switch back to Merchant A: verify data remains pristine & untouched
    with get_rls_session(m1_id) as session:
        stock_m1 = get_stock_availability(session, m1_id, private_item)
        assert stock_m1["total_available_units"] == 20.0

        khata_m1 = get_customer_khata(session, m1_id, private_customer)
        assert khata_m1 is not None
        assert khata_m1.current_balance == 1500.0
