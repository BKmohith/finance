import time
from app.workers.gemini_extractor import get_genai_client, INVOICE_EXTRACTION_PROMPT, _sanitize_schema_for_genai
from app.workers.contracts import ExtractedInvoiceData
from google.genai import types

client = get_genai_client()
with open('scratch/invoices/wa_1792886033_eb407c_whatsapp_bill.jpg', 'rb') as f:
    raw = f.read()

raw_schema = ExtractedInvoiceData.model_json_schema()
sanitized_schema = _sanitize_schema_for_genai(raw_schema)

models_to_test = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-3.5-flash-lite"
]

for m in models_to_test:
    t0 = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=m,
            contents=[
                types.Part.from_bytes(data=raw, mime_type="image/jpeg"),
                INVOICE_EXTRACTION_PROMPT
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=sanitized_schema,
                temperature=0.0
            )
        )
        el = time.perf_counter() - t0
        extracted = ExtractedInvoiceData.model_validate_json(resp.text)
        print(f"Model {m}: {el:.2f}s | Items: {len(extracted.items)} | Total: {extracted.grand_total}")
    except Exception as e:
        print(f"Model {m}: FAILED in {time.perf_counter()-t0:.2f}s -> {e}")
