"""
tests/test_jev_stt.py
Isolated Test Suite for Laptop 3 (Perception, Jev Router, Vernacular STT & Counter Tasks).
Zero dependencies on Laptop 1 (Gateway) or Laptop 2 (Database).
"""
import time
import pytest
from unittest.mock import patch, MagicMock

from app.core.contracts import (
    InboundIntentClass,
    PaymentMethod,
    VoiceKhataIntent,
    CounterSaleEvent,
)
from app.workers.jev_router import classify_inbound_intent, JevRouter
from app.workers.stt_engine import transcribe_audio, STTEngine
from app.workers.voice_khata import parse_voice_khata, parse_counter_sale
from app.workers.counter_tasks import process_counter_sale


# ============================================================================
# 1. System 1: Jev Router Tests
# ============================================================================

def test_jev_router_latency_under_18ms():
    """Verifies that System 1 intent routing runs in <18ms on CPU."""
    start = time.perf_counter()
    result = classify_inbound_intent("25 bag atta 450 cash")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert result == InboundIntentClass.COUNTER_SALE
    assert elapsed_ms < 18.0, f"Jev router took {elapsed_ms:.2f}ms, which exceeds 18ms SLA!"


def test_jev_router_spam_rejection():
    """Confirms greetings, blessings, and memes are dropped as MEME_SPAM in <5ms."""
    spam_samples = [
        "Good Morning!",
        "Suprabhat",
        "Jai Shree Ram 🙏",
        "Radhe Radhe",
        "Happy Diwali to all",
        "Hello hi hey",
    ]

    for sample in spam_samples:
        start = time.perf_counter()
        intent = classify_inbound_intent(sample)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert intent == InboundIntentClass.MEME_SPAM, f"Failed for spam sample: {sample}"
        assert elapsed_ms < 5.0, f"Spam fast-path took {elapsed_ms:.2f}ms, expected <5ms"


def test_jev_router_intent_routing():
    """Confirms accurate routing across Counter Sales, Voice Khata, and Invoices."""
    # Counter Sales
    assert classify_inbound_intent("Paytm 300 Oil 2") == InboundIntentClass.COUNTER_SALE
    assert classify_inbound_intent("5 packet milk 30 upi") == InboundIntentClass.COUNTER_SALE

    # Voice Khata
    assert classify_inbound_intent("Sharma ji 500 udhaar") == InboundIntentClass.VOICE_KHATA
    assert classify_inbound_intent("ರಮೇಶ್ ಅವರಿಗೆ 500 ರೂಪಾಯಿ ಸಾಲ") == InboundIntentClass.VOICE_KHATA
    assert classify_inbound_intent("Gupta ji 1000 jama kiya") == InboundIntentClass.VOICE_KHATA

    # Invoices
    assert classify_inbound_intent("Tax Invoice No 4210 GSTIN") == InboundIntentClass.INVOICE_BILL
    assert classify_inbound_intent(media_mime_type="image/jpeg") == InboundIntentClass.INVOICE_BILL


# ============================================================================
# 2. Vernacular Speech-to-Text (Sarvam AI / Kannada) Tests
# ============================================================================

def test_stt_mock_kannada_transcription():
    """Tests Kannada audio ingestion via STT engine mock."""
    mock_audio = b"MOCK_KANNADA_AUDIO_STREAM_DATA_123456789"
    result = transcribe_audio(mock_audio, filename="voice.ogg", language_code="kn-IN")

    assert result["transcription"] == "ರಮೇಶ್ ಅವರಿಗೆ 500 ರೂಪಾಯಿ ಸಾಲ"
    assert result["language_code"] == "kn-IN"
    assert result["confidence"] >= 0.90
    assert result["provider"] == "mock"


def test_stt_mock_sale_transcription():
    """Tests sales voice note ingestion via STT engine."""
    mock_audio = b"MOCK_SALE_AUDIO_BYTES_TEST_STREAM"
    result = transcribe_audio(mock_audio, filename="sale.wav", language_code="en-IN")

    assert "atta" in result["transcription"].lower()
    assert result["confidence"] >= 0.90


@patch("httpx.Client.post")
def test_stt_sarvam_api_call(mock_post):
    """Verifies Sarvam AI API payload structure and response handling."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "transcript": "ರಮೇಶ್ 500 ರೂಪಾಯಿ ಸಾಲ",
        "language_code": "kn-IN",
    }
    mock_post.return_value = mock_response

    engine = STTEngine()
    engine.sarvam_api_key = "test_sarvam_key"

    audio_bytes = b"REAL_BINARY_AUDIO_BYTES_FOR_SARVAM_TEST"
    res = engine.transcribe_audio(audio_bytes, filename="note.opus", language_code="kn-IN")

    assert res["transcription"] == "ರಮೇಶ್ 500 ರೂಪಾಯಿ ಸಾಲ"
    assert res["provider"] == "sarvam_ai"
    mock_post.assert_called_once()


# ============================================================================
# 3. Conversational Entity Extractor (Agent 1) Tests
# ============================================================================

def test_voice_khata_kannada_credit_extraction():
    """Verifies parsing of Kannada Udhaar credit notes into VoiceKhataIntent."""
    kannada_text = "ರಮೇಶ್ ಅವರಿಗೆ 500 ರೂಪಾಯಿ ಸಾಲ"
    intent = parse_voice_khata(kannada_text)

    assert intent is not None
    assert intent.customer_name == "Ramesh"
    assert intent.amount == 500.0
    assert intent.action == "GIVE_CREDIT"
    assert intent.confidence >= 0.90


def test_voice_khata_repayment_extraction():
    """Verifies parsing of customer credit repayment into VoiceKhataIntent."""
    repayment_text = "Gupta ji ne 1000 jama kiya"
    intent = parse_voice_khata(repayment_text)

    assert intent is not None
    assert intent.customer_name == "Gupta ji"
    assert intent.amount == 1000.0
    assert intent.action == "COLLECT_PAYMENT"


def test_voice_khata_counter_sale_extraction():
    """Verifies parsing of sales shorthand into CounterSaleEvent."""
    # Test 1: Atta bags with unit rate
    sale_text_1 = "25 bag atta 450 cash"
    event_1 = parse_counter_sale(sale_text_1, merchant_id="M_STORE_001")

    assert event_1 is not None
    assert event_1.merchant_id == "M_STORE_001"
    assert event_1.payment_method == PaymentMethod.CASH
    assert event_1.amount_paid == 11250.0  # 25 * 450
    assert len(event_1.items) == 1
    assert event_1.items[0].item_name == "atta"
    assert event_1.items[0].quantity == 25.0
    assert event_1.items[0].unit_retail_price == 450.0

    # Test 2: Paytm Oil sale shorthand
    sale_text_2 = "Paytm 300 Oil 2"
    event_2 = parse_counter_sale(sale_text_2, merchant_id="M_STORE_001")

    assert event_2 is not None
    assert event_2.payment_method == PaymentMethod.PAYTM_UPI
    assert event_2.amount_paid == 300.0
    assert len(event_2.items) == 1
    assert event_2.items[0].item_name == "Oil"
    assert event_2.items[0].quantity == 2.0
    assert event_2.items[0].unit_retail_price == 150.0


# ============================================================================
# 4. Celery Counter Worker Task Tests
# ============================================================================

def test_celery_counter_task_execution():
    """Verifies process_counter_sale task executes cleanly and formats depletion request."""
    sample_sale_dict = {
        "merchant_id": "M_TEST_STORE",
        "amount_paid": 450.0,
        "payment_method": "CASH",
        "payment_reference": "TXN_998877",
        "items": [
            {
                "item_name": "Sugar",
                "quantity": 10.0,
                "unit": "kg",
                "unit_retail_price": 45.0,
                "line_total": 450.0,
            }
        ],
    }

    # Execute task synchronously
    result = process_counter_sale.apply(args=[sample_sale_dict]).get()

    assert result["status"] == "SUCCESS"
    assert result["merchant_id"] == "M_TEST_STORE"
    assert result["items_count"] == 1
    assert result["amount_paid"] == 450.0
    assert "depletion_request" in result
    assert result["depletion_request"]["sale_id"] == "TXN_998877"
