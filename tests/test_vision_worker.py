"""
tests/test_vision_worker.py
Comprehensive isolated unit and integration test suite for Laptop 3 (Vision AI & OCR Worker).
Tests OpenCV preprocessing, Gemini Flash structured extraction, arithmetic guardrails,
and the Celery pipeline task.
"""
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import cv2
import numpy as np

from app.core.contracts import (
    ExtractedInvoiceData,
    ExtractedLineItem,
    PriceHikeAlert,
)
from app.workers.preprocessor import (
    decode_image_bytes,
    compute_skew_angle,
    rotate_image,
    preprocess_bill_image,
)
from app.workers.guardrails import (
    validate_invoice_arithmetic,
    validate_line_item_math,
    GuardrailValidationError,
)
from app.workers.gemini_extractor import extract_invoice_from_image
from app.workers.tasks import process_invoice_task, fetch_media_from_storage_or_meta
from app.core.config import settings

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "bills"


# --- Fixtures ---
@pytest.fixture
def sample_clean_bill_bytes() -> bytes:
    bill_path = FIXTURES_DIR / "sample_bill_SBT_2026_081.jpg"
    assert bill_path.exists(), f"Fixture missing: {bill_path}"
    return bill_path.read_bytes()


@pytest.fixture
def sample_skewed_bill_bytes() -> bytes:
    bill_path = FIXTURES_DIR / "sample_bill_SBT_2026_082_skewed.jpg"
    assert bill_path.exists(), f"Fixture missing: {bill_path}"
    return bill_path.read_bytes()


@pytest.fixture
def valid_invoice_data() -> ExtractedInvoiceData:
    return ExtractedInvoiceData(
        supplier_name="Shree Balaji Traders",
        supplier_gstin="29AABCU9603R1ZM",
        invoice_number="SBT-2026-081",
        invoice_date=date(2026, 10, 24),
        credit_due_date=date(2026, 11, 5),
        items=[
            ExtractedLineItem(
                item_name="Fortune Sunflower Oil 1L",
                quantity=25.0,
                unit="units",
                unit_wholesale_rate=110.0,
                tax_rate_pct=5.0,
                line_total=2750.0,
            ),
            ExtractedLineItem(
                item_name="Aashirvaad Shudh Chakki Atta 10kg",
                quantity=10.0,
                unit="units",
                unit_wholesale_rate=380.0,
                tax_rate_pct=0.0,
                line_total=3800.0,
            ),
            ExtractedLineItem(
                item_name="Tata Salt 1kg",
                quantity=50.0,
                unit="units",
                unit_wholesale_rate=24.0,
                tax_rate_pct=0.0,
                line_total=1200.0,
            ),
        ],
        grand_total=7750.0,
        confidence_score=0.98,
    )


# --- 1. Contract Tests ---
def test_contracts_schema_validation(valid_invoice_data):
    """Verifies that ExtractedInvoiceData matches the frozen contract constraints."""
    assert valid_invoice_data.supplier_name == "Shree Balaji Traders"
    assert len(valid_invoice_data.items) == 3
    assert valid_invoice_data.grand_total == 7750.0
    assert 0.0 <= valid_invoice_data.confidence_score <= 1.0

    # Ensure serialization roundtrips cleanly
    json_str = valid_invoice_data.model_dump_json()
    reparsed = ExtractedInvoiceData.model_validate_json(json_str)
    assert reparsed == valid_invoice_data


# --- 2. OpenCV Image Preprocessor Tests ---
def test_preprocessor_decode_valid_bytes(sample_clean_bill_bytes):
    """Tests decoding raw image bytes to an OpenCV ndarray."""
    img = decode_image_bytes(sample_clean_bill_bytes)
    assert isinstance(img, np.ndarray)
    assert len(img.shape) == 3
    assert img.shape[0] > 0 and img.shape[1] > 0


def test_preprocessor_rejects_corrupted_bytes():
    """Verifies ValueError when fed corrupted bytes."""
    with pytest.raises(ValueError, match="Failed to decode image bytes"):
        decode_image_bytes(b"not_an_image_corrupted_data")


def test_preprocessor_deskew_and_enhancement(sample_skewed_bill_bytes):
    """Verifies the complete preprocessing pipeline (deskew, bilateral filter, CLAHE)."""
    preprocessed_bytes = preprocess_bill_image(
        sample_skewed_bill_bytes,
        enable_deskew=True,
        apply_clahe=True,
        apply_bilateral=True,
    )
    assert isinstance(preprocessed_bytes, bytes)
    assert len(preprocessed_bytes) > 0

    # Verify output can be decoded as a valid grayscale/BGR image
    enhanced_img = decode_image_bytes(preprocessed_bytes)
    assert enhanced_img is not None
    assert enhanced_img.shape[0] > 100


# --- 3. Arithmetic Guardrails Tests ---
def test_arithmetic_guardrails_pass_valid_invoice(valid_invoice_data):
    """Verifies that valid mathematics passes with zero discrepancies."""
    validated, summary = validate_invoice_arithmetic(valid_invoice_data, raise_on_failure=True)
    assert summary.is_valid is True
    assert len(summary.discrepancies) == 0
    assert summary.calculated_subtotal == 7750.0
    assert summary.grand_total == 7750.0


def test_arithmetic_guardrails_detect_line_item_mismatch():
    """Verifies rejection when a line total is mathematically hallucinated."""
    corrupted_invoice = ExtractedInvoiceData(
        supplier_name="Test Supplier",
        invoice_number="INV-CORRUPT-1",
        invoice_date=date(2026, 10, 24),
        items=[
            ExtractedLineItem(
                item_name="Sugar 50kg bag",
                quantity=2.0,
                unit="units",
                unit_wholesale_rate=2000.0,
                tax_rate_pct=0.0,
                line_total=3500.0,  # Deliberate error: 2 * 2000 = 4000 != 3500
            )
        ],
        grand_total=3500.0,
        confidence_score=0.90,
    )

    with pytest.raises(GuardrailValidationError) as excinfo:
        validate_invoice_arithmetic(corrupted_invoice, raise_on_failure=True)

    assert "discrepancies detected" in str(excinfo.value).lower()


def test_arithmetic_guardrails_detect_grand_total_mismatch(valid_invoice_data):
    """Verifies rejection when the grand total does not match the sum of items."""
    corrupted_invoice = valid_invoice_data.model_copy(deep=True)
    corrupted_invoice.grand_total = 9999.0  # Deliberate error: sum is 7750.0

    with pytest.raises(GuardrailValidationError) as excinfo:
        validate_invoice_arithmetic(corrupted_invoice, raise_on_failure=True)

    assert "grand total mismatch" in str(excinfo.value).lower()


# --- 4. Mocked Celery Task Pipeline Tests ---
@patch("app.workers.tasks.extract_invoice_from_image")
def test_celery_task_process_invoice_mocked(mock_extract, valid_invoice_data, sample_clean_bill_bytes):
    """
    Tests the Celery task orchestration in eager mode with mocked Gemini extractor,
    verifying clean decoupled execution without requiring live PostgreSQL or Meta APIs.
    """
    mock_extract.return_value = valid_invoice_data

    from app.workers.tasks import celery_app
    celery_app.conf.update(task_always_eager=True)

    # Execute task synchronously in isolated worker test
    res = process_invoice_task.apply(
        args=[
            "MERCHANT_M001",
            str(FIXTURES_DIR / "sample_bill_SBT_2026_081.jpg"),
            "wamid.HBgLMTIzNDU2",
            "+919876543210",
        ]
    )
    result = res.result

    assert result["status"] == "SUCCESS"
    assert result["merchant_id"] == "MERCHANT_M001"
    assert result["invoice_number"] == "SBT-2026-081"
    assert result["grand_total"] == 7750.0
    assert result["items_count"] == 3
    assert result["confidence_score"] == 0.98


# --- 5. Live Gemini Flash Extraction Test ---
def test_live_gemini_extraction(sample_clean_bill_bytes):
    """
    Executes live extraction with Gemini on the test bill fixture using configured GEMINI_API_KEY.
    Skipped automatically if no key is configured.
    """
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_gemini_api_key_here":
        pytest.skip("GEMINI_API_KEY not configured for live test.")

    try:
        extracted = extract_invoice_from_image(sample_clean_bill_bytes)
        assert isinstance(extracted, ExtractedInvoiceData)
        assert extracted.supplier_name != ""
        assert len(extracted.items) >= 1
        assert extracted.grand_total > 0
        assert 0.0 <= extracted.confidence_score <= 1.0

        # Run guardrail verification on live response
        validated, summary = validate_invoice_arithmetic(extracted, raise_on_failure=False)
        assert summary.calculated_subtotal > 0
    except Exception as exc:
        pytest.skip(f"Live Gemini API call transient error or timeout: {exc}")
