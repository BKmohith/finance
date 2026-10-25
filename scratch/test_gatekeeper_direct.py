"""
scratch/test_gatekeeper_direct.py
Test product photo and selfie rejection.
"""
import sys
import os
from pathlib import Path
import cv2
import numpy as np
from dotenv import load_dotenv

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

from google import genai
from google.genai import types

client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=20000))

# Create a product photo (bottle on shelf, no bill)
img = np.zeros((400, 400, 3), dtype=np.uint8)
img[:] = (220, 220, 220)
cv2.rectangle(img, (150, 100), (250, 350), (0, 180, 255), -1)
cv2.putText(img, "Fortune 1L", (160, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
_, encoded = cv2.imencode(".jpg", img)
product_bytes = encoded.tobytes()

INSPECTION_PROMPT = """
You are a document classifier for an Indian retail & wholesale business system.
Analyze this image and determine if it is a commercial paper invoice, distributor wholesale bill, retail purchase receipt, cash memo, or delivery challan.

Important Rule: A photo of a physical product/item without a billing document, invoice paper, or receipt is NOT an invoice (set is_invoice = false).

Respond strictly in JSON format with schema:
{
  "is_invoice": true/false,
  "document_type": "wholesale_invoice" | "retail_bill" | "cash_memo" | "delivery_challan" | "meme" | "selfie" | "personal_photo" | "product_photo" | "scenery" | "greeting_card" | "unrelated" | "other",
  "confidence": float between 0.0 and 1.0,
  "reason": "short explanation"
}
"""

resp = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents=[
        types.Part.from_bytes(data=product_bytes, mime_type="image/jpeg"),
        INSPECTION_PROMPT
    ],
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.0
    )
)
print(f"PRODUCT PHOTO result:\n{resp.text}")
