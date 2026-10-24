"""
app/core/contracts.py
SHARED FROZEN CONTRACT ACROSS LAPTOP 1, LAPTOP 2, AND LAPTOP 3
Defines the unalterable Pydantic contracts and shared interfaces across all domains.
"""
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field


# --- 1. WhatsApp Inbound Payload (Used by Laptop 1) ---
class WebhookMediaItem(BaseModel):
    media_id: str
    mime_type: str
    sha256: str
    file_size: int


class InboundInvoiceEvent(BaseModel):
    merchant_id: str
    sender_phone: str
    whatsapp_message_id: str
    media: WebhookMediaItem
    timestamp: int


# --- 2. Invoice OCR Extracted Schema (Used by Laptop 3 & Laptop 2) ---
class ExtractedLineItem(BaseModel):
    item_name: str = Field(description="Normalized FMCG item name e.g. Fortune Sunflower Oil 1L")
    brand: Optional[str] = None
    batch_number: Optional[str] = None
    quantity: float = Field(gt=0, description="Quantity delivered")
    unit: str = Field(default="units", description="units, cartons, kg, litres")
    unit_wholesale_rate: float = Field(gt=0, description="Purchase rate per unit before tax")
    tax_rate_pct: float = Field(default=0.0, ge=0.0, le=28.0)
    line_total: float = Field(gt=0, description="Total amount for this line item")


class ExtractedInvoiceData(BaseModel):
    supplier_name: str
    supplier_gstin: Optional[str] = None
    invoice_number: str
    invoice_date: date
    credit_due_date: Optional[date] = Field(default=None, description="Payment deadline or cheque due date")
    items: List[ExtractedLineItem]
    grand_total: float
    confidence_score: float = Field(ge=0.0, le=1.0)


# --- 3. Price-Shield Deviation Alert (Used by Laptop 2 & Laptop 1) ---
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


# --- 4. Celery Task Contract (Used by Laptop 1 to dispatch, Laptop 3 to execute) ---
# Task Name: "workers.process_invoice"
# Arguments: (merchant_id: str, media_id: str, whatsapp_message_id: str, sender_phone: str)
CELERY_INVOICE_TASK_NAME = "workers.process_invoice"
