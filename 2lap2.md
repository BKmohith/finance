# Sahayak (सहायक) — Laptop 2: ACID Core, Customer Khata & FIFO Inventory Engine
## Phase 2 Implementation Blueprint & Final Architectural Specification
### Device: Laptop 2 (Developer B) | Git Branch: `feat/khata-db` | Milestone: Phase 2

---

## 1. System Identity & Mission Statement

* **Device Identity:** Laptop 2 (Developer B)
* **Git Branch:** `feat/khata-db`
* **Target Database:** Supabase PostgreSQL 16 (Session Pooler on Port 5432 with active Row-Level Security)
* **Host URL:** `aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres`
* **Domain Ownership:** The Deterministic ACID Financial Core & Inventory Engine.
* **Mission:** In Phase 2, Laptop 2 builds the transactional foundation for retail inflows:
  1. The **Customer Khata (*Udhaar*) Ledger** (tracking credit given and repayments collected).
  2. The **Double-Entry Cash Ledger** (settled cash and Paytm UPI inflows).
  3. The **Concurrency-Safe FIFO Inventory Depletion Engine** (Agent 4) with row-level locks (`SELECT ... FOR UPDATE`) to guarantee zero negative stock and no race conditions during rush hours.

---

## 2. Phase 2 Tri-Laptop Decoupled Inflow Dataflow

Laptop 2 is the central transactional anchor. Laptop 1 (Gateway & POS) and Laptop 3 (System 1 Jev & STT) plug directly into Laptop 2's models and repository functions:

```
  [LAPTOP 1: TOUCHPOINTS]            [LAPTOP 3: JEV & STT]              [LAPTOP 2: YOU / DATA CORE]
  Dashboard POS / Telegram Bot       System 1 Router + Speech STT        Supabase PostgreSQL 16 + RLS
  
  Merchant logs counter sale         Classifies intent in <18ms          Atomic ACID Inflow Commit
  or sends voice: "Sharma 500"       Transcribes & extracts entities                 │
             │                                     │                                 │
             ▼                                     ▼                                 ▼
  Emits: CounterSaleEvent            Emits: VoiceKhataIntent             1. Commits CashTransaction (+₹300)
             │                                     │                     2. Updates CustomerKhata (Udhaar)
             └───────────────────┬─────────────────┘                     3. Agent 4: FIFO Row-Locked Depletion
                                 │                                          (SELECT ... FOR UPDATE)
                                 ▼                                                   │
  Customer Digital Receipt <─────────────────────────────────────────────────────────┘
  "₹500 Udhaar darj hua"
```

---

## 3. Strict Directory & File Ownership (Zero Git Conflict Guarantee)

To guarantee **0.00% merge conflicts**, Laptop 2 develops in **100% brand-new, isolated files**. Laptop 2 never touches Phase 1 files (`routes.py`, `models.py`, `tasks.py`, or `main.py`):

```
sahayak/
├── app/
│   ├── core/
│   │   └── contracts.py             <-- FROZEN CONTRACT (Pre-committed to main, READ-ONLY)
│   │
│   └── db/                          <-- [LAPTOP 2 EXCLUSIVE DOMAIN]
│       ├── khata_models.py          # NEW: CustomerKhata, InventoryBatch, CashTransaction ORM
│       ├── fifo_engine.py           # NEW: Concurrency-safe FIFO row-locked batch depletion
│       └── khata_repository.py      # NEW: Atomic ACID operations for Khata & counter inflows
│
└── tests/
    └── test_khata_fifo_rls.py       # NEW: Laptop 2 isolated multi-tenant & FIFO test suite
```

---

## 4. External Tools & Logins Assessment

| Tool / Service | Required for Laptop 2? | Status / Action Needed |
| :--- | :---: | :--- |
| **Supabase PostgreSQL 16** | **YES** | **Ready & Active:** Connection string is live in `.env` and verified. |
| **Google Gemini API Key** | **NO** | Owned exclusively by Laptop 3 (Perception / Vision). |
| **Sarvam / Whisper STT** | **NO** | Owned exclusively by Laptop 3 (Speech-to-Text). |
| **Telegram Bot Token** | **NO** | Owned exclusively by Laptop 1 (Telegram bot polling). |
| **Meta WhatsApp Token** | **NO** | Owned exclusively by Laptop 1 (WhatsApp webhook). |
| **Redis / Celery** | **NO** (Mocked in test) | Laptop 2 tests purely in PostgreSQL with SQLAlchemy transactions. |

> **Conclusion for User:** **Zero new logins or paid API keys are required for Laptop 2.** Everything needed is already in the repository and `.env`.

---

## 5. Architectural Blueprint of Laptop 2 Modules

### A. SQLAlchemy 2.0 ORM Schema (`app/db/khata_models.py`)

Laptop 2 creates 3 new tables inheriting from `app.db.session.Base`:

```python
"""
app/db/khata_models.py
Phase 2 Inflow, Customer Khata & Inventory Batch Tables.
"""
import uuid
from datetime import datetime, date
from sqlalchemy import Column, String, Float, Integer, Date, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.db.session import Base

def generate_uuid():
    return str(uuid.uuid4())


class CashTransaction(Base):
    """
    Settled liquid cash & UPI counter inflows (e.g. +₹300 on Paytm QR).
    """
    __tablename__ = "cash_transactions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(64), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(32), default="PAYTM_UPI", nullable=False)  # PAYTM_UPI, CASH, SPLIT
    reference = Column(String(64), nullable=True)  # Optional UPI UTR / Txn Ref
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_cash_merchant_time", "merchant_id", "created_at"),
    )


class CustomerKhata(Base):
    """
    Customer credit ledger (Udhaar Baaki).
    Positive balance = Store Receivable (Customer owes money to merchant).
    """
    __tablename__ = "customer_khata"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(64), nullable=False, index=True)
    customer_name = Column(String(128), nullable=False)
    customer_phone = Column(String(20), nullable=True, index=True)
    current_balance = Column(Float, default=0.0, nullable=False)
    last_transaction_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_khata_merchant_customer", "merchant_id", "customer_name"),
    )


class InventoryBatch(Base):
    """
    Stock batches populated from Phase 1 supplier invoices.
    Depleted oldest-first by Agent 4 (FIFO).
    """
    __tablename__ = "inventory_batches"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    merchant_id = Column(String(64), nullable=False, index=True)
    item_name = Column(String(128), nullable=False, index=True)
    batch_number = Column(String(64), nullable=True)
    quantity_remaining = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=False)
    expiry_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_inventory_fifo_lookup", "merchant_id", "item_name", "expiry_date", "created_at"),
    )
```

### B. Agent 4: Concurrency-Safe FIFO Inventory Engine (`app/db/fifo_engine.py`)

Executes batch depletion with **PostgreSQL row-level locks** to eliminate checkout race conditions:

```python
"""
app/db/fifo_engine.py
Agent 4: Concurrency-Safe FIFO Inventory Depletion with Row-Level Locks.
"""
import logging
from typing import List, Dict, Any
from sqlalchemy import select, and_, func
from app.db.khata_models import InventoryBatch

logger = logging.getLogger("sahayak.db.fifo")

def deplete_inventory_fifo(
    session,
    merchant_id: str,
    item_name: str,
    quantity_to_deplete: float
) -> List[Dict[str, Any]]:
    """
    Depletes stock using First-In, First-Out (FIFO) logic:
    1. Locks matching rows with `FOR UPDATE` so other concurrent checkouts wait.
    2. Sorts batches by earliest expiry date first, then earliest created_at.
    3. Deducts required quantity sequentially across batches.
    """
    clean_name = item_name.strip()
    
    # Row-level lock: prevents concurrent checkouts from overdrawing the same batch
    batches = session.execute(
        select(InventoryBatch)
        .where(
            and_(
                InventoryBatch.merchant_id == merchant_id,
                func.lower(func.trim(InventoryBatch.item_name)) == func.lower(clean_name),
                InventoryBatch.quantity_remaining > 0
            )
        )
        .order_by(
            InventoryBatch.expiry_date.asc().nulls_last(),
            InventoryBatch.created_at.asc()
        )
        .with_for_update()
    ).scalars().all()

    depleted_records = []
    needed = quantity_to_deplete

    for batch in batches:
        if needed <= 0:
            break
        take = min(batch.quantity_remaining, needed)
        batch.quantity_remaining = round(batch.quantity_remaining - take, 3)
        needed = round(needed - take, 3)
        
        depleted_records.append({
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "depleted_units": take,
            "unit_cost": batch.cost_price,
            "remaining_in_batch": batch.quantity_remaining
        })

    if needed > 0:
        logger.warning(
            f"Stock deficit for merchant {merchant_id}, item '{clean_name}': "
            f"requested {quantity_to_deplete}, short by {needed}"
        )

    return depleted_records
```

### C. Atomic Repository Operations (`app/db/khata_repository.py`)

Guarantees all double-entry mutations happen atomically inside the active merchant's RLS boundary:

1. **`record_counter_sale(session, merchant_id, sale_event)`**:
   * Writes `CashTransaction` for the paid amount.
   * If customer credit was extended (`credit_amount > 0`), updates `CustomerKhata`.
   * For every SKU in `items`, calls `deplete_inventory_fifo`.
   * Commits atomically (if any failure occurs, automatically rolls back).
2. **`record_khata_entry(session, merchant_id, customer_name, amount, action, phone)`**:
   * Finds or creates `CustomerKhata` record.
   * `GIVE_CREDIT` $\rightarrow$ `current_balance += amount` (Customer owes more).
   * `COLLECT_PAYMENT` $\rightarrow$ `current_balance -= amount` & writes `CashTransaction`.
3. **`get_khata_balance(session, merchant_id, customer_name)`**:
   * Returns current outstanding balance for the customer.
4. **`get_available_stock(session, merchant_id, item_name)`**:
   * Returns sum of `quantity_remaining` across all active batches for the item.

---

## 6. Testing & Acceptance Criteria (Gate 2 Validation)

Laptop 2 will be completely validated using `tests/test_khata_fifo_rls.py`:

```bash
# Run isolated test suite:
pytest tests/test_khata_fifo_rls.py -v
```

### Acceptance Checklist:
* [ ] **FIFO Multi-Batch Depletion:**
  * Seed Batch 1 (5 units @ ₹140, expires Nov 1) and Batch 2 (10 units @ ₹147, expires Dec 1).
  * Deplete 8 units.
  * **Assert:** Batch 1 remaining == 0. Batch 2 remaining == 7. Remaining store stock == 7.
* [ ] **Customer Khata Math:**
  * Customer Sharma ji takes ₹500 Udhaar $\rightarrow$ assert balance == ₹500.
  * Customer Sharma ji pays back ₹200 on Paytm $\rightarrow$ assert balance == ₹300, and CashTransaction has +₹200.
* [ ] **Multi-Tenant RLS Isolation:**
  * Seed inventory for Merchant A (`M_RAMESH`).
  * In a session configured for Merchant B (`M_GUPTA`), execute FIFO depletion for the same SKU.
  * **Assert:** Zero rows matched or locked. Zero cross-tenant leakage.
* [ ] **Zero Crash on Stock Deficit:**
  * Request depletion of 50 units when only 10 units exist.
  * **Assert:** Depletes available 10 units to zero without crashing or allowing negative inventory numbers.

---

## 7. Step-by-Step Git Execution Workflow

```bash
# 1. Switch to dedicated Laptop 2 branch
git checkout -b feat/khata-db

# 2. Develop the 4 exclusive files:
#    - app/db/khata_models.py
#    - app/db/fifo_engine.py
#    - app/db/khata_repository.py
#    - tests/test_khata_fifo_rls.py

# 3. Run isolated test suite
pytest tests/test_khata_fifo_rls.py -v

# 4. Stage and commit ONLY Laptop 2 files
git add app/db/khata_models.py app/db/fifo_engine.py app/db/khata_repository.py tests/test_khata_fifo_rls.py
git commit -m "feat(db): implement phase 2 khata models, fifo engine and rls repository"

# 5. Push branch to GitHub
git push -u origin feat/khata-db
```

### Merge Precedence
**Laptop 2 is the FIRST branch merged into `main`**.  
Once merged, Laptop 3 (Jev/Workers) and Laptop 1 (Gateway/POS) pull `main` to immediately use these models and repository functions without a single merge conflict.
