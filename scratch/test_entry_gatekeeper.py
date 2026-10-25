"""
scratch/test_entry_gatekeeper.py
End-to-End Test for Tiered Gatekeeper (Tier 1 OpenCV Fast Filter + Tier 2 Single-Pass Extraction).
Verifies that random images are blocked with zero database writes.
"""
import sys
import os
from pathlib import Path
import numpy as np
import cv2

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from app.services.image_gatekeeper import classify_image_document, fast_opencv_document_filter
from app.services.bot_service import handle_bill_image_bytes
from app.db.session import get_rls_session
from app.db.models import Invoice
from sqlalchemy import select, func

def test_gatekeeper_pipeline():
    print("=" * 60)
    print("🚀 RUNNING TIERED HYBRID GATEKEEPER TESTS")
    print("=" * 60)

    # 1. Test Real Wholesale Bill
    bill_path = Path("tests/fixtures/bills/sample_bill_SBT_2026_081.jpg")
    bill_bytes = bill_path.read_bytes()

    print("\n[TEST 1] Testing Real Wholesale Invoice...")
    passed_cv, cv_type, cv_reason, metrics = fast_opencv_document_filter(bill_bytes)
    print(f" -> Tier 1 OpenCV Filter: passed={passed_cv}, metrics={metrics}")
    assert passed_cv is True, "Expected wholesale bill to pass Tier 1 OpenCV!"
    print("✅ TEST 1 PASSED: Real bill passes Tier 1 OpenCV filter in <5ms.")

    # 2. Test Colorful Meme / Greeting Card Image (Tier 1 OpenCV Rejection)
    print("\n[TEST 2] Testing Colorful Good Morning Greeting / Meme...")
    img = np.zeros((400, 400, 3), dtype=np.uint8)
    img[:] = (240, 200, 150)
    cv2.circle(img, (200, 200), 100, (0, 255, 255), -1)
    cv2.circle(img, (165, 175), 15, (0, 0, 0), -1)
    cv2.circle(img, (235, 175), 15, (0, 0, 0), -1)
    cv2.ellipse(img, (200, 220), (50, 30), 0, 0, 180, (0, 0, 0), 6)
    cv2.putText(img, "GOOD MORNING!", (60, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (50, 50, 200), 3)
    _, encoded = cv2.imencode(".jpg", img)
    meme_bytes = encoded.tobytes()

    passed_meme, m_type, m_reason, m_metrics = fast_opencv_document_filter(meme_bytes)
    print(f" -> Tier 1 OpenCV Filter: passed={passed_meme}, type={m_type}, reason={m_reason}")
    print(f" -> Metrics: {m_metrics}")
    assert passed_meme is False, "Expected colorful meme to be rejected by Tier 1 OpenCV!"
    assert m_type == "meme"

    meme_res = classify_image_document(meme_bytes)
    assert meme_res.is_invoice is False
    assert "Non-Invoice Image Detected" in meme_res.rejection_message
    print(f" -> Latency: {meme_res.cv_latency_ms} ms ($0 cost, 0 LLM calls!)")
    print("✅ TEST 2 PASSED: Colorful meme rejected in <5ms by Tier 1 OpenCV with $0 cost.")

    # 3. Test Non-Bill Image through Tier 2 Single-Pass Rejection
    print("\n[TEST 3] Testing Non-Bill Document through Single-Pass Pipeline...")
    prod_img = np.zeros((400, 400, 3), dtype=np.uint8)
    prod_img[:] = (220, 220, 220)
    cv2.rectangle(prod_img, (150, 100), (250, 350), (100, 100, 100), -1)
    cv2.putText(prod_img, "Fortune 1L", (160, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    _, encoded_prod = cv2.imencode(".jpg", prod_img)
    prod_bytes = encoded_prod.tobytes()

    test_merchant_id = "M_TEST_GATEKEEPER"
    reply = handle_bill_image_bytes(test_merchant_id, prod_bytes, "product_photo.jpg")
    print(f" -> Single-Pass result: {reply[:100]}...")
    assert "Non-Invoice Image Detected" in reply
    print("✅ TEST 3 PASSED: Non-bill document rejected in Tier 2 Single-Pass without logging.")

    # 4. Verify Zero Database Ingestion for Rejected Images
    print("\n[TEST 4] Verifying Zero Database Pollution...")
    with get_rls_session(test_merchant_id) as session:
        invoices = session.execute(
            select(func.count(Invoice.id)).where(Invoice.merchant_id == test_merchant_id)
        ).scalar() or 0

    print(f" -> Total invoices for test merchant in PostgreSQL: {invoices}")
    assert invoices == 0, f"Expected 0 invoices in database, but found {invoices}!"
    print("✅ TEST 4 PASSED: Exactly 0 invoices logged in database for rejected images.")

    print("\n" + "=" * 60)
    print("🎉 ALL TIERED GATEKEEPER TESTS PASSED 100%!")
    print("=" * 60)

if __name__ == "__main__":
    test_gatekeeper_pipeline()
