# Sahayak (सहायक) — Phase 1 Multi-Device Implementation Plan
## Tri-Laptop Decoupled Engineering Blueprint (Zero-Conflict Contract Architecture)
### Target Milestone: Phase 1 — Outflow Engine & Paper Bill Digitizer ("Price-Shield" MVP)

---

## 1. Multi-Device Architecture & Separation Strategy

To ensure **3 laptops (Developers A, B, and C)** with Antigravity Pro accounts can work 100% in parallel without merge conflicts, the codebase is isolated into distinct domains separated by a **Frozen Interface Contract** (`app/core/contracts.py`).

```
                                  ┌────────────────────────────────────────┐
                                  │      SHARED FROZEN CONTRACT            │
                                  │     (app/core/contracts.py)            │
                                  │   Pydantic Schemas & Task Signatures   │
                                  └───────────────────┬────────────────────┘
                                                      │
         ┌────────────────────────────────────────────┼────────────────────────────────────────────┐
         ▼                                            ▼                                            ▼
┌───────────────────────────────┐     ┌───────────────────────────────┐     ┌───────────────────────────────┐
│           LAPTOP 1            │     │           LAPTOP 2            │     │           LAPTOP 3            │
│  Gateway, Ingest & Alerts     │     │  Database, RLS & Margin Core  │     │  OpenCV, Gemini Vision & OCR  │
│                               │     │                               │     │                               │
│  • WhatsApp Webhook Ingestion │     │  • PostgreSQL 16 + RLS Setup  │     │  • OpenCV Bill Preprocessing  │
│  • HMAC-SHA256 Signature      │     │  • SQLAlchemy 2.0 Models      │     │  • Gemini 1.5 Flash Vision    │
│  • Redis 7.2 Idempotency Drop │     │  • Double-Entry Ledger Schema │     │  • JSON Schema Guardrail      │
│  • WhatsApp Outbound Alerts   │     │  • Margin Guard Trigger Math  │     │  • Celery Async Worker Task   │
│  • Git Branch: `feat/gateway` │     │  • Git Branch: `feat/db-core` │     │  • Git Branch: `feat/vision`  │
└───────────────────────────────┘     └───────────────────────────────┘     └───────────────────────────────┘
```

### Git Repository Directory Boundaries (Strict Ownership)

```
sahayak/
├── app/
│   ├── core/                        # SHARED FROZEN CONTRACT (No unilateral edits!)
│   │   ├── config.py
│   │   └── contracts.py
│   │
│   ├── api/                         # [LAPTOP 1 EXCLUSIVE DOMAIN]
│   │   ├── __init__.py
│   │   ├── routes.py                # FastAPI Webhook routes
│   │   ├── security.py              # Meta HMAC signature validator
│   │   ├── deduplication.py         # Redis SHA-256 perceptual hash checker
│   │   └── notifier.py              # WhatsApp Cloud API template sender
│   │
│   ├── db/                          # [LAPTOP 2 EXCLUSIVE DOMAIN]
│   │   ├── __init__.py
│   │   ├── session.py               # RLS-scoped PgBouncer engine
│   │   ├── models.py                # SQLAlchemy 2.0 ORM tables
│   │   ├── repository.py            # ACID transactional write functions
│   │   └── margin_guard.py          # Deterministic price-hike calculator
│   │
│   └── workers/                     # [LAPTOP 3 EXCLUSIVE DOMAIN]
│       ├── __init__.py
│       ├── tasks.py                 # Celery async invoice ingestion task
│       ├── preprocessor.py          # OpenCV contrast, deskew & clean
│       ├── gemini_extractor.py      # Gemini 1.5 Flash structured OCR
│       └── guardrails.py            # Arithmetic validator (qty * rate == subtotal)
│
├── tests/
│   ├── test_gateway.py              # Laptop 1 tests
│   ├── test_database_rls.py         # Laptop 2 tests
│   └── test_vision_worker.py        # Laptop 3 tests
└── docker-compose.yml               # Postgres 16, Redis 7.2, RabbitMQ/Redis Broker
```

---

## 2. The Shared Frozen Contract (`app/core/contracts.py`)

> **MANDATORY RULE FOR ALL 3 LAPTOPS:**  
> This file is created first. No laptop may change field names or types without mutual agreement. All 3 laptops code strictly to these Pydantic models.

```python
"""
app/core/contracts.py
SHARED FROZEN CONTRACT ACROSS LAPTOP 1, LAPTOP 2, AND LAPTOP 3
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

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
    credit_due_date: Optional[date] = Field(description="Payment deadline or cheque due date")
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
```

---

## 3. Laptop 1: The Gateway, Deduplication & Alerts Engineer

### Objective
Build the outer perimeter: receive incoming WhatsApp webhook traffic, verify security HMAC, deduplicate repetitive uploads in $<1\text{ms}$, dispatch tasks to Celery, and send outbound WhatsApp Margin-Guard alerts.

### Assigned Files
* `app/api/routes.py`
* `app/api/security.py`
* `app/api/deduplication.py`
* `app/api/notifier.py`
* `tests/test_gateway.py`

### Infrastructure Needed
* **Runtime:** Python 3.11+, FastAPI, Uvicorn
* **Cache/Store:** Local Redis 7.2 container (`docker run -p 6379:6379 redis:7.2-alpine`)
* **Meta API:** WhatsApp Cloud API Test App Token & Webhook Verify Token

### Step-by-Step Implementation

1. **Meta Webhook Verification (`app/api/security.py`):**
   * Implement `GET /webhook/whatsapp` handling Meta’s `hub.challenge` verification.
   * Implement `validate_hub_signature(request_body: bytes, x_hub_signature_256: str)` using HMAC-SHA256 with Meta App Secret.
2. **Perceptual Deduplication Engine (`app/api/deduplication.py`):**
   * Hash incoming media using SHA-256.
   * Query Redis: `SET invoice_hash:{merchant_id}:{sha256} 1 EX 172800 NX` (48-hour TTL).
   * If Redis returns `None` (key already exists), return HTTP 200 immediately with status `"DUPLICATE_DROPPED"` and terminate.
3. **Task Dispatcher (`app/api/routes.py`):**
   * Parse inbound media payload into `InboundInvoiceEvent`.
   * Dispatch to Celery:
     ```python
     from celery import Celery
     celery_client = Celery('sahayak_tasks', broker='redis://localhost:6379/0')
     celery_client.send_task(
         "workers.process_invoice",
         kwargs={
             "merchant_id": event.merchant_id,
             "media_id": event.media.media_id,
             "whatsapp_message_id": event.whatsapp_message_id,
             "sender_phone": event.sender_phone
         }
     )
     ```
4. **Outbound Price-Shield Notifier (`app/api/notifier.py`):**
   * Implements `send_price_shield_alert(alert: PriceHikeAlert)` calling Meta WhatsApp Cloud API endpoint:
     `POST https://graph.facebook.com/v19.0/{phone_number_id}/messages`
   * Message template payload:
     *`"⚠️ Price-Shield Alert: {item_name} wholesale cost rose from ₹{old} to ₹{new} (+{hike}%). Raise shelf price to ₹{new_mrp} to protect 10% margin!"`*

### Mocking & Isolated Testing (How Laptop 1 works without L2 & L3)
* Create `tests/test_gateway.py`:
  * Use FastAPI `TestClient`.
  * Mock Meta Webhook POST payload.
  * Mock Celery `send_task` using `unittest.mock.patch`.
  * **Verify:** Webhook returns HTTP 200 in $<25\text{ms}$; duplicate payloads are dropped in $<1\text{ms}$; outbound WhatsApp alert sends successfully with mock payload.

---

## 4. Laptop 2: The Data Core, Security & Margin Engine

### Objective
Build the transactional PostgreSQL double-entry core, configure multi-tenant Row-Level Security (RLS), build repository CRUD methods, and code the deterministic **Margin-Guard Price Shield trigger**.

### Assigned Files
* `app/db/session.py`
* `app/db/models.py`
* `app/db/repository.py`
* `app/db/margin_guard.py`
* `tests/test_database_rls.py`

### Infrastructure Needed
* **Runtime:** Python 3.11+, SQLAlchemy 2.0, Alembic
* **Database:** PostgreSQL 16 (`docker run -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16-alpine`)
* **Connection Pooler:** PgBouncer (optional local container for pool leak testing)

### Step-by-Step Implementation

1. **SQLAlchemy 2.0 Models (`app/db/models.py`):**
   * `Merchant`: `id`, `name`, `phone`, `gstin`, `created_at`.
   * `Supplier`: `id`, `merchant_id`, `name`, `gstin`, `payment_terms_days`.
   * `Invoice`: `id`, `merchant_id`, `supplier_id`, `invoice_num`, `invoice_date`, `due_date`, `grand_total`, `status`.
   * `InvoiceItem`: `id`, `invoice_id`, `merchant_id`, `item_name`, `qty`, `unit_rate`, `tax_pct`, `line_total`.
   * `PriceHistory`: `id`, `merchant_id`, `item_name`, `supplier_id`, `unit_rate`, `recorded_at`.
   * `StatutoryAuditLog`: `id`, `merchant_id`, `action`, `payload_hash`, `timestamp`.
2. **Session-Scoped Row-Level Security (`app/db/session.py`):**
   * Configure context manager:
     ```python
     @contextmanager
     def get_rls_session(merchant_id: str):
         session = SessionLocal()
         try:
             session.execute(text("SELECT set_config('app.current_merchant_id', :m_id, true)"), {"m_id": merchant_id})
             yield session
             session.commit()
         except Exception:
             session.rollback()
             raise
         finally:
             session.close()
     ```
   * Enable PostgreSQL RLS:
     ```sql
     ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
     CREATE POLICY merchant_isolation_policy ON invoices 
     FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));
     ```
3. **Repository Operations (`app/db/repository.py`):**
   * `save_extracted_invoice(merchant_id: str, data: ExtractedInvoiceData) -> Invoice`:
     * Inserts supplier (or fetches existing).
     * Creates invoice header and batch-inserts line items inside a single ACID transaction.
     * Appends to `PriceHistory`.
4. **Deterministic Margin-Guard Calculator (`app/db/margin_guard.py`):**
   * Implements `evaluate_price_deviations(merchant_id: str, invoice_id: str) -> List[PriceHikeAlert]`.
   * Queries previous purchase price for each item.
   * If $\frac{\text{new} - \text{old}}{\text{old}} \times 100 > 3.0\%$:
     * Calculates `suggested_new_mrp = new_rate * 1.12` (assuming standard 12% retail markup).
     * Instantiates and returns `PriceHikeAlert` objects.

### Mocking & Isolated Testing (How Laptop 2 works without L1 & L3)
* Create `tests/test_database_rls.py`:
  * Seed database with test merchants `M_001` and `M_002`.
  * Instantiate dummy `ExtractedInvoiceData` conforming to the contract.
  * Call `save_extracted_invoice("M_001", dummy_data)`.
  * Attempt to query the invoice using a session configured for `M_002` $\rightarrow$ **Assert that 0 rows are returned (RLS works)**.
  * Feed an invoice with a 5% rate increase $\rightarrow$ **Assert that `PriceHikeAlert` is generated accurately**.

---

## 5. Laptop 3: The Vision AI, OpenCV & OCR Guardrails Engineer

### Objective
Build the asynchronous Celery perceptual worker: clean noisy camera images with OpenCV, call Gemini 1.5 Flash in Spatial Vision mode with rigid JSON schemas, run arithmetic guardrail verification, and pass clean data to the DB repository.

### Assigned Files
* `app/workers/tasks.py`
* `app/workers/preprocessor.py`
* `app/workers/gemini_extractor.py`
* `app/workers/guardrails.py`
* `tests/test_vision_worker.py`

### Infrastructure Needed
* **Runtime:** Python 3.11+, Celery, OpenCV (`opencv-python-headless`)
* **AI SDK:** `google-genai` (Google GenAI Python SDK)
* **Credentials:** Google Gemini API Key (`GEMINI_API_KEY`)

### Step-by-Step Implementation

1. **Image Preprocessor (`app/workers/preprocessor.py`):**
   * Convert image to grayscale.
   * Apply Bilateral Filtering to remove dot-matrix background noise while preserving sharp font edges:
     `cv2.bilateralFilter(gray, 9, 75, 75)`
   * Adaptive Contrast Stretching (CLAHE) to fix uneven shop lighting/shadows.
   * Auto-deskew orientation using Hough line transform.
2. **Gemini 1.5 Flash Structured Ingestion (`app/workers/gemini_extractor.py`):**
   * Calls Gemini 1.5 Flash with **Rigid JSON Schema**:
     ```python
     from google import genai
     from google.genai import types
     from app.core.contracts import ExtractedInvoiceData

     client = genai.Client()

     def extract_invoice_from_image(image_bytes: bytes) -> ExtractedInvoiceData:
         prompt = (
             "You are an expert Indian FMCG wholesale invoice decoder. "
             "Extract the supplier name, invoice date, payment due date (or credit terms), "
             "and all itemized products with quantities, wholesale unit rates, and totals. "
             "Decode dot-matrix typography and regional handwriting accurately."
         )
         response = client.models.generate_content(
             model="gemini-1.5-flash",
             contents=[
                 types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                 prompt
             ],
             config=types.GenerateContentConfig(
                 response_mime_type="application/json",
                 response_schema=ExtractedInvoiceData,
                 temperature=0.0
             )
         )
         return ExtractedInvoiceData.model_validate_json(response.text)
     ```
3. **Arithmetic Guardrail Validator (`app/workers/guardrails.py`):**
   * Verify every line item:
     $$|\text{quantity} \times \text{unit\_wholesale\_rate} - \text{line\_total}| < 1.0$$
   * Verify grand total:
     $$|\sum \text{line\_total} - \text{grand\_total}| < 2.0$$
   * If arithmetic checks fail, reject unverified AI math and flag for human review.
4. **Celery Worker Orchestration (`app/workers/tasks.py`):**
   * Implements the Celery task:
     ```python
     @celery_app.task(name="workers.process_invoice")
     def process_invoice_task(merchant_id: str, media_id: str, whatsapp_message_id: str, sender_phone: str):
         image_bytes = fetch_media_from_storage_or_meta(media_id)
         clean_image = preprocess_bill_image(image_bytes)
         extracted_data = extract_invoice_from_image(clean_image)
         validated_data = validate_arithmetic(extracted_data)
         
         # Call Laptop 2's DB repository (or mocked repo in isolation)
         saved_invoice = repository.save_extracted_invoice(merchant_id, validated_data)
         alerts = margin_guard.evaluate_price_deviations(merchant_id, saved_invoice.id)
         
         # Call Laptop 1's notification dispatcher if alerts exist
         for alert in alerts:
             alert.merchant_phone = sender_phone
             notifier.send_price_shield_alert(alert)
     ```

### Mocking & Isolated Testing (How Laptop 3 works without L1 & L2)
* Create `tests/test_vision_worker.py`:
  * Place 3 sample Indian bill photos in a `fixtures/bills/` folder.
  * Run the extraction pipeline offline.
  * Mock `repository.save_extracted_invoice` with a dummy function returning a fake invoice object.
  * **Assert:** Extracted Pydantic object matches `ExtractedInvoiceData` schema with $>95\%$ OCR field accuracy and passed arithmetic checks.

---

## 6. Zero-Conflict Merge Protocol & Integration Sequence

When all 3 laptops complete their isolated unit tests, merge in this strict sequence:

```
  STEP 1: Merge Laptop 2 (Database & Models) ──> `main`
          • Run Alembic migrations on target PostgreSQL instance.
          • Verify tables and RLS policies are active.
          │
          ▼
  STEP 2: Merge Laptop 3 (Vision AI & Worker) ──> `main`
          • Plugs `tasks.py` into Laptop 2's `repository.py`.
          • Test running Celery worker against live Postgres.
          │
          ▼
  STEP 3: Merge Laptop 1 (Gateway & Webhooks) ──> `main`
          • Connects FastAPI route to Celery task queue.
          • Connects notifier to Laptop 2's `PriceHikeAlert` objects.
          │
          ▼
  STEP 4: Run End-to-End Golden Bill Verification
```

### End-to-End Verification Command
```bash
# Run on the integration machine after merging all 3 branches:
pytest tests/test_gateway.py tests/test_database_rls.py tests/test_vision_worker.py -v
```

---

## 7. Responsibilities Matrix Summary

| Area | Laptop 1 (Dev A) | Laptop 2 (Dev B) | Laptop 3 (Dev C) |
| :--- | :---: | :---: | :---: |
| **Git Branch** | `feat/gateway` | `feat/db-core` | `feat/vision` |
| **Meta Webhook & HMAC** | **OWNER** | Observer | Observer |
| **Redis Deduplication** | **OWNER** | Observer | Observer |
| **Outbound WhatsApp Alert** | **OWNER** | Observer | Observer |
| **PostgreSQL 16 & RLS** | Observer | **OWNER** | Observer |
| **Double-Entry Ledger SQL** | Observer | **OWNER** | Observer |
| **Margin-Guard Price Math** | Observer | **OWNER** | Observer |
| **OpenCV Image Clean** | Observer | Observer | **OWNER** |
| **Gemini 1.5 Flash Vision** | Observer | Observer | **OWNER** |
| **Arithmetic Guardrail** | Observer | Observer | **OWNER** |
| **Celery Worker Task** | Dispatches Task | Observer | **Executes Task** |

---

> **Ready to Start:**  
> 1. Laptop 1 checkouts `feat/gateway`  
> 2. Laptop 2 checkouts `feat/db-core`  
> 3. Laptop 3 checkouts `feat/vision`  
> All 3 copy the shared `contracts.py` file into their repositories and develop independently.
