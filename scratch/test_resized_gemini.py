import time
import cv2
import numpy as np
from app.workers.gemini_extractor import extract_invoice_from_image

with open('scratch/invoices/wa_1792886033_eb407c_whatsapp_bill.jpg', 'rb') as f:
    raw = f.read()

# Test 1: Full original
t0 = time.perf_counter()
res1 = extract_invoice_from_image(raw)
el1 = time.perf_counter() - t0
print(f"Original size ({len(raw)/1024:.1f} KB): {el1:.2f}s")

# Test 2: Resized to max 1200px
img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
h, w = img.shape[:2]
scale = min(1200 / max(h, w), 1.0)
if scale < 1.0:
    img_resized = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
else:
    img_resized = img

_, encoded = cv2.imencode(".jpg", img_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
resized_bytes = encoded.tobytes()

t0 = time.perf_counter()
res2 = extract_invoice_from_image(resized_bytes)
el2 = time.perf_counter() - t0
print(f"Resized to max 1200px ({len(resized_bytes)/1024:.1f} KB): {el2:.2f}s")
print(f"Items extracted: {len(res2.items)}, Grand Total: {res2.grand_total}")
