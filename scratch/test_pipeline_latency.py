import sys
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
import time
from app.workers.tasks import process_invoice_task

with open('scratch/invoices/wa_1792886033_eb407c_whatsapp_bill.jpg', 'rb') as f:
    raw = f.read()

print(f"Testing optimized invoice pipeline (raw image size: {len(raw)/1024:.1f} KB)...")
t0 = time.perf_counter()

res = process_invoice_task(
    merchant_id="M_MOHITH_A5AN",
    media_id="test_media_speed",
    whatsapp_message_id="speed_test_02",
    sender_phone="9845012345",
    image_bytes=raw
)

total_elapsed = time.perf_counter() - t0
print(f"Total Pipeline Latency: {total_elapsed:.2f} seconds!")
print(f"Status: {res.get('status', 'SUCCESS')}")
print(f"Invoice Number: {res.get('invoice_number')}")
print(f"Items: {res.get('items_count')}")
print(f"Grand Total: Rs.{res.get('grand_total')}")
