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
    estimated_loss_if_unchanged: float = Field(default=0.0, description="Estimated monthly profit loss")
    supplier_name: Optional[str] = None
    rate_difference: Optional[float] = None
    comparison_summary: Optional[str] = None


# --- 4. Celery Task Contract (Used by Laptop 1 to dispatch, Laptop 3 to execute) ---
# Task Name: "workers.process_invoice"
# Arguments: (merchant_id: str, media_id: str, whatsapp_message_id: str, sender_phone: str)
CELERY_INVOICE_TASK_NAME = "workers.process_invoice"


# ============================================================================
# --- PHASE 2 SHARED FROZEN CONTRACTS (Inflow Rails, Khata & FIFO) ---
# ============================================================================
from enum import Enum
from datetime import datetime


class PaymentMethod(str, Enum):
    PAYTM_UPI = "PAYTM_UPI"
    CASH = "CASH"
    KHATA_CREDIT = "KHATA_CREDIT"      # Udhaar
    SPLIT = "SPLIT"                    # Part cash/UPI, part credit


class CounterItemSale(BaseModel):
    item_name: str = Field(description="SKU or product name, e.g. Fortune Sunflower Oil 1L")
    quantity: float = Field(gt=0, description="Quantity sold")
    unit: str = Field(default="units", description="units, kg, litre, packet")
    unit_retail_price: float = Field(gt=0, description="Retail selling price per unit")
    line_total: float = Field(gt=0, description="quantity * unit_retail_price")


# --- 5. Normalized Counter Sale Contract (Emitted by Laptop 1, Ingested by L2 & L3) ---
class CounterSaleEvent(BaseModel):
    merchant_id: str
    amount_paid: float = Field(ge=0.0, description="Total monetary amount received")
    payment_method: PaymentMethod = Field(default=PaymentMethod.PAYTM_UPI)
    payment_reference: Optional[str] = Field(default=None, description="Optional UPI UTR or Txn ID")
    items: List[CounterItemSale] = Field(default_factory=list, description="Itemized basket SKUs")
    customer_phone: Optional[str] = Field(default=None, description="Required if Udhaar/Khata credit given")
    customer_name: Optional[str] = Field(default=None, description="Customer name for Khata ledger")
    credit_amount: float = Field(default=0.0, ge=0.0, description="Unpaid balance added to customer Khata")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- 6. Voice Khata Inbound Contract (Produced by Laptop 3, Dispatched by Laptop 1) ---
class VoiceKhataIntent(BaseModel):
    customer_name: str
    amount: float = Field(gt=0)
    action: str = Field(description="GIVE_CREDIT (Udhaar diya) or COLLECT_PAYMENT (Udhaar chukaya)")
    transcription: str
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


# --- 7. FIFO Depletion Task Payload (Processed by Laptop 2) ---
class FIFODepletionRequest(BaseModel):
    merchant_id: str
    sale_id: str
    items: List[CounterItemSale]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- 8. System 1 (Jev Router) Payload Classification ---
class InboundIntentClass(str, Enum):
    MEME_SPAM = "MEME_SPAM"             # Drop in <18ms ($0)
    COUNTER_SALE = "COUNTER_SALE"       # Process sale + FIFO depletion
    VOICE_KHATA = "VOICE_KHATA"         # Agent 1 customer credit update
    INVOICE_BILL = "INVOICE_BILL"       # Phase 1 wholesale bill OCR


CELERY_COUNTER_TASK_NAME = "workers.process_counter_sale"

