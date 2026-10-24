"""
app/db/repository.py
ACID transactional write and read operations for Sahayak financial ledger.
"""
import hashlib
import json
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc

from app.core.contracts import ExtractedInvoiceData, ExtractedLineItem
from app.db.models import (
    Merchant, Supplier, Invoice, InvoiceItem, PriceHistory, StatutoryAuditLog
)


def get_or_create_merchant(session: Session, merchant_id: str, name: str = "Sahayak Retail Merchant", phone: Optional[str] = None) -> Merchant:
    stmt = select(Merchant).where(Merchant.id == merchant_id)
    merchant = session.execute(stmt).scalars().first()
    if not merchant:
        import uuid
        phone_num = phone or f"+91{uuid.uuid4().int % 10000000000:010d}"
        merchant = Merchant(
            id=merchant_id,
            name=name,
            phone=phone_num
        )
        session.add(merchant)
        session.flush()
    return merchant


def get_or_create_supplier(session: Session, merchant_id: str, supplier_name: str, supplier_gstin: Optional[str] = None) -> Supplier:
    """
    Looks up an existing supplier for this merchant by name, or creates a new one.
    """
    stmt = select(Supplier).where(
        and_(
            Supplier.merchant_id == merchant_id,
            Supplier.name == supplier_name
        )
    )
    supplier = session.execute(stmt).scalars().first()

    if not supplier:
        supplier = Supplier(
            merchant_id=merchant_id,
            name=supplier_name,
            gstin=supplier_gstin
        )
        session.add(supplier)
        session.flush()  # Populates supplier.id

    return supplier


def save_extracted_invoice(session: Session, merchant_id: str, data: ExtractedInvoiceData) -> Invoice:
    """
    Atomic transactional write of an extracted invoice into the PostgreSQL ledger.
    
    1. Resolves/Creates Supplier
    2. Writes Invoice Header
    3. Batch writes Invoice Line Items
    4. Appends to PriceHistory for margin tracking
    5. Writes cryptographic audit log entry
    """
    # 0. Ensure Merchant exists
    get_or_create_merchant(session=session, merchant_id=merchant_id)

    # 1. Supplier
    supplier = get_or_create_supplier(
        session=session,
        merchant_id=merchant_id,
        supplier_name=data.supplier_name,
        supplier_gstin=data.supplier_gstin
    )

    # 2. Invoice Header
    invoice = Invoice(
        merchant_id=merchant_id,
        supplier_id=supplier.id,
        invoice_number=data.invoice_number,
        invoice_date=data.invoice_date,
        credit_due_date=data.credit_due_date,
        grand_total=data.grand_total,
        confidence_score=data.confidence_score,
        status="LOGGED"
    )
    session.add(invoice)
    session.flush()  # Populates invoice.id

    # 3. Line Items & Price History
    for item in data.items:
        # Create Line Item
        db_item = InvoiceItem(
            invoice_id=invoice.id,
            merchant_id=merchant_id,
            item_name=item.item_name,
            brand=item.brand,
            batch_number=item.batch_number,
            quantity=item.quantity,
            unit=item.unit,
            unit_wholesale_rate=item.unit_wholesale_rate,
            tax_rate_pct=item.tax_rate_pct,
            line_total=item.line_total
        )
        session.add(db_item)

        # Append to Price History for Margin-Guard tracking
        price_entry = PriceHistory(
            merchant_id=merchant_id,
            item_name=item.item_name,
            supplier_id=supplier.id,
            unit_wholesale_rate=item.unit_wholesale_rate
        )
        session.add(price_entry)

    # 4. Cryptographic Audit Log
    payload_str = json.dumps({
        "invoice_num": data.invoice_number,
        "grand_total": data.grand_total,
        "supplier": data.supplier_name,
        "item_count": len(data.items)
    }, sort_keys=True)
    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    audit_entry = StatutoryAuditLog(
        merchant_id=merchant_id,
        action="INVOICE_LOGGED",
        payload_hash=payload_hash
    )
    session.add(audit_entry)

    # Flush all items, price history and audit log so subsequent queries see them
    session.flush()

    return invoice
