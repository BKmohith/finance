import sys
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
import time
from app.workers.preprocessor import preprocess_bill_image
from app.workers.gemini_extractor import extract_invoice_from_image
from app.workers.guardrails import validate_invoice_arithmetic
from app.db.session import get_rls_session
from app.db import repository, margin_guard

with open('scratch/invoices/wa_1792886033_eb407c_whatsapp_bill.jpg', 'rb') as f:
    raw = f.read()

print("--- DETAILED PIPELINE PROFILING ---")

# Step 1: Preprocess
t0 = time.perf_counter()
clean = preprocess_bill_image(raw)
t_pre = time.perf_counter() - t0
print(f"1. OpenCV Preprocessing: {t_pre:.3f}s")

# Step 2: Gemini OCR
t0 = time.perf_counter()
extracted = extract_invoice_from_image(clean)
t_gem = time.perf_counter() - t0
print(f"2. Gemini Vision Extraction: {t_gem:.3f}s")

# Step 3: Guardrail
t0 = time.perf_counter()
validated, summary = validate_invoice_arithmetic(extracted, raise_on_failure=False)
t_guard = time.perf_counter() - t0
print(f"3. Arithmetic Validation: {t_guard:.3f}s")

# Step 4: DB Session & Save
t0 = time.perf_counter()
merchant_id = "M_MOHITH_A5AN"
with get_rls_session(merchant_id) as session:
    t_conn = time.perf_counter() - t0
    print(f"4. DB Session Connect: {t_conn:.3f}s")
    
    t0_save = time.perf_counter()
    saved = repository.save_extracted_invoice(session, merchant_id, validated)
    t_save = time.perf_counter() - t0_save
    print(f"5. DB save_extracted_invoice: {t_save:.3f}s")
    
    t0_guard = time.perf_counter()
    alerts = margin_guard.evaluate_price_deviations(session, merchant_id, saved.id)
    t_mg = time.perf_counter() - t0_guard
    print(f"6. Margin Guard Deviations: {t_mg:.3f}s")

print(f"TOTAL TIME: {t_pre + t_gem + t_guard + t_conn + t_save + t_mg:.3f}s")
