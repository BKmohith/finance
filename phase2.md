# Sahayak (सहायक) — Phase 2 Multi-Device Implementation Plan
## Tri-Laptop Decoupled Engineering Blueprint (Zero-Git-Conflict Architecture)
### Target Milestone: Phase 2 — Inflow Rails, Customer Khata & Concurrency-Safe FIFO

---

## 1. Executive Problem Statement & Architectural Pivot

### The Payment-Basket Attribution Gap (Why Soundbox SDK Is Replaced)
In retail kirana operations, when a customer scans a merchant's Paytm QR code and pays ₹300, a standard payment soundbox or UPI webhook only emits monetary metadata:
$$\text{Payload} = \{\text{amount}: ₹300.00, \text{mode}: \text{"UPI"}, \text{timestamp}: t\}$$

**The Missing Link:** A raw payment notification contains **zero basket data**. It does not know whether the customer bought 2 bottles of cooking oil, 5 kg of flour, or paid off previous store credit (*Udhaar*). Without knowing the SKUs purchased:
1. **Agent 4 (FIFO Inventory Depletion)** cannot identify which batch rows to lock or decrement.
2. Proprietary hardware Soundbox MQTT brokers and regional device firmware SDKs introduce closed hardware locks and complex mock environments without solving this fundamental basket-attribution problem.

### The Architectural Decision: Dual Practical Ingestion Touchpoints
Instead of physical Soundbox MQTT SDKs, Phase 2 implements two high-speed, friction-free counter touchpoints while keeping the **Core Decision Engine (System 1 / Jev Engine + ACID Core) 100% untouched**:

```
 ┌────────────────────────────────────┐     ┌────────────────────────────────────┐
 │     TOUCHPOINT 1: DASHBOARD        │     │     TOUCHPOINT 2: TELEGRAM BOT     │
 │  • Quick-tap Counter POS UI        │     │  • Shorthand: "Paytm 300 Oil 2"    │
 │  • Amount + Payment Mode + SKUs    │     │  • Vernacular Voice Note:          │
 │  • Direct browser/tablet entry     │     │    "Paytm pe 300 aaya, 2 tel diya" │
 └─────────────────┬──────────────────┘     └─────────────────┬──────────────────┘
                   │                                          │
                   ▼                                          ▼
           [FastAPI Gateway]                         [Telegram Ingestion]
        POST /api/counter/sale                      POST /webhook/telegram
                   │                                          │
                   └────────────────────┬─────────────────────┘
                                        │
                                        ▼
                     ┌──────────────────────────────────────┐
                     │       SYSTEM 1: JEV ROUTER           │ ◄── CORE DECISION ENGINE
                     │   (<18ms Sub-LLM Intent Classifier)  │     (UNTOUCHED & PRESERVED)
                     └──────────────────┬───────────────────┘
                                        │ Normalizes to CounterSaleEvent
                                        ▼
                     ┌──────────────────────────────────────┐
                     │     MULTI-AGENT FABRIC & ACID CORE   │
                     ├──────────────────────────────────────┤
                     │ 1. ACID Cash Ledger (+₹300 Cash/UPI) │
                     │ 2. Agent 4: FIFO Inventory Depletion │
                     │ 3. Agent 1: Customer Khata (Udhaar)  │
                     │ 4. Agent 5: Real-Time Cash Forecast  │
                     └──────────────────────────────────────┘
```

---

## 2. Zero-Git-Conflict Architecture (Mathematical Guarantee)

To guarantee **0.00% merge conflicts** across 3 laptops developing simultaneously, Phase 2 implements the **Disjoint File & Pluggable Module Protocol**.

### The 4 Laws of Zero Merge Conflict
1. **The Shared Contract Law (Pre-Branch Commit):**  
   The Phase 2 schema extensions in `app/core/contracts.py` are committed to `main` **before any developer cuts a branch**. Once committed, this file is frozen. No laptop modifies it during Phase 2.
2. **The New-File-Only Rule (Zero Overlapping Files):**  
   Every laptop works **exclusively inside new, dedicated files**. No developer edits another developer's files, and no developer modifies shared Phase 1 files (`routes.py`, `models.py`, `tasks.py`).
3. **Pluggable Architecture (Zero Edits to `main.py`):**  
   Laptop 1 defines a self-contained `counter_router` in `app/api/counter.py`. In `main.py`, a single pre-committed dynamic import mounts it cleanly:
   ```python
   # Pre-committed on main before branching:
   try:
       from app.api.counter import counter_router
       app.include_router(counter_router)
   except ImportError:
       pass
   ```
4. **Isolated Test Suites:**  
   Each laptop owns its dedicated test file in `tests/`. No shared test files exist.

```
                                  ┌────────────────────────────────────────┐
                                  │   PRE-COMMITTED FROZEN CONTRACT        │
                                  │     (app/core/contracts.py)            │
                                  │   Committed to `main` before branching │
                                  └───────────────────┬────────────────────┘
                                                      │
         ┌────────────────────────────────────────────┼────────────────────────────────────────────┐
         ▼                                            ▼                                            ▼
┌───────────────────────────────────────┐ ┌───────────────────────────────────────┐ ┌───────────────────────────────────────┐
│          LAPTOP 1 (Dev A)             │ │          LAPTOP 2 (Dev B)             │ │          LAPTOP 3 (Dev C)             │
│       Branch: `feat/counter`          │ │       Branch: `feat/khata-db`         │ │       Branch: `feat/jev-stt`          │
│                                       │ │                                       │ │                                       │
│  EXCLUSIVE NEW FILES:                 │ │  EXCLUSIVE NEW FILES:                 │ │  EXCLUSIVE NEW FILES:                 │
│  • app/api/counter.py                 │ │  • app/db/khata_models.py             │ │  • app/workers/jev_router.py          │
│  • app/api/counter_notifier.py        │ │  • app/db/fifo_engine.py              │ │  • app/workers/stt_engine.py          │
│  • simulator/counter.html             │ │  • app/db/khata_repository.py         │ │  • app/workers/voice_khata.py         │
│  • tests/test_counter_gateway.py      │ │  • tests/test_khata_fifo_rls.py       │ │  • app/workers/counter_tasks.py       │
│                                       │ │                                       │ │  • tests/test_jev_stt.py              │
│  TOUCHES ZERO L2 / L3 FILES           │ │  TOUCHES ZERO L1 / L3 FILES           │ │  TOUCHES ZERO L1 / L2 FILES           │
└───────────────────────────────────────┘ └───────────────────────────────────────┘ └───────────────────────────────────────┘
```

### Complete Disjoint File Map (DFM)

```
sahayak/
├── app/
│   ├── core/                        # [FROZEN CONTRACT] Pre-committed to main
│   │   ├── config.py
│   │   └── contracts.py             # Phase 2 models committed before branching
│   │
│   ├── api/                         # [LAPTOP 1 DOMAIN ONLY]
│   │   ├── counter.py               # NEW: Counter POS endpoints (POST /api/counter/sale)
│   │   └── counter_notifier.py      # NEW: Merchant ACK & Customer Khata digital receipts
│   │
│   ├── db/                          # [LAPTOP 2 DOMAIN ONLY]
│   │   ├── khata_models.py          # NEW: CustomerKhata, InventoryBatch, CashTransaction
│   │   ├── fifo_engine.py           # NEW: Concurrency-safe row-locked batch depletion
│   │   └── khata_repository.py      # NEW: Khata balance updates & cash inflow writes
│   │
│   └── workers/                     # [LAPTOP 3 DOMAIN ONLY]
│       ├── jev_router.py            # NEW: System 1 ONNX / fast text router (<18ms)
│       ├── stt_engine.py            # NEW: Vernacular audio-to-text (Sarvam/Whisper)
│       ├── voice_khata.py           # NEW: Agent 1 credit note entity extractor
│       └── counter_tasks.py         # NEW: Celery/Redis stream counter worker tasks
│
├── simulator/                       # [LAPTOP 1 DOMAIN ONLY]
│   └── counter.html                 # NEW: Touch-friendly Kirana Counter POS Web UI
│
└── tests/                           # [ISOLATED TEST FILES]
    ├── test_counter_gateway.py      # LAPTOP 1 ONLY
    ├── test_khata_fifo_rls.py       # LAPTOP 2 ONLY
    └── test_jev_stt.py              # LAPTOP 3 ONLY
```

---

## 3. The Shared Frozen Contract (`app/core/contracts.py`)

> **EXECUTION NOTICE:**  
> This block is committed to `main` **before** creating feature branches. Once on `main`, all 3 developers pull `main` and code strictly to these schemas.

```python
"""
app/core/contracts.py — Phase 2 Shared Frozen Models
"""
from enum import Enum
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel, Field


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


# --- 1. Normalized Counter Sale Contract (Emitted by Laptop 1, Ingested by L2 & L3) ---
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


# --- 2. Voice Khata Inbound Contract (Produced by Laptop 3, Dispatched by Laptop 1) ---
class VoiceKhataIntent(BaseModel):
    customer_name: str
    amount: float = Field(gt=0)
    action: str = Field(description="GIVE_CREDIT (Udhaar diya) or COLLECT_PAYMENT (Udhaar chukaya)")
    transcription: str
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


# --- 3. FIFO Depletion Task Payload (Processed by Laptop 2) ---
class FIFODepletionRequest(BaseModel):
    merchant_id: str
    sale_id: str
    items: List[CounterItemSale]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- 4. System 1 (Jev Router) Payload Classification ---
class InboundIntentClass(str, Enum):
    MEME_SPAM = "MEME_SPAM"             # Drop in <18ms ($0)
    COUNTER_SALE = "COUNTER_SALE"       # Process sale + FIFO depletion
    VOICE_KHATA = "VOICE_KHATA"         # Agent 1 customer credit update
    INVOICE_BILL = "INVOICE_BILL"       # Phase 1 wholesale bill OCR


# Celery Task Name for Phase 2 Counter Ingestion
CELERY_COUNTER_TASK_NAME = "workers.process_counter_sale"
```

---

## 4. Laptop 1: Gateway, Touchpoints & Alerts Engineer

### Developer A | Git Branch: `feat/counter`

### Exclusive File Assignments
* `app/api/counter.py`
* `app/api/counter_notifier.py`
* `simulator/counter.html`
* `tests/test_counter_gateway.py`

### Implementation Steps

1. **Dashboard Counter POS API (`app/api/counter.py`):**
   * Creates isolated `counter_router = APIRouter(prefix="/api/counter", tags=["Counter POS"])`.
   * Endpoint `POST /api/counter/sale`:
     * Validates inbound `CounterSaleEvent`.
     * Logs cash inflow via `app/db/khata_repository.py` (or mocked repository in test).
     * Enqueues `CELERY_COUNTER_TASK_NAME` for background FIFO inventory depletion.
     * Responds in $<40\text{ms}$ with transaction confirmation.
2. **Customer Khata Notifier (`app/api/counter_notifier.py`):**
   * Dispatches instant digital receipts to customer Telegram/WhatsApp when credit (*Udhaar*) is given:
     *`"Namaste Sharma ji, Ramesh Kirana par aapka ₹500 udhaar darj hua. Kul baaki: ₹1,200."`*
3. **Kirana Touch Counter UI (`simulator/counter.html`):**
   * Responsive web UI for mobile/tablet counter:
     * Quick amount buttons (₹50, ₹100, ₹200, ₹500, Custom).
     * Payment mode selector (Paytm QR / Cash / Khata).
     * Item search with instant autocomplete & quantity incrementors.
     * Single-click **"Complete Sale & Deplete Stock"** action.

### Isolated Testing (Zero Dependency on L2/L3)
```bash
# Laptop 1 runs its test in isolation:
pytest tests/test_counter_gateway.py -v
```

---

## 5. Laptop 2: ACID Core, Customer Khata & FIFO DB Engineer

### Developer B | Git Branch: `feat/khata-db`

### Exclusive File Assignments
* `app/db/khata_models.py`
* `app/db/fifo_engine.py`
* `app/db/khata_repository.py`
* `tests/test_khata_fifo_rls.py`

### Implementation Steps

1. **Phase 2 Models (`app/db/khata_models.py`):**
   * `CashTransaction`: Inflow records (`merchant_id`, `amount`, `payment_method`, `created_at`).
   * `CustomerKhata`: Store credit balance (`merchant_id`, `customer_name`, `customer_phone`, `current_balance`).
   * `InventoryBatch`: Stock batches with expiry (`merchant_id`, `item_name`, `batch_number`, `quantity_remaining`, `cost_price`, `expiry_date`).
2. **Concurrency-Safe FIFO Depletion (`app/db/fifo_engine.py`):**
   * Uses PostgreSQL row-level locks (`SELECT ... FOR UPDATE`) to guarantee zero negative stock and no race conditions:
   ```python
   def deplete_inventory_fifo(session, merchant_id: str, item_name: str, quantity: float):
       batches = session.execute(
           select(InventoryBatch)
           .where(
               and_(
                   InventoryBatch.merchant_id == merchant_id,
                   func.lower(InventoryBatch.item_name) == func.lower(item_name),
                   InventoryBatch.quantity_remaining > 0
               )
           )
           .order_by(InventoryBatch.expiry_date.asc().nulls_last(), InventoryBatch.created_at.asc())
           .with_for_update()
       ).scalars().all()
       # Depletes oldest batches first...
   ```
3. **Khata Repository (`app/db/khata_repository.py`):**
   * Atomically commits cash inflows, updates customer credit ledgers, and logs audit entries within RLS session boundaries.

### Isolated Testing (Zero Dependency on L1/L3)
```bash
# Laptop 2 verifies RLS and row-locking in isolation:
pytest tests/test_khata_fifo_rls.py -v
```

---

## 6. Laptop 3: Perception, Jev Engine & Audio STT Engineer

### Developer C | Git Branch: `feat/jev-stt`

### Exclusive File Assignments
* `app/workers/jev_router.py`
* `app/workers/stt_engine.py`
* `app/workers/voice_khata.py`
* `app/workers/counter_tasks.py`
* `tests/test_jev_stt.py`

### Implementation Steps

1. **System 1: Jev Reflex Router (`app/workers/jev_router.py`):**
   * High-speed CPU intent classifier running in $<18\text{ms}$.
   * Classifies inbound text/audio into:
     * `MEME_SPAM` $\rightarrow$ Drop immediately ($0 cost).
     * `COUNTER_SALE` $\rightarrow$ Forward to `counter_tasks.py`.
     * `VOICE_KHATA` $\rightarrow$ Forward to `voice_khata.py`.
     * `INVOICE_BILL` $\rightarrow$ Forward to Phase 1 OCR pipeline.
2. **Vernacular Speech-to-Text (`app/workers/stt_engine.py`):**
   * Ingests audio notes from Telegram/WhatsApp (Hinglish/Hindi/Regional).
   * Applies Silero VAD noise reduction to remove kirana background sounds.
   * Transcribes speech via Sarvam AI / Whisper in $<800\text{ms}$.
3. **Entity Extraction (`app/workers/voice_khata.py`):**
   * Extracts customer names, monetary amounts, and items from conversational text.
   * Emits validated `CounterSaleEvent` or `VoiceKhataIntent`.
4. **Celery Counter Worker (`app/workers/counter_tasks.py`):**
   * Implements `workers.process_counter_sale` consuming tasks and calling `deplete_inventory_fifo`.

### Isolated Testing (Zero Dependency on L1/L2)
```bash
# Laptop 3 tests Jev router speed & STT extraction in isolation:
pytest tests/test_jev_stt.py -v
```

---

## 7. Zero-Conflict Git Workflow & Merge Sequence

### Step 0: Pre-Branch Contract Freeze (One Developer Executes on `main`)
```bash
# Commit the frozen contracts.py changes to main
git checkout main
git pull origin main
git add app/core/contracts.py
git commit -m "chore(contracts): freeze phase 2 data contracts"
git push origin main
```

### Daily Routine for Each Laptop
```bash
# Before coding each day:
git checkout <your-branch>
git fetch origin
git pull --rebase origin main

# Stage and commit ONLY your assigned files:
git add app/<your-assigned-domain>/
git add tests/<your-assigned-test>.py
git commit -m "feat(domain): description of feature"
git push -u origin <your-branch>
```

---

### The Strict 3-Step Merge Sequence

```
   STEP 1: Merge Laptop 2 (`feat/khata-db`) First
           • Laptop 2 creates DB tables and FIFO logic.
           • Merges into `main` and pushes.
           │
           ▼
   STEP 2: Laptop 3 Rebase & Merge (`feat/jev-stt`) Second
           • Laptop 3 runs: git pull --rebase origin main
           • Tests worker against live DB models.
           • Merges into `main` and pushes.
           │
           ▼
   STEP 3: Laptop 1 Rebase & Merge (`feat/counter`) Third
           • Laptop 1 runs: git pull --rebase origin main
           • Mounts counter_router in main.py.
           • Merges into `main` and pushes.
           │
           ▼
   STEP 4: Run Unified Test Suite on `main`
```

### Complete Verification Command
```bash
pytest tests/test_counter_gateway.py tests/test_khata_fifo_rls.py tests/test_jev_stt.py -v
```

---

## 8. Summary Comparison: Why This Guarantees Zero Merge Conflicts

| Dimension | Typical Risky Setup | Sahayak Zero-Conflict Architecture |
| :--- | :--- | :--- |
| **File Overlap** | Multiple devs editing `routes.py` & `models.py` | **100% Disjoint Files:** Each dev works in distinct, dedicated files. |
| **Contracts** | Edited on the fly during dev | **Frozen Pre-Branch:** Committed to `main` before any branch is cut. |
| **Routing** | Everyone editing `main.py` | **Self-Contained APIRouter:** Mounted via clean pluggable import. |
| **Testing** | Shared monolithic test files | **Isolated Test Suites:** Dev A, B, and C have dedicated test files. |
| **Merge Order** | Random simultaneous PR merges | **Deterministic Sequence:** DB Core (L2) ➔ Worker (L3) ➔ Gateway (L1). |
