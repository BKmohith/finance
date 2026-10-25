# Laptop 2 — Final Architectural Conclusion & Build Specification
## Domain: Data Core, Multi-Tenant RLS & Deterministic Margin-Guard Engine
### Project: Sahayak (सहायक) Phase 1 — Outflow Foundation & Paper Bill Digitizer

---

## 1. System Identity & Mission Statement

* **Device Identity:** Laptop 2 (Developer B)
* **Git Branch:** `feat/db-core`
* **Target Database:** Supabase PostgreSQL 16 (Cloud)
* **Host:** `db.qhuzerpsnkxmbjrkaadz.supabase.co:5432/postgres`
* **Role in Team:** Central Data Foundation. Laptop 2 builds the transactional backbone. Laptop 1 (Gateway) and Laptop 3 (Vision AI) integrate into Laptop 2's database models and repository functions.

---

## 2. The 3-Laptop Integration Dataflow

```
  [LAPTOP 1: GATEWAY]                [LAPTOP 3: VISION AI]               [LAPTOP 2: YOU / DATA CORE]
  WhatsApp Webhook Ingestion         Celery Worker + Gemini Flash        Supabase PostgreSQL 16 + RLS
  
  Merchant snaps paper bill          Pre-processes image (OpenCV)        Atomic ACID Transaction Write
             │                                     │                                    │
             ▼                                     ▼                                    ▼
  Receives image payload  ────────>  Decodes dot-matrix invoice  ───────>  Saves Invoice & Items to Supabase
  Deduplicates in Redis (<1ms)       Validates: qty * rate == total        Calculates Margin-Guard (>3% hike)
                                                                                        │
                                                                                        ▼
  Dispatches WhatsApp Alert  <─────────────────────────────────────────────  Emits PriceHikeAlert payload
  to merchant: "Raise MRP!"
```

---

## 3. Laptop 2 Scope & Deliverables

Laptop 2 codes exclusively in `app/db/`, `app/core/contracts.py`, and `tests/test_database_rls.py`:

```
sahayak/
├── app/
│   ├── core/
│   │   ├── __init__.py
│   │   └── contracts.py         <-- Shared Frozen Pydantic Contract
│   │
│   └── db/                      <-- Laptop 2 Core Domain
│       ├── __init__.py
│       ├── session.py           # Supabase connection & RLS context manager
│       ├── models.py            # PostgreSQL 16 SQLAlchemy 2.0 ORM tables
│       ├── repository.py        # Atomic ACID transaction write operations
│       └── margin_guard.py      # Deterministic price-hike calculator (Agent 3)
│
├── tests/
│   └── test_database_rls.py     # Multi-tenant isolation & margin guard test suite
├── .env                         # Supabase connection string (URL-encoded)
└── requirements.txt             # sqlalchemy, psycopg2-binary, pydantic, pytest
```

---

## 4. Supabase Connection Configuration

Because the password contains a special character (`@`), it is URL-encoded as `%40` to ensure SQLAlchemy and psycopg2 connect without syntax errors:

```env
# Raw Password:      Mohithbk@2007
# Encoded Password:  Mohithbk%402007

DATABASE_URL=postgresql://postgres:Mohithbk%402007@db.qhuzerpsnkxmbjrkaadz.supabase.co:5432/postgres
```

---

## 5. Architectural Blueprint of Laptop 2 Modules

### A. The Shared Frozen Contract (`app/core/contracts.py`)
Provides the strict, unchangeable interface between all 3 laptops:
* `ExtractedLineItem`: Normalized product name, quantity, unit wholesale rate, tax, line total.
* `ExtractedInvoiceData`: Supplier name, invoice number, invoice date, credit due date, line items list, grand total.
* `PriceHikeAlert`: Merchant ID, phone, item name, old rate, new rate, hike percentage, previous MRP, suggested new MRP.

### B. Supabase Multi-Tenant RLS Session (`app/db/session.py`)
* Establishes a pooled SQLAlchemy engine connecting to Supabase.
* Implements a **session-scoped context manager**:
  ```python
  @contextmanager
  def get_rls_session(merchant_id: str):
      session = SessionLocal()
      try:
          # Sets session parameter strictly for the duration of this transaction
          session.execute(
              text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
              {"m_id": merchant_id}
          )
          yield session
          session.commit()
      except Exception:
          session.rollback()
          raise
      finally:
          session.close()
  ```

### C. Financial Database Schema (`app/db/models.py`)
* **`merchants`**: Store name, phone number, GSTIN, created timestamp.
* **`suppliers`**: FMCG distributor name, GSTIN, default payment credit terms.
* **`invoices`**: Invoice number, invoice date, credit due date (cheque bounce date), grand total.
* **`invoice_line_items`**: Item name, quantity delivered, wholesale purchase rate, tax percentage, line total.
* **`price_history`**: SKU price tracking table recording every wholesale rate shift over time.
* **`statutory_audit_log`**: Append-only log recording every transaction with cryptographic payload hash.
* **PostgreSQL RLS Policies**:
  ```sql
  ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
  CREATE POLICY merchant_isolation_policy ON invoices 
  FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));
  ```

### D. Transactional Repository (`app/db/repository.py`)
* Implements `save_extracted_invoice(merchant_id: str, data: ExtractedInvoiceData) -> Invoice`:
  1. Checks if supplier exists; creates if new.
  2. Inserts invoice header record.
  3. Batch-inserts itemized line items.
  4. Appends to `price_history`.
  5. If any single step fails, performs an **instant automatic rollback** to prevent half-saved records.

### E. Agent 3: Margin-Guard Price-Shield (`app/db/margin_guard.py`)
* Implements `evaluate_price_deviations(merchant_id: str, invoice_id: str) -> List[PriceHikeAlert]`:
  1. Queries the previous wholesale unit rate for each item in the invoice.
  2. Calculates rate of change:
     $$\Delta \text{Rate} = \frac{\text{New Rate} - \text{Old Rate}}{\text{Old Rate}} \times 100$$
  3. If $\Delta \text{Rate} > 3.0\%$:
     * Computes the new suggested retail MRP to defend a 12% gross profit margin:
       $$\text{Suggested MRP} = \text{New Rate} \times 1.12$$
     * Packages and returns a list of `PriceHikeAlert` objects for Laptop 1 to broadcast over WhatsApp.

---

## 6. Testing & Acceptance Criteria (Gate 1 Validation)

Laptop 2 will be verified using `tests/test_database_rls.py`:
1. **Multi-Tenant Security Test:**
   * Create Merchant `M_001` and Merchant `M_002` in Supabase.
   * Save an invoice under `M_001`.
   * Attempt to query invoices using an active session for `M_002`.
   * **Assertion:** Query returns **0 rows**. Cross-tenant leakage is physically impossible.
2. **ACID Rollback Test:**
   * Simulate a database constraint failure on line item insertion.
   * **Assertion:** Invoice header is rolled back; zero corrupt rows remain.
3. **Margin-Guard Calculation Test:**
   * Insert a baseline item: *Fortune Oil @ ₹140*.
   * Ingest a new invoice: *Fortune Oil @ ₹147 (+5%)*.
   * **Assertion:** Generates a `PriceHikeAlert` suggesting new MRP of ₹164.64.

---

## 7. Merge Readiness Protocol

When Laptop 2 completes and all unit tests pass:
```bash
git checkout -b feat/db-core
git add app/core/ app/db/ tests/ .env
git commit -m "feat(db): complete supabase rls schema, repository and margin-guard engine"
git push -u origin feat/db-core
```
**Laptop 2 is the FIRST branch merged into `main`**, unlocking Laptop 3 and Laptop 1 for final integration.
