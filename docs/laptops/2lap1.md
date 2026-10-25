# Sahayak (सहायक) — Phase 2 Laptop 1 Engineering Blueprint
## Inflow Rails, Customer Khata & Counter POS Touchpoint
### Device: Laptop 1 (Developer A) | Git Branch: `feat/counter` | Target: Phase 2

---

## 1. Executive Context & The Problem Solved

### The Payment-Basket Attribution Gap
In Indian retail kirana operations, when a customer scans a UPI QR code or pays ₹300, existing soundboxes only broadcast monetary metadata:
$$\text{Metadata} = \{\text{amount}: ₹300.00, \text{mode}: \text{"UPI"}\}$$

**The Gap:** Standard payment notifications contain **zero basket itemization**. They cannot determine whether the customer purchased 2 bottles of cooking oil, 5 kg of atta, or repaid prior store credit (*Udhaar*). Without itemization:
1. Concurrency-safe FIFO inventory depletion cannot run.
2. Customer *Khata* credit ledgers cannot be updated with line-item accuracy.

**Laptop 1's Mission:** Build the high-speed **Counter Touchpoint & Customer Receipt Engine** that bridges this gap in $<40\text{ms}$ while maintaining zero merge conflicts with Laptop 2 (DB Core) and Laptop 3 (Jev Engine / STT).

```
 ┌─────────────────────────────────────────────────────────────┐
 │                TOUCHPOINT 1: COUNTER POS                    │
 │               (simulator/counter.html)                      │
 │  • Quick-tap denomination buttons (₹50, ₹100, ₹200, ₹500)   │
 │  • Payment mode toggles (Paytm UPI / Cash / Khata / Split)  │
 │  • SKU autocomplete & single-tap "Complete Sale"            │
 └──────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │              LAPTOP 1: COUNTER INGESTION API                │
 │                   (app/api/counter.py)                      │
 │  1. Ingests & validates CounterSaleEvent (<40ms)            │
 │  2. Dispatches Celery task "workers.process_counter_sale"   │
 │  3. Calls Customer Khata Notifier if Udhaar is given        │
 └──────────────┬───────────────────────────────▲──────────────┘
                │                               │
                ▼                               │ Digital Receipt
   [Celery Worker Queue]                        │
                │                               │
                ▼                               │
   [Laptop 3: Voice/Jev & Laptop 2: FIFO DB] ───┘
```

---

## 2. Disjoint File Map (DFM) — 100% Zero Git Conflicts

Laptop 1 has exclusive, strict ownership over these 4 files:

```
sahayak/
├── app/
│   ├── core/                        # [FROZEN CONTRACT] Pre-committed to main
│   │   ├── config.py
│   │   └── contracts.py             # Phase 2 schemas frozen on main
│   │
│   └── api/                         # [LAPTOP 1 EXCLUSIVE DOMAIN]
│       ├── counter.py               # NEW: POS endpoint (POST /api/counter/sale)
│       └── counter_notifier.py      # NEW: Customer Khata receipt dispatcher
│
├── simulator/                       # [LAPTOP 1 EXCLUSIVE DOMAIN]
│   └── counter.html                 # NEW: Touch-Friendly Kirana Counter POS Web UI
│
└── tests/                           # [LAPTOP 1 EXCLUSIVE DOMAIN]
    └── test_counter_gateway.py      # NEW: Isolated unit test suite (100% green target)
```

> **Zero Collision Guarantee:** Laptop 1 touches **ZERO** files belonging to Laptop 2 (`app/db/khata_models.py`, `app/db/fifo_engine.py`, `app/db/khata_repository.py`) and **ZERO** files belonging to Laptop 3 (`app/workers/jev_router.py`, `app/workers/stt_engine.py`, `app/workers/voice_khata.py`).

---

## 3. The Shared Frozen Phase 2 Contract (`app/core/contracts.py`)

All three laptops adhere strictly to these schemas (already committed to `main`):

```python
class PaymentMethod(str, Enum):
    PAYTM_UPI = "PAYTM_UPI"
    CASH = "CASH"
    KHATA_CREDIT = "KHATA_CREDIT"      # Udhaar
    SPLIT = "SPLIT"                    # Part cash/UPI, part credit

class CounterItemSale(BaseModel):
    item_name: str = Field(description="SKU or product name")
    quantity: float = Field(gt=0, description="Quantity sold")
    unit: str = Field(default="units", description="units, kg, litre, packet")
    unit_retail_price: float = Field(gt=0, description="Retail selling price per unit")
    line_total: float = Field(gt=0, description="quantity * unit_retail_price")

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

CELERY_COUNTER_TASK_NAME = "workers.process_counter_sale"
```

---

## 4. Laptop 1 Technical Implementation Breakdown

### 4.1 Counter POS API (`app/api/counter.py`)
* Router: `counter_router = APIRouter(prefix="/api/counter", tags=["Counter POS"])`
* **`POST /api/counter/sale`**:
  - Validates `CounterSaleEvent`.
  - Calculates total basket value and checks consistency against `amount_paid + credit_amount`.
  - Dispatches `CELERY_COUNTER_TASK_NAME` with basket items for FIFO inventory depletion.
  - If `credit_amount > 0` and `customer_phone` is present, triggers `counter_notifier.send_khata_credit_receipt()`.
  - Latency: $<40\text{ms}$ return.
* **`GET /api/counter/summary`**:
  - Quick snapshot of today's counter inflow: cash total, UPI total, credit extended, and transaction count.

### 4.2 Customer Khata Notifier (`app/api/counter_notifier.py`)
* Dispatches formatted digital receipts to customers when store credit (*Udhaar*) is granted:
  ```
  🙏 *Namaste {customer_name} ji,*
  Ramesh Kirana Store par aapka naya hisaab darj hua hai:
  
  🧾 *Bill Amount:* ₹{total_bill:,.2f}
  💵 *Amount Paid:* ₹{amount_paid:,.2f}
  📝 *Naya Udhaar (Credit):* ₹{credit_amount:,.2f}
  
  _Shukriya! Sahayak Digital Khata dwara surakshit._
  ```
* Supports delivery via Telegram Bot API (`@sahayak_retail_bot`) and WhatsApp.

### 4.3 Kirana Touch Counter Web UI (`simulator/counter.html`)
* Modern, responsive interface optimized for mobile and counter tablets:
  - Preset quick cash buttons: ₹50, ₹100, ₹200, ₹500, Custom.
  - One-tap payment mode selection: **Paytm UPI**, **Cash**, **Khata (Udhaar)**, **Split**.
  - Fast SKU search with autocomplete for Indian FMCG items (*Fortune Sunflower Oil 1L*, *Aashirvaad Atta 10kg*, *Surf Excel 1kg*, *Tata Salt 1kg*).
  - Live basket calculation with item quantity stepper (+ / -).
  - Single-click **"Complete Sale & Deplete Stock"** action.

### 4.4 Isolated Test Suite (`tests/test_counter_gateway.py`)
* Unit tests running via FastAPI `TestClient` with mocked Celery task dispatcher:
  1. `test_counter_sale_cash_success`: Full cash transaction verification.
  2. `test_counter_sale_upi_success`: Paytm UPI payment verification.
  3. `test_counter_sale_khata_credit_receipt`: Verifies customer Khata receipt trigger when `credit_amount > 0`.
  4. `test_counter_sale_split_payment`: Split cash + credit verification.
  5. `test_counter_sale_validation_errors`: Rejects negative amounts or mismatched totals.
  6. `test_counter_summary_snapshot`: Validates daily sales totals endpoint.

---

## 5. External Tools & Credentials Status

| Service / Tool | Status | Action Required |
|---|---|---|
| **Telegram Bot API** | ✅ Active | `@sahayak_retail_bot` already configured in `.env` — **No action needed** |
| **Supabase PostgreSQL** | ✅ Active | Database URL configured in `app/core/config.py` — **No action needed** |
| **Python 3.11 Runtime** | ✅ Ready | Virtual environment `.venv` active with all dependencies — **No action needed** |
| **GitHub Push Access** | ✅ Active | Authenticated on `origin` — **No action needed** |

> **Conclusion on External Tools:** Zero new external accounts or logins are required from the user! Everything needed for Laptop 1 is already in place.

---

## 6. Strict Merge Sequence Alignment (Phase 2)

```
   STEP 1: Laptop 2 (`feat/khata-db`) Merges First
           • Deploys Khata tables & FIFO batch depletion logic to Supabase.
           │
           ▼
   STEP 2: Laptop 3 (`feat/jev-stt`) Merges Second
           • Connects Jev router & audio STT to Celery tasks.
           │
           ▼
   STEP 3: Laptop 1 (`feat/counter`) Merges Third
           • Plugs counter_router into the unified gateway.
           │
           ▼
   STEP 4: Unified Multi-Laptop Verification
           pytest tests/test_counter_gateway.py tests/test_khata_fifo_rls.py tests/test_jev_stt.py -v
```

---

## 7. Immediate Next Steps

1. Checkout branch `feat/counter` (or build on `feature/laptop1`).
2. Build `app/api/counter.py` and `app/api/counter_notifier.py`.
3. Build `simulator/counter.html`.
4. Build `tests/test_counter_gateway.py` and achieve 100% green test pass.
5. Push to GitHub!
