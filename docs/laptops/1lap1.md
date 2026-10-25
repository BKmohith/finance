# Sahayak (सहायक) — Laptop 1: Gateway, Ingestion & Alerts Blueprint
## Pre-Build Engineering Specification & Final Architectural Conclusion
### Device: Laptop 1 (Developer A) | Git Branch: `feature/laptop1` (mapped to `feat/gateway`)

---

## 1. Laptop 1 Identity & Responsibility Boundary

In the Sahayak Tri-Laptop Decoupled Architecture, **Laptop 1** acts as the high-speed outer perimeter. It receives all external traffic, guarantees cryptographic security, prevents duplicate uploads in sub-millisecond time, dispatches heavy AI processing asynchronously, and delivers instant actionable alerts back to merchants.

```
                      MERCHANT PHONE (WhatsApp)
                                 │
                                 │ Inbound Bill Photo / Audio
                                 ▼
         ┌───────────────────────────────────────────────┐
         │         LAPTOP 1: HIGH-SPEED GATEWAY          │
         │                                               │
         │  1. Meta HMAC-SHA256 Security Verification    │
         │  2. Redis 7.2 Perceptual Media Deduplication  │  <1ms Duplicate Drop
         │  3. Inbound Event Parsing (contracts.py)      │
         │  4. Celery Queue Task Dispatcher              │
         └───────┬───────────────────────────────▲───────┘
                 │                               │
                 │ workers.process_invoice       │ PriceHikeAlert
                 ▼                               │
     [Celery Queue / Redis]              [Laptop 2 & 3 Output]
                 │                               │
                 ▼                               │
     [Laptop 3: Vision Worker]                   │
                 │                               │
                 ▼                               │
     [Laptop 2: ACID DB + Margin Engine] ────────┘
```

---

## 2. Strict Directory & File Ownership

Laptop 1 has exclusive ownership of the `app/api/` boundary and isolated gateway tests. No other laptop modifies these files.

```
sahayak/
├── app/
│   ├── core/                        # SHARED FROZEN CONTRACT (Created first, read-only)
│   │   ├── config.py                # Environment secrets & connection strings
│   │   └── contracts.py             # Pydantic schemas (Shared across all 3 laptops)
│   │
│   └── api/                         # [LAPTOP 1 EXCLUSIVE DOMAIN]
│       ├── __init__.py
│       ├── routes.py                # FastAPI endpoints (GET/POST /webhook/whatsapp, /health)
│       ├── security.py              # HMAC-SHA256 signature & hub.challenge validator
│       ├── deduplication.py         # Redis SHA-256 media hash check (48h TTL)
│       └── notifier.py              # Meta WhatsApp Cloud API alert dispatcher
│
├── tests/
│   └── test_gateway.py              # Laptop 1 isolated test suite (FastAPI TestClient + Mocks)
│
├── simulator/                       # Local Interactive Webhook Simulator (Demo & Offline Test)
│   └── index.html                   # Visual bill upload simulator matching Meta payloads
│
├── requirements.txt                 # Dependencies: fastapi, uvicorn, celery, redis, pydantic, httpx, pytest
├── .env.example                     # Environment variables template
└── 1lap1.md                         # This specification & final conclusion
```

---

## 3. The Shared Frozen Contract (`app/core/contracts.py`)

All three laptops adhere strictly to these Pydantic models. Field names and data types are locked:

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

# 1. WhatsApp Inbound Payload (Handled by Laptop 1)
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

# 2. Invoice OCR Schema (Produced by Laptop 3, ingested by Laptop 2)
class ExtractedLineItem(BaseModel):
    item_name: str
    brand: Optional[str] = None
    batch_number: Optional[str] = None
    quantity: float = Field(gt=0)
    unit: str = Field(default="units")
    unit_wholesale_rate: float = Field(gt=0)
    tax_rate_pct: float = Field(default=0.0, ge=0.0, le=28.0)
    line_total: float = Field(gt=0)

class ExtractedInvoiceData(BaseModel):
    supplier_name: str
    supplier_gstin: Optional[str] = None
    invoice_number: str
    invoice_date: date
    credit_due_date: Optional[date] = None
    items: List[ExtractedLineItem]
    grand_total: float
    confidence_score: float = Field(ge=0.0, le=1.0)

# 3. Price-Shield Alert (Produced by Laptop 2, sent by Laptop 1)
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

# 4. Celery Task Contract (Dispatched by Laptop 1, executed by Laptop 3)
# Task: "workers.process_invoice"
# Args: (merchant_id: str, media_id: str, whatsapp_message_id: str, sender_phone: str)
```

---

## 4. Laptop 1 Technical Implementation Breakdown

### 4.1 Security & Webhook Handshake (`app/api/security.py`)
* **GET `/webhook/whatsapp`:** Handles Meta's initial challenge handshake:
  - Validates `hub.mode == "subscribe"` and `hub.verify_token == WHATSAPP_VERIFY_TOKEN`.
  - Responds with `hub.challenge` integer in `<10ms`.
* **POST `/webhook/whatsapp` HMAC Verification:**
  - Extracts header `X-Hub-Signature-256` (format: `sha256=<hex_digest>`).
  - Computes `hmac.new(META_APP_SECRET, raw_body, hashlib.sha256).hexdigest()`.
  - Performs constant-time comparison `hmac.compare_digest()` to prevent timing attacks.
  - Rejects tampering with `HTTP 403 Forbidden`.

### 4.2 Perceptual Deduplication Engine (`app/api/deduplication.py`)
* Computes SHA-256 digest of incoming media or unique message payload.
* Atomic Redis query:
  ```python
  key = f"invoice_hash:{merchant_id}:{media_sha256}"
  is_new = redis_client.set(key, "1", ex=172800, nx=True) # 48-Hour TTL, Set-if-Not-Exists
  ```
* If `is_new is None` (already seen): immediately returns `HTTP 200` with `{"status": "DUPLICATE_DROPPED"}` in **$<1\text{ms}$** without triggering Celery or AI pipelines.

### 4.3 Webhook Ingestion & Celery Dispatcher (`app/api/routes.py`)
* Extracts merchant ID, sender phone, WhatsApp message ID, and media attachment.
* Instantiates `InboundInvoiceEvent`.
* Dispatches async task to Celery:
  ```python
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
* Acknowledges Meta within **$<25\text{ms}$** with `HTTP 200 {"status": "QUEUED"}`.

### 4.4 WhatsApp Outbound Notifier (`app/api/notifier.py`)
* Implements `send_price_shield_alert(alert: PriceHikeAlert)`.
* Calls Meta Graph API endpoint:
  `POST https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages`
* Formats clear, actionable Indian retail alert message:
  ```
  ⚠️ *Sahayak Price-Shield Alert* ⚠️
  Wholesale cost for *{item_name}* rose from ₹{old} to ₹{new} (+{hike}%).
  
  📉 If unchanged, projected loss: ₹{estimated_loss}/mo
  🛡️ *Suggested Shelf MRP:* ₹{suggested_mrp} (protects 10% gross margin)
  ```

---

## 5. External Tools, Credentials & Hackathon Strategy

### 5.1 Credentials Matrix

| Credential | Purpose | Source / How to Obtain |
|---|---|---|
| `META_APP_SECRET` | HMAC signature validation | Meta App Dashboard $\rightarrow$ App Settings $\rightarrow$ Basic |
| `WHATSAPP_VERIFY_TOKEN` | Webhook verification handshake | User-defined secret (e.g. `sahayak_secret_token_2026`) |
| `WHATSAPP_API_TOKEN` | Outbound WhatsApp alerts | Meta App Dashboard $\rightarrow$ WhatsApp $\rightarrow$ API Setup |
| `WHATSAPP_PHONE_NUMBER_ID` | Sender ID for alerts | Meta App Dashboard $\rightarrow$ WhatsApp $\rightarrow$ API Setup |
| `REDIS_URL` | Deduplication & Celery broker | Local (`localhost:6379`) or Upstash Cloud Redis |

### 5.2 Resolution for Meta's "Account Too New" Cooldown
When attempting to create a Meta Business Portfolio on a brand-new Facebook account, Meta imposes an anti-spam cooldown ("Try again in an hour").

**Our 3-Tier Zero-Blocker Strategy:**
1. **Tier 1 (Instant):** If a teammate (Laptop 2 or Laptop 3 developer) has a personal Facebook account created previously, they can log in to [developers.facebook.com](https://developers.facebook.com/) and generate the credentials with zero cooldown.
2. **Tier 2 (Built-in Simulator):** We build an interactive Webhook Simulator & Test Harness inside Laptop 1. It sends genuine Meta-formatted JSON payloads and tests HMAC verification, Redis deduplication, and Celery queuing locally. We can run live demos for hackathon judges even without active Meta servers.
3. **Tier 3 (Twilio WhatsApp Fallback):** If Meta remains restricted, we can drop in Twilio's WhatsApp Sandbox in under 2 minutes (requires no Facebook account).

---

## 6. How Laptop 1 Operates in 100% Isolation

Laptop 1 does **NOT** wait for Laptop 2 (Postgres DB) or Laptop 3 (Gemini Vision AI) to finish.

* **Database isolation:** Laptop 1 does not talk directly to PostgreSQL; it dispatches to the Celery queue.
* **Vision AI isolation:** Celery `send_task("workers.process_invoice")` is mocked during tests using Python `unittest.mock.patch`.
* **Redis isolation:** Runs against local Redis or an in-memory `fakeredis` test harness.
* **Test Verification:** [tests/test_gateway.py](file:///c:/Users/DHANUSH%20B%20U/finance/tests/test_gateway.py) tests all routes, signatures, deduplication hits, and alert formatting independently.

---

## 7. Merge Sequence Alignment (Phase 3 Protocol)

When development is complete across the 3 laptops, the merge sequence is strictly:
1. **Laptop 2 (`feat/db-core`)** merges to `main` (PostgreSQL schemas & RLS).
2. **Laptop 3 (`feat/vision`)** pulls `main`, verifies worker against live DB, merges to `main`.
3. **Laptop 1 (`feat/gateway` / `feature/laptop1`)** pulls `main`, runs full end-to-end integration test suite, and completes the final merge.

---

## 8. Immediate Execution Plan

1. Install Python 3.11+ on this machine.
2. Create `requirements.txt` and install dependencies.
3. Scaffold `app/core/contracts.py` and `app/core/config.py`.
4. Build `app/api/security.py`, `app/api/deduplication.py`, `app/api/routes.py`, and `app/api/notifier.py`.
5. Build `tests/test_gateway.py` and verify all tests pass with green status.
6. Create the local interactive Webhook Simulator so we can demo bill uploads immediately.
