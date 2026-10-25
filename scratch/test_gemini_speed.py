import time
from app.workers.gemini_extractor import extract_invoice_from_image

with open('scratch/invoices/wa_1792886033_eb407c_whatsapp_bill.jpg', 'rb') as f:
    raw = f.read()

print("Testing Gemini invoice extraction speed...")
t0 = time.perf_counter()
try:
    res = extract_invoice_from_image(raw)
    elapsed = time.perf_counter() - t0
    print(f"Extraction succeeded in {elapsed:.2f}s!")
    print(f"Supplier: {res.supplier_name}, Total: {res.grand_total}, Items: {len(res.items)}")
except Exception as e:
    print(f"Extraction failed in {time.perf_counter() - t0:.2f}s: {e}")
