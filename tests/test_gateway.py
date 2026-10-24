"""
tests/test_gateway.py
Comprehensive Isolated Unit Test Suite for Laptop 1 (Gateway, Security, Deduplication & Alerts).
Supports both Meta WhatsApp and Telegram Bot API.
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
from app.api.notifier import AlertNotifier, WhatsAppNotifier, whatsapp_notifier
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
    assert "active_channel" in data


def test_serve_simulator_endpoint():
    response = client.get("/simulator")
    assert response.status_code == 200
    assert "Sahayak" in response.text


# ============================================================================
# 2. Telegram Webhook & Ingestion Tests
# ============================================================================
def test_telegram_webhook_photo_ingestion():
    telegram_payload = {
        "update_id": 9991,
        "message": {
            "message_id": 101,
            "chat": {"id": 12345678, "type": "private"},
            "date": 1719234000,
            "photo": [
                {"file_id": "thumb_123", "file_unique_id": "uniq_thumb_123", "file_size": 1000},
                {"file_id": "highres_123", "file_unique_id": "uniq_highres_123", "file_size": 200000},
            ],
            "caption": "today supplier bill"
        }
    }

    with patch("app.api.routes.celery_client.send_task") as mock_celery, \
         patch("app.api.routes.send_telegram_text") as mock_send_reply:
        resp = client.post("/webhook/telegram", json=telegram_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "QUEUED"
        assert data["merchant_id"] == "M_TG_12345678"
        mock_celery.assert_called_once()
        mock_send_reply.assert_called_once()


def test_telegram_webhook_deduplication():
    telegram_payload = {
        "update_id": 9992,
        "message": {
            "message_id": 102,
            "chat": {"id": 888777, "type": "private"},
            "date": 1719234000,
            "photo": [
                {"file_id": "bill_file_dup", "file_unique_id": "fixed_dup_unique_hash", "file_size": 150000}
            ]
        }
    }

    with patch("app.api.routes.celery_client.send_task") as mock_celery, \
         patch("app.api.routes.send_telegram_text"):
        # First upload
        resp1 = client.post("/webhook/telegram", json=telegram_payload)
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "QUEUED"
        assert mock_celery.call_count == 1

        # Duplicate upload
        resp2 = client.post("/webhook/telegram", json=telegram_payload)
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "DUPLICATE_DROPPED"
        assert mock_celery.call_count == 1  # Not called again!


def test_telegram_webhook_start_command():
    payload = {
        "update_id": 9993,
        "message": {
            "message_id": 103,
            "chat": {"id": 112233, "type": "private"},
            "text": "/start"
        }
    }
    with patch("app.api.routes.send_telegram_text") as mock_send:
        resp = client.post("/webhook/telegram", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ACK"
        mock_send.assert_called_once()


# ============================================================================
# 3. Meta Webhook Verification Handshake (GET /webhook/whatsapp)
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


# ============================================================================
# 4. HMAC-SHA256 Payload Signature Validation (POST /webhook/whatsapp)
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


# ============================================================================
# 5. Price-Shield Outbound Alert Formatting & Dispatcher Test
# ============================================================================
def test_price_shield_outbound_alert():
    alert_payload = {
        "merchant_id": "M_001",
        "merchant_phone": "12345678",
        "item_name": "Fortune Sunflower Oil 1L",
        "old_wholesale_rate": 140.0,
        "new_wholesale_rate": 147.0,
        "percentage_hike": 5.0,
        "previous_mrp": 155.0,
        "suggested_new_mrp": 165.0,
        "estimated_loss_if_unchanged": 350.0,
    }

    alert_obj = PriceHikeAlert.model_validate(alert_payload)
    formatted_msg = AlertNotifier.format_alert_message(alert_obj)
    assert "Fortune Sunflower Oil 1L" in formatted_msg
    assert "₹140.00 to ₹147.00" in formatted_msg
    assert "+5.0%" in formatted_msg

    with patch("app.api.notifier.AlertNotifier.send_telegram_alert") as mock_tg:
        mock_tg.return_value = {"status": "mock_delivered", "recipient": "12345678"}
        response = client.post("/api/alerts/price-shield", json=alert_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PROCESSED"
        assert data["percentage_hike"] == 5.0
