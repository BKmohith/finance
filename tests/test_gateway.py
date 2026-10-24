"""
tests/test_gateway.py
Comprehensive Isolated Unit Test Suite for Laptop 1 (Gateway, Security, Deduplication & Alerts).
Executes in 100% isolation with zero dependency on Laptop 2 (DB) or Laptop 3 (Vision).
"""
import json
import time
from unittest.mock import MagicMock, patch
import fakeredis
import httpx
import pytest
import redis
from fastapi.testclient import TestClient

from app.api.deduplication import DeduplicationService, deduplication_engine
from app.api.notifier import WhatsAppNotifier, whatsapp_notifier
from app.api.security import (
    generate_test_signature,
    validate_hub_signature,
    verify_webhook_subscription,
)
from app.core.config import settings
from app.core.contracts import (
    CELERY_INVOICE_TASK_NAME,
    PriceHikeAlert,
)
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_redis():
    """Provides a fresh in-memory fakeredis instance for each test to isolate cache state."""
    fake_redis_client = fakeredis.FakeRedis(decode_responses=True)
    deduplication_engine.client = fake_redis_client
    yield fake_redis_client


# ============================================================================
# 1. System Health & Main App Tests
# ============================================================================
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_serve_simulator_endpoint():
    response = client.get("/simulator")
    assert response.status_code == 200
    assert "Sahayak" in response.text
    assert "WhatsApp" in response.text


# ============================================================================
# 2. Meta Webhook Verification Handshake (GET /webhook/whatsapp)
# ============================================================================
def test_meta_webhook_verification_success():
    challenge_num = "1158201444"
    response = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
            "hub.challenge": challenge_num,
        },
    )
    assert response.status_code == 200
    assert response.text == challenge_num


def test_meta_webhook_verification_failure_wrong_token():
    response = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_unauthorized_token",
            "hub.challenge": "1158201444",
        },
    )
    assert response.status_code == 403


def test_verify_webhook_subscription_invalid_challenge_type():
    res = verify_webhook_subscription("subscribe", settings.WHATSAPP_VERIFY_TOKEN, "not-a-number")
    assert res is None


# ============================================================================
# 3. HMAC-SHA256 Payload Signature Validation (POST /webhook/whatsapp)
# ============================================================================
def test_meta_hmac_signature_verification_success():
    payload = {
        "merchant_id": "M_TEST_001",
        "sender_phone": "+919876543210",
        "whatsapp_message_id": "wam_test_001",
        "media": {
            "media_id": "med_101",
            "mime_type": "image/jpeg",
            "sha256": "hash_abc_123",
            "file_size": 102400,
        },
        "timestamp": int(time.time()),
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    valid_signature = generate_test_signature(raw_bytes, settings.META_APP_SECRET)

    with patch("app.api.routes.celery_client.send_task") as mock_celery:
        response = client.post(
            "/webhook/whatsapp",
            content=raw_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": valid_signature,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "QUEUED"
        mock_celery.assert_called_once()


def test_meta_hmac_signature_verification_failure_tampered():
    payload = {"merchant_id": "M_TEST_001", "sender_phone": "+919876543210"}
    raw_bytes = json.dumps(payload).encode("utf-8")
    invalid_signature = "sha256=invalid_tampered_hex_digest_999999"

    response = client.post(
        "/webhook/whatsapp",
        content=raw_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": invalid_signature,
        },
    )
    assert response.status_code == 403
    assert "Invalid HMAC signature" in response.json()["detail"]


def test_validate_hub_signature_malformed_header():
    assert validate_hub_signature(b"data", None) is False
    assert validate_hub_signature(b"data", "malformed_prefix_without_sha") is False


# ============================================================================
# 4. Redis Perceptual Media Deduplication (<1ms Drop Test)
# ============================================================================
def test_redis_perceptual_deduplication():
    payload = {
        "merchant_id": "M_KIRANA_007",
        "sender_phone": "+919876543210",
        "whatsapp_message_id": "wam_001",
        "media": {
            "media_id": "med_dup_test",
            "mime_type": "image/jpeg",
            "sha256": "duplicate_image_hash_fixed_value_999",
            "file_size": 204800,
        },
        "timestamp": int(time.time()),
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    signature = generate_test_signature(raw_bytes)

    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature,
    }

    with patch("app.api.routes.celery_client.send_task") as mock_celery:
        # First upload: Must be accepted and queued
        resp1 = client.post("/webhook/whatsapp", content=raw_bytes, headers=headers)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["status"] == "QUEUED"
        assert mock_celery.call_count == 1

        # Second upload with identical media hash: Must be DROPPED
        resp2 = client.post("/webhook/whatsapp", content=raw_bytes, headers=headers)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["status"] == "DUPLICATE_DROPPED"
        assert "latency_ms" in data2
        # Verify Celery was NOT called a second time
        assert mock_celery.call_count == 1


def test_deduplication_helper_methods_and_fallbacks():
    # Test SHA-256 static helper
    digest = DeduplicationService.compute_sha256(b"hello world")
    assert len(digest) == 64

    # Test fallback when client is None
    service_no_client = DeduplicationService(redis_client=None)
    service_no_client.client = None
    is_dup, key = service_no_client.is_duplicate_media("M_001", "hash_xyz")
    assert is_dup is False

    # Test Redis error fail-open handling
    mock_redis = MagicMock()
    mock_redis.set.side_effect = redis.RedisError("Connection refused")
    service_with_error = DeduplicationService(redis_client=mock_redis)
    is_dup2, _ = service_with_error.is_duplicate_media("M_002", "hash_error")
    assert is_dup2 is False


# ============================================================================
# 5. Celery Task Contract & Arguments Validation
# ============================================================================
def test_celery_task_dispatch_contract_args():
    payload = {
        "merchant_id": "M_SURAT_404",
        "sender_phone": "+919123456789",
        "whatsapp_message_id": "wamid.HBgLMTEw...",
        "media": {
            "media_id": "media_bill_fortune_oil",
            "mime_type": "image/jpeg",
            "sha256": "unique_sha256_bill_987",
            "file_size": 512000,
        },
        "timestamp": 1719234000,
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    signature = generate_test_signature(raw_bytes)

    with patch("app.api.routes.celery_client.send_task") as mock_celery:
        response = client.post(
            "/webhook/whatsapp",
            content=raw_bytes,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
        )
        assert response.status_code == 200
        mock_celery.assert_called_once_with(
            CELERY_INVOICE_TASK_NAME,
            kwargs={
                "merchant_id": "M_SURAT_404",
                "media_id": "media_bill_fortune_oil",
                "whatsapp_message_id": "wamid.HBgLMTEw...",
                "sender_phone": "+919123456789",
            },
        )


def test_celery_dispatch_error_resilience():
    payload = {
        "merchant_id": "M_001",
        "sender_phone": "+919876543210",
        "whatsapp_message_id": "wam_001",
        "media": {
            "media_id": "med_err",
            "mime_type": "image/jpeg",
            "sha256": "hash_err",
            "file_size": 1000,
        },
        "timestamp": int(time.time()),
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    signature = generate_test_signature(raw_bytes)

    with patch("app.api.routes.celery_client.send_task", side_effect=Exception("Broker down")):
        response = client.post(
            "/webhook/whatsapp",
            content=raw_bytes,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
        )
        # Should gracefully return queued receipt to acknowledge Meta
        assert response.status_code == 200
        assert response.json()["status"] == "QUEUED"


# ============================================================================
# 6. Meta Raw WhatsApp Cloud API Webhook Format Parser Tests
# ============================================================================
def test_raw_meta_webhook_format_parsing():
    raw_meta_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "100200300",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "999888"},
                            "contacts": [{"wa_id": "919876543210"}],
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.HBgLMTEx...",
                                    "timestamp": "1719234567",
                                    "type": "image",
                                    "image": {
                                        "id": "meta_media_777",
                                        "mime_type": "image/jpeg",
                                        "sha256": "perceptual_hash_777",
                                        "file_size": 150000,
                                    },
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    raw_bytes = json.dumps(raw_meta_payload).encode("utf-8")
    signature = generate_test_signature(raw_bytes)

    with patch("app.api.routes.celery_client.send_task") as mock_celery:
        response = client.post(
            "/webhook/whatsapp",
            content=raw_bytes,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "QUEUED"
        assert data["merchant_id"] == "M_919876543210"
        mock_celery.assert_called_once()


def test_non_actionable_meta_message_ignored():
    status_update_payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "1", "changes": [{"value": {"statuses": [{"status": "read"}]}}]}]
    }
    raw_bytes = json.dumps(status_update_payload).encode("utf-8")
    signature = generate_test_signature(raw_bytes)

    response = client.post(
        "/webhook/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "IGNORED"


def test_malformed_json_bad_request():
    response = client.post(
        "/webhook/whatsapp",
        content=b"not a valid json {{{{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400


# ============================================================================
# 7. Price-Shield Outbound Alert Formatting & Dispatcher Test
# ============================================================================
def test_price_shield_outbound_alert():
    alert_payload = {
        "merchant_id": "M_001",
        "merchant_phone": "+919876543210",
        "item_name": "Fortune Sunflower Oil 1L",
        "old_wholesale_rate": 140.0,
        "new_wholesale_rate": 147.0,
        "percentage_hike": 5.0,
        "previous_mrp": 155.0,
        "suggested_new_mrp": 165.0,
        "estimated_loss_if_unchanged": 350.0,
    }

    # Test alert message formatter
    alert_obj = PriceHikeAlert.model_validate(alert_payload)
    formatted_msg = WhatsAppNotifier.format_alert_message(alert_obj)
    assert "Fortune Sunflower Oil 1L" in formatted_msg
    assert "₹140.00 to ₹147.00" in formatted_msg
    assert "+5.0%" in formatted_msg
    assert "₹165.00" in formatted_msg
    assert "Price-Shield Alert" in formatted_msg

    # Test alert trigger endpoint (mock mode)
    response = client.post("/api/alerts/price-shield", json=alert_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PROCESSED"
    assert data["percentage_hike"] == 5.0
    assert data["dispatch_result"]["status"] in ("mock_delivered", "delivered")


def test_notifier_live_http_success_and_error():
    alert_obj = PriceHikeAlert(
        merchant_id="M_999",
        merchant_phone="+919876543210",
        item_name="Sugar 1kg",
        old_wholesale_rate=40.0,
        new_wholesale_rate=44.0,
        percentage_hike=10.0,
        previous_mrp=45.0,
        suggested_new_mrp=50.0,
        estimated_loss_if_unchanged=200.0,
    )

    # Test live client mock success
    live_notifier = WhatsAppNotifier(api_token="EAAG_live_token_test", phone_number_id="123456")
    mock_http_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"messages": [{"id": "wamid.live.123"}]}
    mock_http_client.post.return_value = mock_response

    res = live_notifier.send_price_shield_alert(alert_obj, client=mock_http_client)
    assert res["status"] == "delivered"

    # Test live client HTTP error handling
    mock_http_client.post.side_effect = httpx.HTTPStatusError("Bad Request", request=MagicMock(), response=MagicMock())
    err_res = live_notifier.send_price_shield_alert(alert_obj, client=mock_http_client)
    assert err_res["status"] == "error"
