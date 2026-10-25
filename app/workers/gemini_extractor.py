"""
app/workers/gemini_extractor.py
Structured Invoice Extraction using Gemini 2.5 Flash and rigid Pydantic JSON schemas.
"""
import logging
from typing import Optional, Any, List
from google import genai
from google.genai import types

from app.workers.config import settings
from app.workers.contracts import ExtractedInvoiceData

logger = logging.getLogger(__name__)

INVOICE_EXTRACTION_PROMPT = """
You are an expert Indian FMCG wholesale invoice decoder and auditor.
Analyze this invoice image and extract structured data conforming strictly to the requested schema.

Key Instructions:
1. Extract the supplier name and GSTIN (if present).
2. Extract the invoice number and invoice date (YYYY-MM-DD format).
3. If payment terms, credit days, or cheque due date is mentioned, compute the credit_due_date.
4. Carefully extract all itemized FMCG line items:
   - item_name: Standardized product name including pack size (e.g. 'Fortune Sunflower Oil 1L', 'Parle-G 100g').
   - quantity: Quantity delivered (must be > 0).
   - unit: e.g. units, cartons, cases, kg, litres.
   - unit_wholesale_rate: Base purchase rate per unit before tax.
   - tax_rate_pct: GST tax percentage (0.0 to 28.0%).
   - line_total: Net total for this line.
5. Decode dot-matrix typography, faint printer ribbons, regional formats, and handwritten numbers accurately.
6. Provide a confidence_score between 0.0 and 1.0 reflecting visual clarity.
7. NON-INVOICE REJECTION: If this image is NOT a commercial invoice, wholesale paper bill, cash memo, or delivery challan (e.g. an ID card, portrait, or paper without itemized prices):
   - Leave items empty: items = []
   - Set grand_total = 0.0
   - Set confidence_score = 0.0
   - Set supplier_name = "NON_INVOICE"
"""


def _sanitize_schema_for_genai(schema: Any) -> Any:
    """
    Sanitizes Pydantic v2 JSON Schema to align with Google GenAI OpenAPI 3.0 types.Schema constraints.
    Translates exclusiveMinimum/exclusiveMaximum to minimum/maximum.
    """
    if isinstance(schema, dict):
        sanitized = {}
        for k, v in schema.items():
            if k == "exclusiveMinimum":
                sanitized["minimum"] = v
            elif k == "exclusiveMaximum":
                sanitized["maximum"] = v
            else:
                sanitized[k] = _sanitize_schema_for_genai(v)
        return sanitized
    elif isinstance(schema, list):
        return [_sanitize_schema_for_genai(x) for x in schema]
    return schema


def get_genai_client(api_key: Optional[str] = None) -> genai.Client:
    """Returns a GenAI client initialized with the provided or configured API key."""
    key = api_key or settings.GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_API_KEY is not set. Please set it in .env or provide it directly.")
    return genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=30000),
    )


class NonInvoiceDocumentError(ValueError):
    """Raised when an image does not contain a commercial invoice or paper bill."""
    pass


def extract_invoice_from_image(
    image_bytes: bytes,
    client: Optional[genai.Client] = None,
    model_name: Optional[str] = None,
    mime_type: str = "image/jpeg",
) -> ExtractedInvoiceData:
    """
    Extracts structured invoice data from preprocessed image bytes using Gemini Flash.
    Enforces rigid JSON schema adherence via the ExtractedInvoiceData Pydantic contract.
    """
    ai_client = client or get_genai_client()
    target_model = model_name or settings.GEMINI_MODEL or "gemini-3.5-flash-lite"

    logger.info("Dispatching image to Gemini (%s) for structured invoice extraction...", target_model)

    # Convert Pydantic JSON schema to sanitized dictionary accepted directly by GenerateContentConfig
    raw_schema = ExtractedInvoiceData.model_json_schema()
    sanitized_schema = _sanitize_schema_for_genai(raw_schema)

    # Candidate models in preference order
    candidate_models: List[str] = [target_model]
    for fallback in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]:
        if fallback not in candidate_models:
            candidate_models.append(fallback)

    last_error: Optional[Exception] = None

    for model in candidate_models:
        try:
            logger.info("Attempting extraction with Gemini model: %s", model)
            response = ai_client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    INVOICE_EXTRACTION_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=sanitized_schema,
                    temperature=0.0,
                ),
            )

            if response and response.text:
                extracted = ExtractedInvoiceData.model_validate_json(response.text)
                # Guardrail: Abort if no line items, zero grand total, or flagged non-invoice
                if len(extracted.items) == 0 or extracted.grand_total <= 0.0:
                    raise NonInvoiceDocumentError("Image does not contain commercial line items or billing amounts.")
                if extracted.confidence_score < 0.3:
                    raise NonInvoiceDocumentError(f"Confidence score ({extracted.confidence_score}) is too low for an invoice.")
                if extracted.supplier_name.upper() == "NON_INVOICE":
                    raise NonInvoiceDocumentError("Image was identified as a non-invoice document.")
                return extracted

            raise RuntimeError(f"Model {model} returned an empty response.")

        except NonInvoiceDocumentError:
            raise
        except Exception as exc:
            logger.warning("Extraction attempt with %s failed: %s. Trying next model...", model, exc)
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("All candidate Gemini models failed to extract invoice data.")
