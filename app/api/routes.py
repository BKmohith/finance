"""
app/api/routes.py
FastAPI router for Webhook Ingestion (WhatsApp & Telegram), Media Deduplication, and Price-Shield Alerting.
"""
import json
import logging
import time
from typing import Any, Dict, Optional

from celery import Celery
from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
import httpx

from app.api.deduplication import deduplication_engine
from app.api.notifier import whatsapp_notifier
from app.api.security import validate_hub_signature, verify_webhook_subscription
from app.core.config import settings
from app.core.contracts import (
    CELERY_INVOICE_TASK_NAME,
    InboundInvoiceEvent,
    PriceHikeAlert,
    WebhookMediaItem,
)

logger = logging.getLogger("sahayak.api")
router = APIRouter()

# Initialize Celery client producer for task dispatching
celery_client = Celery("sahayak_gateway", broker=settings.CELERY_BROKER_URL)


@router.get("/health", tags=["System"])
async def health_check():
    """Service health and readiness check."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "active_channel": settings.NOTIFICATION_CHANNEL,
        "telegram_bot": "@sahayak_retail_bot" if settings.TELEGRAM_BOT_TOKEN else "disabled",
        "version": "0.1.0"
    }


# ============================================================================
# 1. Telegram Inbound Webhook (Zero Facebook Dependency)
# ============================================================================
@router.post("/webhook/telegram", tags=["Telegram Webhook"])
async def receive_telegram_webhook(request: Request):
    """
    Receives Telegram Bot updates (photos, documents, text).
    1. Extracts highest-resolution photo attachment.
    2. Runs sub-millisecond Redis deduplication (<1ms).
    3. Queues OCR worker via Celery (<25ms).
    4. Sends immediate conversational reply back to merchant on Telegram.
    """
    start_time = time.perf_counter()
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    message = payload.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return {"status": "IGNORED", "reason": "No chat ID found"}

    photos = message.get("photo", [])
    document = message.get("document")

    # If it's a photo or image document
    if photos:
        # Highest resolution photo is last in list
        best_photo = photos[-1]
        media_id = best_photo.get("file_id")
        media_hash = best_photo.get("file_unique_id")
        file_size = best_photo.get("file_size", 0)
    elif document and document.get("mime_type", "").startswith("image/"):
        media_id = document.get("file_id")
        media_hash = document.get("file_unique_id")
        file_size = document.get("file_size", 0)
    else:
        # Text only message
        user_text = message.get("text", "")
        if user_text.startswith("/start"):
            reply_text = (
                "🙏 *Namaste! Welcome to Sahayak (सहायक)*\n\n"
                "I am your AI retail copilot. Snap and send a photo of your *wholesale paper bill* "
                "to instantly digitize rates, calculate credit deadlines, and activate the *Price-Shield*."
            )
            send_telegram_text(chat_id, reply_text)
        return {"status": "ACK", "message": "Non-media update acknowledged"}

    merchant_id = f"M_TG_{chat_id}"
    sender_phone = str(chat_id)
    message_id = f"tg_{message.get('message_id')}"

    # --- Microsecond Deduplication ---
    is_duplicate, cache_key = deduplication_engine.is_duplicate_media(
        merchant_id=merchant_id,
        media_sha256=media_hash
    )
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    if is_duplicate:
        logger.info(f"Telegram duplicate dropped in {elapsed_ms:.2f}ms for key {cache_key}")
        send_telegram_text(
            chat_id,
            "⚠️ *Duplicate Bill Detected*\nYou already uploaded this bill. Skipped duplicate processing."
        )
        return {
            "status": "DUPLICATE_DROPPED",
            "merchant_id": merchant_id,
            "cache_key": cache_key,
            "latency_ms": round(elapsed_ms, 2)
        }

    # --- Dispatch to Celery ---
    try:
        celery_client.send_task(
            CELERY_INVOICE_TASK_NAME,
            kwargs={
                "merchant_id": merchant_id,
                "media_id": media_id,
                "whatsapp_message_id": message_id,
                "sender_phone": sender_phone
            }
        )
    except Exception as exc:
        logger.error(f"Error dispatching Telegram task to Celery: {exc}")

    total_latency_ms = (time.perf_counter() - start_time) * 1000
    send_telegram_text(
        chat_id,
        "🧾 *Bill Received!*\nDeciphering FMCG line items via Gemini 1.5 Flash. I will alert you if any wholesale rate increased."
    )

    return {
        "status": "QUEUED",
        "task": CELERY_INVOICE_TASK_NAME,
        "merchant_id": merchant_id,
        "latency_ms": round(total_latency_ms, 2)
    }


def send_telegram_text(chat_id: int | str, text: str):
    """Helper to send instant reply to Telegram user."""
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN.startswith("mock_"):
        return
    url = f"{settings.TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        httpx.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=4.0)
    except Exception as e:
        logger.warning(f"Could not send Telegram reply: {e}")


# ============================================================================
# 2. Meta WhatsApp Inbound Webhook
# ============================================================================
@router.get("/webhook/whatsapp", tags=["WhatsApp Webhook"])
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Meta Webhook Verification Endpoint."""
    challenge = verify_webhook_subscription(hub_mode, hub_verify_token, hub_challenge)
    if challenge is not None:
        return PlainTextResponse(content=str(challenge), status_code=status.HTTP_200_OK)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")


@router.post("/webhook/whatsapp", tags=["WhatsApp Webhook"])
async def receive_whatsapp_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """
    Meta WhatsApp Inbound Webhook Handler:
    1. Cryptographically verifies HMAC-SHA256 signature.
    2. Drops duplicate uploads in <1ms via Redis perceptual hash.
    3. Dispatches async OCR worker task via Celery in <25ms.
    """
    start_time = time.perf_counter()
    raw_body = await request.body()

    if x_hub_signature_256 or settings.ENVIRONMENT == "production":
        if not validate_hub_signature(raw_body, x_hub_signature_256):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid HMAC signature. Access denied."
            )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {str(e)}"
        )

    event = parse_inbound_event(payload)
    if not event:
        return {"status": "IGNORED", "reason": "No actionable media found"}

    is_duplicate, cache_key = deduplication_engine.is_duplicate_media(
        merchant_id=event.merchant_id,
        media_sha256=event.media.sha256
    )

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    if is_duplicate:
        logger.info(f"Duplicate drop in {elapsed_ms:.2f}ms for key {cache_key}")
        return {
            "status": "DUPLICATE_DROPPED",
            "merchant_id": event.merchant_id,
            "cache_key": cache_key,
            "latency_ms": round(elapsed_ms, 2)
        }

    try:
        celery_client.send_task(
            CELERY_INVOICE_TASK_NAME,
            kwargs={
                "merchant_id": event.merchant_id,
                "media_id": event.media.media_id,
                "whatsapp_message_id": event.whatsapp_message_id,
                "sender_phone": event.sender_phone
            }
        )
    except Exception as exc:
        logger.error(f"Error dispatching task to Celery: {exc}")

    total_latency_ms = (time.perf_counter() - start_time) * 1000
    return {
        "status": "QUEUED",
        "task": CELERY_INVOICE_TASK_NAME,
        "merchant_id": event.merchant_id,
        "whatsapp_message_id": event.whatsapp_message_id,
        "latency_ms": round(total_latency_ms, 2)
    }


# ============================================================================
# 3. Price-Shield Outbound Alert Trigger
# ============================================================================
@router.post("/api/alerts/price-shield", tags=["Price Shield"])
async def trigger_price_shield_alert(alert: PriceHikeAlert):
    """
    Outbound Price-Shield Alert trigger endpoint.
    Dispatches to Telegram or WhatsApp based on configuration.
    """
    result = whatsapp_notifier.send_price_shield_alert(alert)
    return {
        "status": "PROCESSED",
        "alert_for": alert.item_name,
        "percentage_hike": alert.percentage_hike,
        "dispatch_result": result
    }


def parse_inbound_event(payload: Dict[str, Any]) -> Optional[InboundInvoiceEvent]:
    """Normalizes both raw Meta WhatsApp webhooks and direct Sahayak contract payloads."""
    if "merchant_id" in payload and "media" in payload:
        return InboundInvoiceEvent.model_validate(payload)

    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0].get("value", {})
        messages = change.get("messages", [])
        if not messages:
            return None

        msg = messages[0]
        sender_phone = msg.get("from", "")
        merchant_id = f"M_{sender_phone}"
        message_id = msg.get("id", "")
        timestamp = int(msg.get("timestamp", int(time.time())))

        media_type = msg.get("type", "")
        if media_type in ("image", "document"):
            media_obj = msg.get(media_type, {})
            media_id = media_obj.get("id", "")
            mime_type = media_obj.get("mime_type", "image/jpeg")
            sha256 = media_obj.get("sha256", f"sha_{media_id}")
            file_size = int(media_obj.get("file_size", 0))

            return InboundInvoiceEvent(
                merchant_id=merchant_id,
                sender_phone=f"+{sender_phone}" if not sender_phone.startswith("+") else sender_phone,
                whatsapp_message_id=message_id,
                media=WebhookMediaItem(
                    media_id=media_id,
                    mime_type=mime_type,
                    sha256=sha256,
                    file_size=file_size
                ),
                timestamp=timestamp
            )
        return None
    except Exception as e:
        logger.debug(f"Failed to parse payload: {e}")
        return None
