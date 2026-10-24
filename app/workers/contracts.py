"""
app/workers/contracts.py
Pydantic contracts and shared interfaces for Laptop 3 (Vision AI & OCR Worker).
Self-contained to eliminate cross-laptop git conflicts on app/core/contracts.py.
Seamlessly falls back to app.core.contracts if available upon repo merge.
"""
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field

# 1. Line Item Schema
class ExtractedLineItem(BaseModel):
    item_name: str = Field(description="Normalized FMCG item name e.g. Fortune Sunflower Oil 1L")
    brand: Optional[str] = None
    batch_number: Optional[str] = None
    quantity: float = Field(gt=0, description="Quantity delivered")
    unit: str = Field(default="units", description="units, cartons, kg, litres")
    unit_wholesale_rate: float = Field(gt=0, description="Purchase rate per unit before tax")
    tax_rate_pct: float = Field(default=0.0, ge=0.0, le=28.0)
    line_total: float = Field(gt=0, description="Total amount for this line item")


# 2. Extracted Invoice Schema
class ExtractedInvoiceData(BaseModel):
    supplier_name: str
    supplier_gstin: Optional[str] = None
    invoice_number: str
    invoice_date: date
    credit_due_date: Optional[date] = Field(default=None, description="Payment deadline or cheque due date")
    items: List[ExtractedLineItem]
    grand_total: float
    confidence_score: float = Field(ge=0.0, le=1.0)


# 3. Price-Shield Deviation Alert (Handoff to Laptop 1 & 2)
class PriceHikeAlert(BaseModel):
    merchant_id: str
    merchant_phone: str
    item_name: str
    old_wholesale_rate: float
    new_wholesale_rate: float
    percentage_hike: float
    previous_mrp: float
    suggested_new_mrp: float
    estimated_loss_if_unchanged: float
    supplier_name: Optional[str] = None
    rate_difference: Optional[float] = None
    comparison_summary: Optional[str] = None


# 4. Celery Task Contract
CELERY_INVOICE_TASK_NAME = "workers.process_invoice"
