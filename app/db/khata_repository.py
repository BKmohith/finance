"""
app/db/khata_repository.py
Repository operations for Counter Sales, Customer Khata (Udhaar) and FIFO Inventory.
Domain: Laptop 2 (Developer B) - ACID Financial Core.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import and_, func, select, text

from app.core.contracts import CounterSaleEvent, PaymentMethod
from app.db.fifo_engine import deplete_inventory_fifo
from app.db.khata_models import CashTransaction, CustomerKhata, InventoryBatch, KhataEntry

logger = logging.getLogger("sahayak.db.khata")


def record_counter_sale(
    session,
    merchant_id: str,
    sale: CounterSaleEvent
) -> Dict[str, Any]:
    """
    Atomically commits a counter sale:
    1. Records settled cash/UPI inflow in `cash_transactions`.
    2. If Udhaar is extended, atomically updates `customer_khata`.
    3. Depletes stock batches sequentially via Agent 4 FIFO engine.
    All operations execute in a single ACID transaction.
    """
    clean_merchant_id = merchant_id.strip()

    # 1. Record Settled Monetary Inflow
    cash_txn = None
    if sale.amount_paid > 0:
        cash_txn = CashTransaction(
            merchant_id=clean_merchant_id,
            amount=round(sale.amount_paid, 2),
            payment_method=sale.payment_method.value if hasattr(sale.payment_method, "value") else str(sale.payment_method),
            reference=sale.payment_reference,
            description=f"Counter Sale ({len(sale.items)} items)"
        )
        session.add(cash_txn)
        session.flush()

    # 2. Record Customer Store Credit (Udhaar) if extended
    khata_record = None
    if sale.credit_amount > 0:
        cust_name = sale.customer_name or "Walk-in Customer"
        khata_record = record_khata_entry(
            session=session,
            merchant_id=clean_merchant_id,
            customer_name=cust_name,
            amount=sale.credit_amount,
            action="GIVE_CREDIT",
            phone=sale.customer_phone,
            notes=f"Credit extended on sale of {len(sale.items)} items"
        )

    # 3. Agent 4: Concurrency-Safe FIFO Inventory Depletion
    depletion_results: List[Dict[str, Any]] = []
    for item in sale.items:
        res = deplete_inventory_fifo(
            session=session,
            merchant_id=clean_merchant_id,
            item_name=item.item_name,
            quantity_to_deplete=item.quantity
        )
        depletion_results.append(res)

    return {
        "status": "RECORDED",
        "merchant_id": clean_merchant_id,
        "cash_transaction_id": cash_txn.id if cash_txn else None,
        "amount_settled": sale.amount_paid,
        "payment_method": str(sale.payment_method),
        "credit_amount": sale.credit_amount,
        "customer_name": sale.customer_name,
        "customer_current_balance": khata_record.current_balance if khata_record else None,
        "inventory_depletions": depletion_results,
        "timestamp": datetime.utcnow().isoformat()
    }


def record_khata_entry(
    session,
    merchant_id: str,
    customer_name: str,
    amount: float,
    action: str,  # "GIVE_CREDIT" or "COLLECT_PAYMENT"
    phone: Optional[str] = None,
    notes: Optional[str] = None
) -> CustomerKhata:
    """
    Updates customer credit ledger and appends to the immutable audit trail:
    - GIVE_CREDIT (Udhaar diya): current_balance += amount
    - COLLECT_PAYMENT (Udhaar chukaya): current_balance -= amount & logs CashTransaction
    """
    if amount <= 0:
        raise ValueError("Khata transaction amount must be greater than zero.")

    clean_name = customer_name.strip()
    norm_action = action.strip().upper()
    if norm_action not in ("GIVE_CREDIT", "COLLECT_PAYMENT"):
        raise ValueError(f"Invalid Khata action: {action}. Must be GIVE_CREDIT or COLLECT_PAYMENT.")

    # Find or create customer Khata
    khata = session.execute(
        select(CustomerKhata)
        .where(
            and_(
                CustomerKhata.merchant_id == merchant_id,
                func.lower(func.trim(CustomerKhata.customer_name)) == func.lower(clean_name)
            )
        )
    ).scalars().first()

    if not khata:
        khata = CustomerKhata(
            merchant_id=merchant_id,
            customer_name=clean_name,
            customer_phone=phone.strip() if phone else None,
            current_balance=0.0,
            total_credit_given=0.0,
            total_repaid=0.0
        )
        session.add(khata)
        session.flush()
    elif phone and not khata.customer_phone:
        khata.customer_phone = phone.strip()

    # Calculate balance changes
    if norm_action == "GIVE_CREDIT":
        khata.current_balance = round(khata.current_balance + amount, 2)
        khata.total_credit_given = round(khata.total_credit_given + amount, 2)
    elif norm_action == "COLLECT_PAYMENT":
        khata.current_balance = round(khata.current_balance - amount, 2)
        khata.total_repaid = round(khata.total_repaid + amount, 2)
        # Log recovered cash as a settled liquid inflow
        settled_cash = CashTransaction(
            merchant_id=merchant_id,
            amount=round(amount, 2),
            payment_method="PAYTM_UPI" if (notes and "paytm" in notes.lower()) else "CASH",
            description=f"Khata Repayment from {clean_name}"
        )
        session.add(settled_cash)

    khata.last_transaction_at = datetime.utcnow()

    # Create immutable audit log entry
    entry = KhataEntry(
        khata_id=khata.id,
        merchant_id=merchant_id,
        amount=round(amount, 2),
        action=norm_action,
        balance_after=khata.current_balance,
        notes=notes
    )
    session.add(entry)
    session.flush()

    return khata


def get_customer_khata(
    session,
    merchant_id: str,
    customer_name: str
) -> Optional[CustomerKhata]:
    """Retrieves customer credit record by name."""
    clean_name = customer_name.strip()
    return session.execute(
        select(CustomerKhata)
        .where(
            and_(
                CustomerKhata.merchant_id == merchant_id,
                func.lower(func.trim(CustomerKhata.customer_name)) == func.lower(clean_name)
            )
        )
    ).scalars().first()


def list_merchant_khatas(
    session,
    merchant_id: str
) -> List[CustomerKhata]:
    """Lists all customer credit records for a merchant."""
    return session.execute(
        select(CustomerKhata)
        .where(CustomerKhata.merchant_id == merchant_id)
        .order_by(CustomerKhata.current_balance.desc(), CustomerKhata.last_transaction_at.desc())
    ).scalars().all()


def setup_phase2_tables_and_rls(engine):
    """
    Initializes Phase 2 tables in Supabase and activates Row-Level Security (RLS) policies.
    """
    from app.db.session import Base
    import app.db.khata_models  # Registers models

    # 1. Create tables
    Base.metadata.create_all(bind=engine)

    # 2. Configure RLS commands
    rls_commands = [
        "ALTER TABLE cash_transactions ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE customer_khata ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE khata_entries ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE inventory_batches ENABLE ROW LEVEL SECURITY;",
        """
        DO $$
        BEGIN
            DROP POLICY IF EXISTS merchant_isolation_cash ON cash_transactions;
            CREATE POLICY merchant_isolation_cash ON cash_transactions
            FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));

            DROP POLICY IF EXISTS merchant_isolation_khata ON customer_khata;
            CREATE POLICY merchant_isolation_khata ON customer_khata
            FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));

            DROP POLICY IF EXISTS merchant_isolation_khata_entries ON khata_entries;
            CREATE POLICY merchant_isolation_khata_entries ON khata_entries
            FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));

            DROP POLICY IF EXISTS merchant_isolation_inventory ON inventory_batches;
            CREATE POLICY merchant_isolation_inventory ON inventory_batches
            FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));
        END $$;
        """
    ]

    with engine.connect() as conn:
        for cmd in rls_commands:
            conn.execute(text(cmd))
        conn.commit()
    logger.info("Phase 2 PostgreSQL RLS policies successfully applied to Supabase.")
