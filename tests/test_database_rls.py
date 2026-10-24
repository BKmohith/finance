"""
tests/test_database_rls.py
Comprehensive test suite for Laptop 2:
1. Multi-Tenant Row-Level Security (RLS) Isolation
2. Agent 3: Margin-Guard Price-Shield Calculation (>3% threshold)
3. Price-Shield Ignores Minor Price Changes (<3% threshold)
"""
import pytest
import uuid
from datetime import date, timedelta
from sqlalchemy import select, text

from app.core.contracts import ExtractedInvoiceData, ExtractedLineItem
from app.db.session import get_rls_session, get_admin_session
from app.db.models import Merchant, Invoice
from app.db.repository import save_extracted_invoice
from app.db.margin_guard import evaluate_price_deviations


@pytest.fixture(scope="module")
def setup_merchants():
    """
    Creates two distinct merchants in Supabase for testing isolation.
    """
    m1_id = f"M_TEST_{uuid.uuid4().hex[:6]}"
    m2_id = f"M_TEST_{uuid.uuid4().hex[:6]}"

    with get_admin_session() as session:
        m1 = Merchant(id=m1_id, name="Ramesh Kirana Store", phone=f"91{uuid.uuid4().int % 10000000000}")
        m2 = Merchant(id=m2_id, name="Gupta Provision Store", phone=f"91{uuid.uuid4().int % 10000000000}")
        session.add_all([m1, m2])

    yield m1_id, m2_id

    # Cleanup after tests
    with get_admin_session() as session:
        session.execute(text("DELETE FROM merchants WHERE id IN (:m1, :m2)"), {"m1": m1_id, "m2": m2_id})


def test_multi_tenant_rls_isolation(setup_merchants):
    """
    Verifies that Merchant A cannot view or query Merchant B's invoices or items
    under PostgreSQL Row-Level Security on Supabase.
    """
    m1_id, m2_id = setup_merchants

    # 1. Ingest an invoice for Merchant A (Ramesh)
    invoice_m1_data = ExtractedInvoiceData(
        supplier_name="ITC Wholesale Distributors",
        invoice_number=f"INV-A-{uuid.uuid4().hex[:4]}",
        invoice_date=date.today(),
        credit_due_date=date.today() + timedelta(days=15),
        items=[
            ExtractedLineItem(
                item_name="Aashirvaad Atta 10kg",
                quantity=10,
                unit="bags",
                unit_wholesale_rate=380.0,
                tax_rate_pct=0.0,
                line_total=3800.0
            )
        ],
        grand_total=3800.0,
        confidence_score=0.98
    )

    with get_rls_session(m1_id) as session:
        inv_m1 = save_extracted_invoice(session, m1_id, invoice_m1_data)
        inv_m1_id = inv_m1.id

    # 2. Ingest an invoice for Merchant B (Gupta)
    invoice_m2_data = ExtractedInvoiceData(
        supplier_name="Hindustan Unilever Depot",
        invoice_number=f"INV-B-{uuid.uuid4().hex[:4]}",
        invoice_date=date.today(),
        credit_due_date=date.today() + timedelta(days=7),
        items=[
            ExtractedLineItem(
                item_name="Lifebuoy Soap 125g",
                quantity=50,
                unit="units",
                unit_wholesale_rate=28.0,
                tax_rate_pct=18.0,
                line_total=1400.0
            )
        ],
        grand_total=1400.0,
        confidence_score=0.96
    )

    with get_rls_session(m2_id) as session:
        inv_m2 = save_extracted_invoice(session, m2_id, invoice_m2_data)
        inv_m2_id = inv_m2.id

    # 3. Query under Merchant A's RLS session:
    with get_rls_session(m1_id) as session:
        m1_invoices = session.execute(select(Invoice)).scalars().all()
        m1_inv_ids = [inv.id for inv in m1_invoices]
        assert inv_m1_id in m1_inv_ids, "Merchant A cannot see their own invoice!"
        assert inv_m2_id not in m1_inv_ids, "CRITICAL: RLS leak! Merchant A saw Merchant B invoice!"

        # Direct query for Merchant B's invoice returns None
        leak_check = session.execute(select(Invoice).where(Invoice.id == inv_m2_id)).scalars().first()
        assert leak_check is None, "CRITICAL: RLS leak! Merchant A accessed Merchant B invoice directly!"

    # 4. Query under Merchant B's RLS session:
    with get_rls_session(m2_id) as session:
        m2_invoices = session.execute(select(Invoice)).scalars().all()
        m2_inv_ids = [inv.id for inv in m2_invoices]
        assert inv_m2_id in m2_inv_ids, "Merchant B cannot see their own invoice!"
        assert inv_m1_id not in m2_inv_ids, "CRITICAL: RLS leak! Merchant B saw Merchant A invoice!"

        # Direct query for Merchant A's invoice returns None
        leak_check = session.execute(select(Invoice).where(Invoice.id == inv_m1_id)).scalars().first()
        assert leak_check is None, "CRITICAL: RLS leak! Merchant B accessed Merchant A invoice directly!"


def test_margin_guard_price_shield_detection(setup_merchants):
    """
    Verifies that Agent 3 (Margin-Guard):
    1. Ignores first baseline invoice.
    2. Flags wholesale price increases >= 3%.
    3. Recomputes recommended retail MRP to protect 12% margin.
    """
    m1_id, _ = setup_merchants

    # Baseline Invoice: Fortune Oil @ ₹140.00
    inv1_data = ExtractedInvoiceData(
        supplier_name="Adani Wilmar Agency",
        invoice_number=f"OIL-BASE-{uuid.uuid4().hex[:4]}",
        invoice_date=date.today() - timedelta(days=7),
        credit_due_date=date.today() + timedelta(days=7),
        items=[
            ExtractedLineItem(
                item_name="Fortune Sunflower Oil 1L",
                quantity=20,
                unit="pouches",
                unit_wholesale_rate=140.0,
                tax_rate_pct=5.0,
                line_total=2800.0
            )
        ],
        grand_total=2800.0,
        confidence_score=0.99
    )

    with get_rls_session(m1_id) as session:
        inv1 = save_extracted_invoice(session, m1_id, inv1_data)
        alerts_base = evaluate_price_deviations(session, m1_id, inv1.id)
        assert len(alerts_base) == 0, "Baseline bill should have 0 alerts"

    # Second Invoice with a 5.0% price increase (₹140.00 -> ₹147.00, +₹7/unit)
    inv2_data = ExtractedInvoiceData(
        supplier_name="Adani Wilmar Agency",
        invoice_number=f"OIL-HIKE-{uuid.uuid4().hex[:4]}",
        invoice_date=date.today(),
        credit_due_date=date.today() + timedelta(days=14),
        items=[
            ExtractedLineItem(
                item_name="Fortune Sunflower Oil 1L",
                quantity=30,
                unit="pouches",
                unit_wholesale_rate=147.0,  # 5% hike
                tax_rate_pct=5.0,
                line_total=4410.0
            )
        ],
        grand_total=4410.0,
        confidence_score=0.98
    )

    with get_rls_session(m1_id) as session:
        inv2 = save_extracted_invoice(session, m1_id, inv2_data)
        alerts = evaluate_price_deviations(
            session, m1_id, inv2.id,
            hike_threshold_pct=3.0,
            target_retail_margin_pct=12.0
        )

        assert len(alerts) == 1, "Expected 1 Margin-Guard alert for Fortune Oil!"
        alert = alerts[0]

        assert alert.item_name == "Fortune Sunflower Oil 1L"
        assert alert.old_wholesale_rate == 140.0
        assert alert.new_wholesale_rate == 147.0
        assert alert.percentage_hike == 5.0
        assert alert.previous_mrp == 156.80          # 140 * 1.12
        assert alert.suggested_new_mrp == 164.64      # 147 * 1.12
        assert alert.estimated_loss_if_unchanged == 210.0  # (147 - 140) * 30


def test_margin_guard_ignores_below_threshold(setup_merchants):
    """
    Verifies that a price change below 3% (e.g., 1.5%) does NOT trigger an alert.
    """
    m1_id, _ = setup_merchants

    # Baseline: Tata Salt @ ₹20.00
    inv1_data = ExtractedInvoiceData(
        supplier_name="Tata Consumer Products",
        invoice_number=f"SALT-1-{uuid.uuid4().hex[:4]}",
        invoice_date=date.today() - timedelta(days=5),
        items=[
            ExtractedLineItem(
                item_name="Tata Salt 1kg",
                quantity=50,
                unit="packets",
                unit_wholesale_rate=20.0,
                line_total=1000.0
            )
        ],
        grand_total=1000.0
    )

    # Next delivery: Tata Salt @ ₹20.30 (+1.5% hike, below 3.0% threshold)
    inv2_data = ExtractedInvoiceData(
        supplier_name="Tata Consumer Products",
        invoice_number=f"SALT-2-{uuid.uuid4().hex[:4]}",
        invoice_date=date.today(),
        items=[
            ExtractedLineItem(
                item_name="Tata Salt 1kg",
                quantity=50,
                unit="packets",
                unit_wholesale_rate=20.30,  # 1.5% hike (< 3.0%)
                line_total=1015.0
            )
        ],
        grand_total=1015.0
    )

    with get_rls_session(m1_id) as session:
        save_extracted_invoice(session, m1_id, inv1_data)
        inv2 = save_extracted_invoice(session, m1_id, inv2_data)
        alerts = evaluate_price_deviations(session, m1_id, inv2.id, hike_threshold_pct=3.0)

        assert len(alerts) == 0, "No alert should trigger for minor 1.5% price shift"
