"""
app/db/khata_models.py
Phase 2 Inflow, Customer Khata & FIFO Inventory Batch Models.
Domain: Laptop 2 (Developer B) - ACID Financial Core.
"""
import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Float, Integer, Date, DateTime, ForeignKey, Index, text
)
from sqlalchemy.orm import relationship
from app.db.session import Base


def generate_uuid():
    return str(uuid.uuid4())


class CashTransaction(Base):
    """
    Settled liquid cash and digital UPI counter inflows (e.g. +₹300 on Paytm QR or cash counter).
    Part of the double-entry cash flow ledger.
    """
    __tablename__ = "cash_transactions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(64), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(32), default="PAYTM_UPI", nullable=False)  # PAYTM_UPI, CASH, SPLIT
    reference = Column(String(64), nullable=True)  # Optional UPI UTR, payment reference, or receipt ID
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_cash_merchant_created", "merchant_id", "created_at"),
    )


class CustomerKhata(Base):
    """
    Customer store credit ledger (Udhaar Baaki).
    Positive balance = Store Receivable (Customer owes money to merchant).
    Zero balance = Fully settled.
    """
    __tablename__ = "customer_khata"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(64), nullable=False, index=True)
    customer_name = Column(String(128), nullable=False)
    customer_phone = Column(String(20), nullable=True, index=True)
    current_balance = Column(Float, default=0.0, nullable=False)  # Positive = Udhaar Baaki
    total_credit_given = Column(Float, default=0.0, nullable=False)
    total_repaid = Column(Float, default=0.0, nullable=False)
    last_transaction_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    entries = relationship("KhataEntry", back_populates="customer", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_khata_merchant_customer", "merchant_id", "customer_name"),
    )


class KhataEntry(Base):
    """
    Append-only ledger of individual credit/repayment transactions for each customer.
    """
    __tablename__ = "khata_entries"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    khata_id = Column(String(64), ForeignKey("customer_khata.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_id = Column(String(64), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    action = Column(String(32), nullable=False)  # GIVE_CREDIT (Udhaar diya), COLLECT_PAYMENT (Udhaar chukaya)
    balance_after = Column(Float, nullable=False)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    customer = relationship("CustomerKhata", back_populates="entries")

    __table_args__ = (
        Index("idx_khata_entry_merchant_time", "merchant_id", "created_at"),
    )


class InventoryBatch(Base):
    """
    Physical stock batches populated from supplier purchase invoices.
    Depleted oldest-first by Agent 4 (FIFO) with row-level locks.
    """
    __tablename__ = "inventory_batches"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(64), nullable=False, index=True)
    item_name = Column(String(128), nullable=False, index=True)
    batch_number = Column(String(64), nullable=True)
    quantity_initial = Column(Float, nullable=False)
    quantity_remaining = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=False)  # Wholesale purchase rate per unit
    retail_mrp = Column(Float, nullable=True)   # Suggested or active shelf price
    unit = Column(String(32), default="units", nullable=False)
    expiry_date = Column(Date, nullable=True)   # Earliest expiry depleted first
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_inventory_fifo_lookup", "merchant_id", "item_name", "expiry_date", "created_at"),
    )
