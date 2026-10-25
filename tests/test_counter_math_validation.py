"""
tests/test_counter_math_validation.py
Mathematical Validation & Verification Suite for Sahayak Counter Sales & FIFO Stock Math:

Validates:
1. Pricing Arithmetic: Total Amount / Qty = Unit Rate, Qty * Unit Rate = Line Total.
2. Cross-Batch FIFO Math: Depleting across multiple batches preserves the inventory invariant:
   Total Initial Stock = Total Depleted + Total Remaining Stock.
3. Stock Deficit Arithmetic: Shortfall = Requested - Available; DB stock clamped at 0.0 (Zero negative stock).
4. Text Shorthand Regex Parser: Verifies rate extraction for colloquial retail inputs.
5. Structured Output Verification: Ensures receipt contains items, unit rate, depleted qty, and remaining shelf stock.
6. Multi-Tenant Isolation & Inflow Double-Entry: Cash transactions match settled amounts.
"""
import uuid
from datetime import date, datetime, timedelta
import pytest
from sqlalchemy import text

from app.core.contracts import CounterItemSale, CounterSaleEvent, PaymentMethod
from app.db.fifo_engine import deplete_inventory_fifo, get_stock_availability, restock_inventory_batch
from app.db.khata_models import CashTransaction, InventoryBatch
from app.db.khata_repository import record_counter_sale
from app.db.models import Merchant
from app.db.session import get_admin_session, get_rls_session
from app.main import format_counter_sale_receipt
from app.workers.voice_khata import voice_khata_parser


@pytest.fixture(scope="module")
def setup_math_merchant():
    """Sets up an isolated test merchant in PostgreSQL."""
    m_id = f"M_MATH_{uuid.uuid4().hex[:6]}"
    with get_admin_session() as session:
        m = Merchant(id=m_id, name="Math Validation Store", phone=f"91{uuid.uuid4().int % 10000000000:010d}")
        session.add(m)

    yield m_id

    # Teardown
    with get_admin_session() as session:
        session.execute(text("DELETE FROM cash_transactions WHERE merchant_id = :m_id"), {"m_id": m_id})
        session.execute(text("DELETE FROM inventory_batches WHERE merchant_id = :m_id"), {"m_id": m_id})
        session.execute(text("DELETE FROM merchants WHERE id = :m_id"), {"m_id": m_id})


# ============================================================================
# 1. PRICING & RATE DERIVATION ARITHMETIC TESTS
# ============================================================================
def test_pricing_math_derivation():
    """
    Validates the fundamental retail equation:
    Unit Retail Price = Total Inflow / Quantity
    Line Total = Quantity * Unit Retail Price == Total Inflow
    """
    test_cases = [
        # (text, expected_total, expected_qty, expected_unit_price, expected_unit)
        ("12000 ruppes Aashirvad atta 10 bags", 12000.0, 10.0, 1200.0, "bags"),
        ("12000 ruppes Aashirvad atta 20 bags", 12000.0, 20.0, 600.0, "bags"),
        ("12000 ruppes ashirwad atta 8 bags", 12000.0, 8.0, 1500.0, "bags"),
        ("paytm 300 oil 2", 300.0, 2.0, 150.0, "units"),
        ("150 rs sugar 3 kg", 150.0, 3.0, 50.0, "kg"),
        ("Cash 750 Rice 5 bags", 750.0, 5.0, 150.0, "bags"),
    ]

    for raw_text, exp_tot, exp_qty, exp_rate, exp_unit in test_cases:
        event = voice_khata_parser.parse_counter_sale(raw_text, merchant_id="M_TEST")
        assert event is not None, f"Failed to parse text: {raw_text}"
        assert event.amount_paid == exp_tot, f"Total mismatch for {raw_text}"
        assert len(event.items) == 1

        item = event.items[0]
        assert item.quantity == exp_qty, f"Quantity mismatch for {raw_text}"
        assert item.unit_retail_price == exp_rate, f"Unit price mismatch for {raw_text}"
        assert item.line_total == exp_tot, f"Line total mismatch for {raw_text}"
        assert item.unit == exp_unit, f"Unit mismatch for {raw_text}"

        # Mathematical Invariant check
        assert round(item.quantity * item.unit_retail_price, 2) == round(item.line_total, 2)


# ============================================================================
# 2. FIFO CROSS-BATCH INVENTORY MATHEMATICS
# ============================================================================
def test_fifo_cross_batch_math_rollover(setup_math_merchant):
    """
    Simulates the exact scenario from the Telegram interaction:
    Initial Stock:
      - Batch 1 (created earliest): 10 bags @ ₹1,100
      - Batch 2: 12 bags @ ₹1,200
      - Batch 3: 10 bags @ ₹1,200
      Total Initial Stock = 10 + 12 + 10 = 32 bags.

    Customer Buys: 20 bags.
    Expected:
      - Batch 1: 10 bags fully depleted (10 - 10 = 0 remaining)
      - Batch 2: 10 bags depleted (12 - 10 = 2 remaining)
      - Batch 3: 0 bags depleted (10 remaining)
      - Total Depleted = 10 + 10 = 20 bags.
      - Total Remaining Stock = 0 + 2 + 10 = 12 bags!
      - Invariant: Initial (32) = Depleted (20) + Remaining (12).
    """
    m_id = setup_math_merchant
    sku = f"Aashirvaad Atta 10kg - {uuid.uuid4().hex[:4]}"

    with get_rls_session(m_id) as session:
        # Seed 3 distinct batches
        b1 = restock_inventory_batch(
            session=session,
            merchant_id=m_id,
            item_name=sku,
            quantity=10.0,
            cost_price=1100.0,
            batch_number="BATCH-OCT-01",
            expiry_date=date.today() + timedelta(days=60),
            unit="bags"
        )
        b2 = restock_inventory_batch(
            session=session,
            merchant_id=m_id,
            item_name=sku,
            quantity=12.0,
            cost_price=1200.0,
            batch_number="BATCH-OCT-02",
            expiry_date=date.today() + timedelta(days=90),
            unit="bags"
        )
        b3 = restock_inventory_batch(
            session=session,
            merchant_id=m_id,
            item_name=sku,
            quantity=10.0,
            cost_price=1200.0,
            batch_number="BATCH-OCT-03",
            expiry_date=date.today() + timedelta(days=120),
            unit="bags"
        )

    # Initial Availability Check
    with get_rls_session(m_id) as session:
        initial_stock = get_stock_availability(session, m_id, sku)
        assert initial_stock["total_available_units"] == 32.0
        assert initial_stock["batch_count"] == 3

    # Deplete 20 bags via FIFO
    with get_rls_session(m_id) as session:
        res = deplete_inventory_fifo(
            session=session,
            merchant_id=m_id,
            item_name=sku,
            quantity_to_deplete=20.0
        )

        assert res["requested_units"] == 20.0
        assert res["total_depleted"] == 20.0
        assert res["shortfall"] == 0.0
        assert res["is_fully_fulfilled"] is True
        assert res["total_remaining"] == 12.0

        # Detailed batch-by-batch audit checks
        batches_hit = res["batches_depleted"]
        assert len(batches_hit) == 2

        # Batch 1: fully depleted
        assert batches_hit[0]["batch_number"] == "BATCH-OCT-01"
        assert batches_hit[0]["units_taken"] == 10.0
        assert batches_hit[0]["remaining_in_batch"] == 0.0

        # Batch 2: partially depleted
        assert batches_hit[1]["batch_number"] == "BATCH-OCT-02"
        assert batches_hit[1]["units_taken"] == 10.0
        assert batches_hit[1]["remaining_in_batch"] == 2.0

    # Invariant verification in DB
    with get_rls_session(m_id) as session:
        post_stock = get_stock_availability(session, m_id, sku)
        # Total remaining = Batch 2 (2) + Batch 3 (10) = 12.0
        assert post_stock["total_available_units"] == 12.0
        assert post_stock["batch_count"] == 2  # Batch 1 is 0, so 2 active batches remain


# ============================================================================
# 3. STOCK DEFICIT & SHORTFALL ARITHMETIC
# ============================================================================
def test_fifo_deficit_math_zero_negative_stock(setup_math_merchant):
    """
    Validates arithmetic when sale quantity exceeds on-shelf stock:
    Available: 5 bags
    Requested: 8 bags
    Expected:
      - Depleted: 5.0 bags
      - Shortfall: 3.0 bags (8.0 - 5.0)
      - Remaining: 0.0 bags
      - Database column is clamped at 0.0 (Zero Negative Stock Guarantee)
    """
    m_id = setup_math_merchant
    sku = f"Madhur Sugar 5kg - {uuid.uuid4().hex[:4]}"

    with get_rls_session(m_id) as session:
        restock_inventory_batch(
            session=session,
            merchant_id=m_id,
            item_name=sku,
            quantity=5.0,
            cost_price=240.0,
            unit="bags"
        )

    with get_rls_session(m_id) as session:
        res = deplete_inventory_fifo(
            session=session,
            merchant_id=m_id,
            item_name=sku,
            quantity_to_deplete=8.0
        )

        assert res["requested_units"] == 8.0
        assert res["total_depleted"] == 5.0
        assert res["shortfall"] == 3.0
        assert res["is_fully_fulfilled"] is False
        assert res["total_remaining"] == 0.0

    # Confirm DB is exactly 0.0
    with get_rls_session(m_id) as session:
        stock = get_stock_availability(session, m_id, sku)
        assert stock["total_available_units"] == 0.0


# ============================================================================
# 4. STRUCTURED RECEIPT FORMATTING VALIDATION
# ============================================================================
def test_structured_receipt_format_validation():
    """
    Ensures format_counter_sale_receipt outputs a structured receipt
    containing:
      - Settled Inflow & Payment method
      - Line item with rate and line total
      - Depleted units and remaining shelf stock
      - ACID Supabase PostgreSQL confirmation
    """
    event = CounterSaleEvent(
        merchant_id="M_TEST_STORE",
        amount_paid=12000.0,
        payment_method=PaymentMethod.CASH,
        items=[
            CounterItemSale(
                item_name="Aashirvad atta",
                quantity=20.0,
                unit="bags",
                unit_retail_price=600.0,
                line_total=12000.0
            )
        ]
    )

    mock_res = {
        "status": "RECORDED",
        "inventory_depletions": [
            {
                "item_name": "Aashirvad atta",
                "matched_sku": "Aashirvaad Chakki Atta 10kg",
                "unit": "bags",
                "total_depleted": 20.0,
                "total_remaining": 12.0,
                "shortfall": 0.0,
                "is_fully_fulfilled": True
            }
        ]
    }

    receipt = format_counter_sale_receipt(event, mock_res)

    # Validate all structured elements exist
    assert "Counter Sale Recorded" in receipt
    assert "₹12,000.00" in receipt
    assert "(CASH)" in receipt
    assert "Aashirvad atta" in receipt
    assert "`20.0 bags` @ ₹600.00/bags" in receipt
    assert "Depleted:* `20.0 bags`" in receipt
    assert "Remaining Shelf Stock:* *`12.0 bags`*" in receipt
    assert "ACID Committed to Supabase PostgreSQL" in receipt


# ============================================================================
# 5. END-TO-END ATOMIC COUNTER SALE WITH DOUBLE-ENTRY INFLOW
# ============================================================================
def test_end_to_end_atomic_counter_sale_math(setup_math_merchant):
    """
    Executes a real counter sale through record_counter_sale:
    - Verifies CashTransaction is created with matching inflow.
    - Verifies FIFO batch depletion deductions match.
    - Verifies remaining stock in DB.
    """
    m_id = setup_math_merchant
    sku = f"Sunflower Oil 1L - {uuid.uuid4().hex[:4]}"

    # Seed 25 units on shelf
    with get_rls_session(m_id) as session:
        restock_inventory_batch(
            session=session,
            merchant_id=m_id,
            item_name=sku,
            quantity=25.0,
            cost_price=175.0,
            unit="units"
        )

    # Record sale: 5 units for ₹1,000 via Paytm UPI
    sale = CounterSaleEvent(
        merchant_id=m_id,
        amount_paid=1000.0,
        payment_method=PaymentMethod.PAYTM_UPI,
        items=[
            CounterItemSale(
                item_name=sku,
                quantity=5.0,
                unit="units",
                unit_retail_price=200.0,
                line_total=1000.0
            )
        ]
    )

    with get_rls_session(m_id) as session:
        sale_res = record_counter_sale(session, m_id, sale)

        assert sale_res["status"] == "RECORDED"
        assert sale_res["amount_settled"] == 1000.0
        assert len(sale_res["inventory_depletions"]) == 1

        dep = sale_res["inventory_depletions"][0]
        assert dep["total_depleted"] == 5.0
        assert dep["total_remaining"] == 20.0

    # Validate Cash Inflow recorded in PostgreSQL
    with get_rls_session(m_id) as session:
        from sqlalchemy import select
        txn = session.execute(
            select(CashTransaction).where(
                CashTransaction.merchant_id == m_id,
                CashTransaction.amount == 1000.0
            )
        ).scalars().first()
        assert txn is not None
        assert txn.payment_method == "PAYTM_UPI"

        # Validate remaining stock on shelf
        stock = get_stock_availability(session, m_id, sku)
        assert stock["total_available_units"] == 20.0


# ============================================================================
# 6. HEADING OUT OF STOCK & OUT OF STOCK WARNING TESTS
# ============================================================================
def test_heading_out_of_stock_warning_receipt():
    """
    Validates that the receipt dynamically emits:
    - 'Heading Out of Stock' alert when remaining stock <= 5 units
    - 'OUT OF STOCK' alert when remaining stock == 0 units
    """
    event = CounterSaleEvent(
        merchant_id="M_TEST_STORE",
        amount_paid=1200.0,
        payment_method=PaymentMethod.CASH,
        items=[
            CounterItemSale(
                item_name="Aashirvaad Atta",
                quantity=1.0,
                unit="bags",
                unit_retail_price=1200.0,
                line_total=1200.0
            )
        ]
    )

    # Case A: Low Stock (<= 5 units remaining)
    res_low = {
        "status": "RECORDED",
        "inventory_depletions": [
            {
                "item_name": "Aashirvaad Atta",
                "matched_sku": "Aashirvaad Atta 10kg",
                "unit": "bags",
                "total_depleted": 1.0,
                "total_remaining": 3.0,
                "shortfall": 0.0,
                "is_fully_fulfilled": True
            }
        ]
    }
    receipt_low = format_counter_sale_receipt(event, res_low)
    assert "Heading Out of Stock" in receipt_low
    assert "Only *`3.0 bags`* left on shelf" in receipt_low

    # Case B: Out of Stock (0 units remaining)
    res_zero = {
        "status": "RECORDED",
        "inventory_depletions": [
            {
                "item_name": "Aashirvaad Atta",
                "matched_sku": "Aashirvaad Atta 10kg",
                "unit": "bags",
                "total_depleted": 1.0,
                "total_remaining": 0.0,
                "shortfall": 0.0,
                "is_fully_fulfilled": True
            }
        ]
    }
    receipt_zero = format_counter_sale_receipt(event, res_zero)
    assert "OUT OF STOCK" in receipt_zero
    assert "completely out of stock for *Aashirvaad Atta 10kg*" in receipt_zero

