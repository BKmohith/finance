"""
app/core/contracts.py
SHARED FROZEN CONTRACT ACROSS LAPTOP 1, LAPTOP 2, AND LAPTOP 3
Zero-Conflict Multi-Device Architecture for Sahayak Phase 1.
"""
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field


# --- 1. WhatsApp Inbound Payload (Used by Laptop 1) ---
class WebhookMediaItem(BaseModel):
    media_id: str = Field(description="Unique Meta/storage media identifier")
    mime_type: str = Field(default="image/jpeg", description="MIME type e.g. image/jpeg, image/png")
    sha256: str = Field(description="Perceptual or cryptographic SHA-256 hash of the media content")
    file_size: int = Field(default=0, description="Size of file in bytes")


class InboundInvoiceEvent(BaseModel):
    merchant_id: str = Field(description="Tenant merchant ID (e.g. M_9876543210)")
    sender_phone: str = Field(description="E.164 phone number of sender e.g. +919876543210")
    whatsapp_message_id: str = Field(description="Unique Meta WhatsApp message ID (wam.id)")
    media: WebhookMediaItem
    timestamp: int = Field(description="Epoch timestamp in seconds")


# --- 2. Invoice OCR Extracted Schema (Used by Laptop 3 & Laptop 2) ---
class ExtractedLineItem(BaseModel):
    item_name: str = Field(description="Normalized FMCG item name e.g. Fortune Sunflower Oil 1L")
    brand: Optional[str] = Field(default=None, description="Brand name if detected")
    batch_number: Optional[str] = Field(default=None, description="Manufacturer batch number")
    quantity: float = Field(gt=0, description="Quantity delivered")
    unit: str = Field(default="units", description="units, cartons, kg, litres, bags")
    unit_wholesale_rate: float = Field(gt=0, description="Purchase rate per unit before tax")
    tax_rate_pct: float = Field(default=0.0, ge=0.0, le=28.0, description="GST slab percentage")
    line_total: float = Field(gt=0, description="Total amount for this line item")


class ExtractedInvoiceData(BaseModel):
    supplier_name: str = Field(description="Distributor/Wholesaler business trade name")
    supplier_gstin: Optional[str] = Field(default=None, description="15-character Indian GSTIN if present")
    invoice_number: str = Field(description="Invoice reference number")
    invoice_date: date = Field(description="Invoice billing date")
    credit_due_date: Optional[date] = Field(default=None, description="Payment deadline or cheque due date")
    items: List[ExtractedLineItem] = Field(default_factory=list, description="Extracted line items")
    grand_total: float = Field(description="Grand total bill amount in INR")
    confidence_score: float = Field(default=0.95, ge=0.0, le=1.0, description="Gemini vision confidence score")


# --- 3. Price-Shield Deviation Alert (Used by Laptop 2 & Laptop 1) ---
class PriceHikeAlert(BaseModel):
    merchant_id: str = Field(description="Merchant ID")
    merchant_phone: Optional[str] = Field(default=None, description="Merchant phone for alert delivery")
    item_name: str = Field(description="Product SKU name")
    old_wholesale_rate: float = Field(description="Previous wholesale rate per unit")
    new_wholesale_rate: float = Field(description="Current new wholesale rate per unit")
    percentage_hike: float = Field(description="Price increase percentage (e.g. 5.2%)")
    previous_mrp: float = Field(description="Existing retail shelf MRP")
    suggested_new_mrp: float = Field(description="Recommended shelf MRP to protect margin")
    estimated_loss_if_unchanged: float
    supplier_name: Optional[str] = None
    rate_difference: Optional[float] = None
    comparison_summary: Optional[str] = None = Field(default=0.0, description="Estimated monthly profit loss")


# --- 4. Celery Task Contract (Used by Laptop 1 to dispatch, Laptop 3 to execute) ---
# Task Name: "workers.process_invoice"
# Arguments: (merchant_id: str, media_id: str, whatsapp_message_id: str, sender_phone: str)
CELERY_INVOICE_TASK_NAME = "workers.process_invoice"
