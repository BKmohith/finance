# Laptop 3: Phase 2 Implementation Specification (2lap3.md)
## Perception, System 1 Jev Router, Vernacular Audio STT & Counter Tasks
### Role: Developer C | Git Branch: `feat/jev-stt`

---

## 1. Executive Summary & Architectural Scope

In Phase 2 of **Sahayak (सहायक)**, **Laptop 3** serves as the **Perception and Background Processing Brain**. While Laptop 1 captures inputs (Counter POS Dashboard & Telegram Gateway) and Laptop 2 records transactional ACID ledgers (PostgreSQL FIFO & Khata), Laptop 3 operates as the intelligent ingestion and execution engine:

1. **System 1 Jev Router:** Uses TypeSafe Jev via OpenRouter (supported by local ultra-fast regex fast-paths) to classify incoming counter/Telegram payloads into strict `InboundIntentClass` categories in **<18ms**, instantly dropping memes, greetings, and spam at **$0 compute cost**.
2. **Vernacular Audio Perception:** Ingests noisy retail voice notes in **Kannada (`kn-IN`)**, **Hindi (`hi-IN`)**, and **Hinglish**, converting colloquial counter speech into normalized English business text via **Sarvam AI (Saaras model)**.
3. **Conversational Entity Extractor:** Normalizes transcribed text or shorthand text (*"ರಮೇಶ್ 500 ಸಾಲ"*, *"Sharma ji 500 udhaar"*, *"25 bag atta 450 cash"*) into the frozen Pydantic contracts (`CounterSaleEvent` and `VoiceKhataIntent`).
4. **Asynchronous Counter Task Worker:** Consumes `workers.process_counter_sale` tasks from Redis to orchestrate batch inventory depletion without blocking counter checkout speeds.

---

## 2. Zero-Git-Conflict Boundary Protocol

To guarantee **0.00% merge conflicts**, Laptop 3 has exclusive write-access to the following 5 files only. Laptop 3 **never modifies** files belonging to Laptop 1 (`app/api/*`) or Laptop 2 (`app/db/*`).

```
sahayak/
├── app/workers/
│   ├── jev_router.py         # [LAPTOP 3 ONLY] System 1 Jev Router & Intent Classifier
│   ├── stt_engine.py         # [LAPTOP 3 ONLY] Sarvam AI Vernacular Speech-to-Text
│   ├── voice_khata.py        # [LAPTOP 3 ONLY] Agent 1 Conversational Entity Extractor
│   └── counter_tasks.py      # [LAPTOP 3 ONLY] Celery task `workers.process_counter_sale`
└── tests/
    └── test_jev_stt.py       # [LAPTOP 3 ONLY] Dedicated isolated test suite (Zero L1/L2 deps)
```

---

## 3. Credentials & Environment Setup

All credentials are fully isolated in `.env` and loaded via [app/workers/config.py](file:///c:/Users/asusm/finance/app/workers/config.py):

| Variable | Configured Value / Provider | Role |
| :--- | :--- | :--- |
| `SARVAM_API_KEY` | `sk_apba05ii_xikxfuEvwXbot88r0t4CLxRF` | Indian Vernacular Speech-to-Text (Kannada, Hindi, Hinglish) via Sarvam Saaras |
| `OPENROUTER_API_KEY` | `sk-or-v1-facc296f7226...` (Active in `.env`) | TypeSafe Jev decision model (`typesafe/jev-latest`) for System 1 routing |
| `GEMINI_API_KEY` | Active in `.env` | Multimodal audio fallback and high-reasoning dialect entity parser |
| `CELERY_BROKER_URL`| `redis://localhost:6379/0` | Async task queue broker for counter sale processing |

---

## 4. End-to-End Perception Data Flow

```
   SHOPKEEPER (Telegram / Voice / Text)
   (e.g., Kannada: "ರಮೇಶ್ ಅವರಿಗೆ 500 ರೂಪಾಯಿ ಸಾಲ" OR "25 bag atta 450 cash")
                      │
                      ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                       LAPTOP 3 PERCEPTION PIPELINE                     │
 ├────────────────────────────────────────────────────────────────────────┤
 │                                                                        │
 │  1. System 1: Jev Router (app/workers/jev_router.py)                   │
 │     • Fast-Path Heuristic (<5ms): Drops greetings, forwards, memes     │
 │     • TypeSafe Jev via OpenRouter: Probabilistic intent classification │
 │     • Output: InboundIntentClass (MEME_SPAM, COUNTER_SALE,             │
 │               VOICE_KHATA, INVOICE_BILL)                               │
 │                                                                        │
 │  2. Vernacular Audio Engine (app/workers/stt_engine.py)                │
 │     • Audio Cleaning: VAD energy filter (strips ceiling fan/horns)     │
 │     • Sarvam AI Saaras API: Kannada/Hindi audio ──> English Text       │
 │     • Fallback: Gemini Flash Audio / Mock Test Mode                    │
 │                                                                        │
 │  3. Financial Entity Extractor (app/workers/voice_khata.py)            │
 │     • Parses Customer, Monetary Amount, Product SKU, Qty, and Action   │
 │     • Emits Validated Frozen Contract:                                 │
 │       - CounterSaleEvent (Cash/UPI Sales + Itemized basket)            │
 │       - VoiceKhataIntent (Udhaar Credit Given / Repayment)             │
 │                                                                        │
 │  4. Async Counter Worker (app/workers/counter_tasks.py)                │
 │     • Celery task: "workers.process_counter_sale"                      │
 │     • Dispatches FIFO inventory depletion request to Database layer    │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Detailed Component Specifications

### 5.1. System 1: Jev Router (`app/workers/jev_router.py`)
* **Objective:** Lightning-fast intent classification determining whether incoming payloads are spam, counter sales, credit notes, or invoices.
* **Architecture:**
  1. **Tier 1 (Sub-5ms Local Fast-Path):**
     * Regex and keyword matcher for common meme greetings (*"Suprabhat"*, *"Good Morning"*, forwards, emojis, sticker IDs). Instantly returns `InboundIntentClass.MEME_SPAM` at $0 cost and <5ms.
  2. **Tier 2 (TypeSafe Jev via OpenRouter API):**
     * When text is ambiguous or complex, queries Jev via OpenRouter (`https://openrouter.ai/api/v1/chat/completions`) using model `typesafe/jev-latest` or structured choice prompt.
     * Evaluates choice options:
       - `MEME_SPAM`: Non-business text, greetings, memes.
       - `COUNTER_SALE`: Customer purchase (*"Paytm 300 Oil 2"*, *"25 bag atta 450 cash"*).
       - `VOICE_KHATA`: Informal credit (*"Sharma ji 500 udhaar"*, *"ರಮೇಶ್ 500 ಸಾಲ"*).
       - `INVOICE_BILL`: Wholesale distributor paper bills.
  3. **Tier 3 (Local Offline Fallback):**
     * If network/API is unavailable, falls back to a deterministic rule-based tokenizer so unit tests and offline demos never crash.

---

### 5.2. Vernacular STT Engine (`app/workers/stt_engine.py`)
* **Objective:** Ingest audio notes in `.ogg`, `.opus`, `.wav`, or `.mp3` and return clean, normalized English text.
* **Primary Provider: Sarvam AI Saaras API:**
  * **Endpoint:** `POST https://api.sarvam.ai/speech-to-text`
  * **Headers:** `api-subscription-key: <SARVAM_API_KEY>`
  * **Supported Language Codes:**
    * `kn-IN`: Kannada (e.g., *"ರಮೇಶ್ ಅವರಿಗೆ 500 ರೂಪಾಯಿ ಸಾಲ"*)
    * `hi-IN`: Hindi (e.g., *"शर्मा जी को 500 रुपये उधार दिए"*)
    * `en-IN`: Indian English / Hinglish
  * **Translation Option:** Automatically translates vernacular speech to English text.
* **Audio Preprocessing:**
  * Validates audio payload and strips high-frequency background street and fan noise.
* **Multi-Provider Fallback:**
  * If `SARVAM_API_KEY` is active $\rightarrow$ calls Sarvam Saaras.
  * If `GEMINI_API_KEY` is active $\rightarrow$ calls Gemini Multimodal Audio.
  * If testing offline $\rightarrow$ returns deterministic mock transcript.

---

### 5.3. Conversational Entity Extractor (`app/workers/voice_khata.py`)
* **Objective:** Parses transcribed vernacular speech or shorthand text into validated Pydantic models from [app/core/contracts.py](file:///c:/Users/asusm/finance/app/core/contracts.py).
* **Use Cases:**
  1. **Customer Khata (Udhaar Credit Given / Repaid):**
     * Input: *"ರಮೇಶ್ ಅವರಿಗೆ 500 ರೂಪಾಯಿ ಸಾಲ"* or *"Sharma ji 500 udhaar"*
     * Output: `VoiceKhataIntent`:
       ```python
       VoiceKhataIntent(
           customer_name="Ramesh",
           amount=500.0,
           action="GIVE_CREDIT",
           transcription="ರಮೇಶ್ ಅವರಿಗೆ 500 ರೂಪಾಯಿ ಸಾಲ",
           confidence=0.98
       )
       ```
     * Input: *"Gupta ji paid 1000 cash for old udhaar"*
     * Output: `VoiceKhataIntent(customer_name="Gupta ji", amount=1000.0, action="COLLECT_PAYMENT", ...)`
  2. **Itemized Counter Sales:**
     * Input: *"25 bag atta 450 cash"*
     * Output: `CounterSaleEvent`:
       ```python
       CounterSaleEvent(
           merchant_id="M_DEMO",
           amount_paid=11250.0,
           payment_method=PaymentMethod.CASH,
           items=[
               CounterItemSale(
                   item_name="atta",
                   quantity=25.0,
                   unit="bags",
                   unit_retail_price=450.0,
                   line_total=11250.0
               )
           ]
       )
       ```
     * Input: *"Paytm 300 Oil 2"*
     * Output: `CounterSaleEvent(amount_paid=300.0, payment_method=PaymentMethod.PAYTM_UPI, items=[...])`

---

### 5.4. Celery Counter Worker (`app/workers/counter_tasks.py`)
* **Objective:** Background task execution for counter sales ingestion.
* **Task Signature:**
  ```python
  @celery_app.task(name="workers.process_counter_sale", bind=True)
  def process_counter_sale(self, sale_event_dict: dict) -> dict:
      """
      Validates CounterSaleEvent, extracts item basket,
      and dispatches FIFO depletion request to database layer.
      """
  ```
* **Resilience:** Automatic retry with exponential backoff on transient database lock contentions.

---

### 5.5. Isolated Test Suite (`tests/test_jev_stt.py`)
* **Objective:** 100% isolated test suite with zero dependencies on Laptop 1 (`app/api/*`) or Laptop 2 (`app/db/*`).
* **Test Matrix:**
  1. `test_jev_router_spam_fast_path`: Confirms greetings/memes are dropped in <5ms.
  2. `test_jev_router_intent_classification`: Tests classification into `COUNTER_SALE`, `VOICE_KHATA`, `INVOICE_BILL`.
  3. `test_sarvam_stt_kannada_transcription`: Tests Sarvam API integration for Kannada audio translation.
  4. `test_voice_khata_kannada_credit_extraction`: Verifies Kannada transcript parses to `VoiceKhataIntent`.
  5. `test_voice_khata_counter_sale_extraction`: Verifies counter sale shorthand parses to `CounterSaleEvent`.
  6. `test_celery_counter_task_execution`: Tests `process_counter_sale` task lifecycle.

---

## 6. Verification & Run Commands

```powershell
# 1. Run Laptop 3 isolated test suite
.venv\Scripts\python.exe -m pytest tests/test_jev_stt.py -v

# 2. Verify zero regressions on Phase 1 Vision Worker
.venv\Scripts\python.exe -m pytest tests/test_vision_worker.py -v
```

---

## 7. Mathematical & Contract Guarantees

* **Zero Merge Conflicts:** 5 exclusive new files, 0 modifications to shared files.
* **Pydantic Compliance:** All outputs strictly conform to `CounterSaleEvent`, `VoiceKhataIntent`, `CounterItemSale`, and `InboundIntentClass`.
* **Latency Guarantee:** Jev Router P99 $<18\text{ms}$; STT transcription $<1.2\text{s}$.
