# Sahayak (सहायक) — Laptop 3 Execution Blueprint & Setup
## Role: Vision AI, OpenCV Preprocessing & OCR Guardrails Engineer
**Branch:** `feat/vision` (or `feat/laptop3`)  
**Parent Plan Reference:** `phase1.md` (Section 5 & Section 7)  
**Status:** ✅ Fully Implemented, Configured & Independently Tested

---

## 1. Executive Summary & Objective

As **Laptop 3 (Developer C)**, our role is to build the **high-precision visual invoice extraction engine** for Sahayak Phase 1. 

Indian wholesale bills in Kirana stores present challenging visual conditions:
- Dot-matrix typography with fading ribbons.
- Wrinkles, perspective distortions, and uneven shop lighting.
- Diverse formatting across hundreds of regional distributors.

Laptop 3 converts noisy bill images into **strictly validated, structured Pydantic data** (`ExtractedInvoiceData`) with deterministic arithmetic verification before handing off to Laptop 2 (PostgreSQL Data Core) and Laptop 1 (WhatsApp Alerts).

---

## 2. External Credentials & Environment Configuration

| Tool / Service | Purpose | Destination | Status |
| :--- | :--- | :--- | :--- |
| **Google AI Studio** | Gemini 2.5 Flash Structured Vision OCR | `.env` (`GEMINI_API_KEY`) | ✅ Configured |

> **Zero Merge Conflict Guarantee:**  
> Laptop 3 **does not** require Meta WhatsApp API credentials or live PostgreSQL database access. Laptop 1 owns Meta WhatsApp, and Laptop 2 owns PostgreSQL. Laptop 3 develops, tests, and validates 100% independently using mocks and contract compliance.

---

## 3. Strict Codebase Ownership & Created Files

```text
finance/
├── .env                          # Local credentials (GEMINI_API_KEY configured)
├── .env.example                  # Template configuration
├── .gitignore                    # Safeguards secrets, caches, and test artifacts
├── requirements-worker.txt       # Isolated worker dependencies
├── pytest.ini                    # Pytest testpath & pythonpath config
├── 1lap3.md                      # This architecture & status document
│
├── app/
│   └── workers/                  # 👈 [LAPTOP 3 EXCLUSIVE DOMAIN - ZERO MERGE CONFLICT]
│       ├── __init__.py
│       ├── config.py             # Dedicated Worker settings (Gemini API key, model, Celery broker)
│       ├── contracts.py          # Worker Pydantic contracts & schemas (ExtractedInvoiceData, etc.)
│       ├── preprocessor.py       # OpenCV contrast, CLAHE, bilateral filtering, deskewing
│       ├── gemini_extractor.py   # Gemini Flash Vision OCR (via google-genai)
│       ├── guardrails.py         # Arithmetic & mathematical integrity validator
│       └── tasks.py              # Celery task ("workers.process_invoice") orchestrating pipeline
│
└── tests/
    ├── fixtures/bills/           # Synthetic realistic Indian bill images (clean & skewed)
    └── test_vision_worker.py     # Independent unit & integration test suite
```

---

## 4. Architectural Components Built

### Component 1: OpenCV Image Preprocessor (`app/workers/preprocessor.py`)
- **Bilateral Filtering (`cv2.bilateralFilter`)**: Suppresses dot-matrix printer noise and paper grain while preserving font edge contours.
- **CLAHE (`cv2.createCLAHE`)**: Balances harsh shadows and uneven tube light illumination.
- **Auto-Deskewing (Hough Line Transform)**: Detects skew angles and straightens tilted phone photos.

### Component 2: Gemini Flash Structured Vision OCR (`app/workers/gemini_extractor.py`)
- Powered by the official `google-genai` Python SDK.
- Enforces strict schema conformity to `ExtractedInvoiceData`.
- Schema sanitizer (`_sanitize_schema_for_genai`) translates Pydantic v2 `exclusiveMinimum` into OpenAPI 3.0 `minimum` constraints, eliminating SDK type and schema validation issues.

### Component 3: Arithmetic Guardrails & Sanity Checker (`app/workers/guardrails.py`)
- Deterministic mathematical double-check:
  - **Line Item Check:** $|\text{quantity} \times \text{unit\_wholesale\_rate} - \text{line\_total}| \le 1.0$
  - **Grand Total Check:** $|\sum \text{line\_total} - \text{grand\_total}| \le 2.0$
- Discrepancies raise `GuardrailValidationError` to ensure unverified AI math is never written to financial ledgers.

### Component 4: Celery Worker Task Pipeline (`app/workers/tasks.py`)
- Task signature: `workers.process_invoice(merchant_id: str, media_id: str, whatsapp_message_id: str, sender_phone: str)`
- Pipeline execution: Fetch Media $\rightarrow$ OpenCV Preprocessing $\rightarrow$ Gemini OCR $\rightarrow$ Arithmetic Guardrails $\rightarrow$ DB Repository Handoff.
- Features graceful fallbacks so Laptop 3 runs in standalone offline mode before Laptop 1 and Laptop 2 are merged.

---

## 5. Verification Commands

Run the Laptop 3 test suite:
```bash
pytest tests/test_vision_worker.py -v
```
