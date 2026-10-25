"""
app/db/models.py
SQLAlchemy 2.0 ORM models for Sahayak double-entry financial core.
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


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(128), nullable=False)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    gstin = Column(String(30), nullable=True)
    telegram_chat_id = Column(String(64), nullable=True, index=True)
    email = Column(String(128), nullable=True)
    business_type = Column(String(64), nullable=True)
    city = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    suppliers = relationship("Supplier", back_populates="merchant", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="merchant", cascade="all, delete-orphan")

    @property
    def business_name(self) -> str:
        return self.name

    @business_name.setter
    def business_name(self, value: str):
        self.name = value


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(64), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    gstin = Column(String(30), nullable=True)
    payment_terms_days = Column(Integer, default=15, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="suppliers")
    invoices = relationship("Invoice", back_populates="supplier")

    __table_args__ = (
        Index("idx_supplier_merchant_name", "merchant_id", "name"),
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(64), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(String(64), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_number = Column(String(64), nullable=False)
    invoice_date = Column(Date, nullable=False)
    credit_due_date = Column(Date, nullable=True)  # Cheque payment date
    grand_total = Column(Float, nullable=False)
    confidence_score = Column(Float, default=0.95, nullable=False)
    status = Column(String(32), default="LOGGED", nullable=False)  # LOGGED, PAID, DISPUTED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    merchant = relationship("Merchant", back_populates="invoices")
    supplier = relationship("Supplier", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

    @property
    def total_amount(self) -> float:
        return self.grand_total

    @total_amount.setter
    def total_amount(self, value: float):
        self.grand_total = value

    @property
    def supplier_name(self) -> str:
        return self.supplier.name if self.supplier else "Distributor"

    __table_args__ = (
        Index("idx_invoice_merchant_due", "merchant_id", "credit_due_date"),
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_line_items"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    invoice_id = Column(String(64), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_id = Column(String(64), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    item_name = Column(String(128), nullable=False, index=True)
    brand = Column(String(64), nullable=True)
    batch_number = Column(String(64), nullable=True)
    quantity = Column(Float, nullable=False)
    unit = Column(String(32), default="units", nullable=False)
    unit_wholesale_rate = Column(Float, nullable=False)
    tax_rate_pct = Column(Float, default=0.0, nullable=False)
    line_total = Column(Float, nullable=False)

    invoice = relationship("Invoice", back_populates="items")


class PriceHistory(Base):
    """
    Historical log of wholesale purchase prices per SKU.
    Used by Agent 3 (Margin-Guard) to detect price spikes.
    """
    __tablename__ = "price_history"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(64), ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True)
    item_name = Column(String(128), nullable=False, index=True)
    supplier_id = Column(String(64), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    unit_wholesale_rate = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_price_history_lookup", "merchant_id", "item_name", "recorded_at"),
    )


class StatutoryAuditLog(Base):
    """
    Append-only statutory audit trail.
    """
    __tablename__ = "statutory_audit_log"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False)  # INVOICE_LOGGED, PRICE_ALERT_SENT
    payload_hash = Column(String(64), nullable=False)  # SHA-256
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
