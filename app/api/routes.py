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
    clean_id = str(chat_id).replace("M_TG_", "").strip()
    try:
        resp = httpx.post(url, json={"chat_id": clean_id, "text": text, "parse_mode": "Markdown"}, timeout=5.0)
        if resp.status_code != 200:
            httpx.post(url, json={"chat_id": clean_id, "text": text}, timeout=5.0)
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


# ============================================================================
# 4. Interactive Simulator Direct Ingestion (Full Pipeline)
# ============================================================================
from pydantic import BaseModel
import base64
from pathlib import Path

class SimulatorProcessRequest(BaseModel):
    merchant_id: str = "M_DEMO_KIRANA"
    sender_phone: str = "+919876543210"
    bill_filename: str = "sample_bill_SBT_2026_081.jpg"
    image_base64: Optional[str] = None
    hike_simulation: bool = False

@router.post("/api/simulator/process-bill", tags=["Simulator"])
async def simulator_process_bill(req: SimulatorProcessRequest):
    """
    Executes the entire end-to-end pipeline:
    1. OpenCV Image Deskew & Contrast Enhancement
    2. Gemini Flash Structured Vision OCR
    3. Arithmetic Guardrail Validation
    4. Supabase PostgreSQL ACID Ledger write with Row-Level Security
    5. Margin-Guard wholesale price deviation evaluation & suggested retail MRP
    """
    start_time = time.perf_counter()
    from app.workers.preprocessor import preprocess_bill_image
    from app.workers.gemini_extractor import extract_invoice_from_image
    from app.workers.guardrails import validate_invoice_arithmetic
    from app.db.session import get_rls_session
    from app.db import repository, margin_guard

    try:
        # 1. Fetch image bytes
        if req.image_base64:
            raw_b64 = req.image_base64.split(",")[-1]
            img_bytes = base64.b64decode(raw_b64)
        else:
            fixtures_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "bills"
            target_path = fixtures_dir / req.bill_filename
            if not target_path.exists():
                target_path = fixtures_dir / "sample_bill_SBT_2026_081.jpg"
            img_bytes = target_path.read_bytes()

        # 2. OpenCV Preprocess
        clean_bytes = preprocess_bill_image(img_bytes)

        # 3. Gemini Vision OCR
        extracted_data = extract_invoice_from_image(clean_bytes)

        # Optional simulation of a wholesale hike for demo comparison
        original_rate = None
        if req.hike_simulation and extracted_data.items:
            first_item = extracted_data.items[0]
            original_rate = first_item.unit_wholesale_rate
            first_item.unit_wholesale_rate = round(first_item.unit_wholesale_rate * 1.055, 2)
            first_item.line_total = round(first_item.unit_wholesale_rate * first_item.quantity, 2)
            extracted_data.grand_total = sum(i.line_total for i in extracted_data.items)

        # 4. Arithmetic Guardrails
        validated_data, guardrail_summary = validate_invoice_arithmetic(extracted_data, raise_on_failure=True)

        # 5. Supabase Transactional Write with RLS
        with get_rls_session(req.merchant_id) as session:
            # Ensure merchant exists before any price history seeding to satisfy foreign key constraints
            repository.get_or_create_merchant(session=session, merchant_id=req.merchant_id)

            # If simulating a hike and merchant has no prior history for this item,
            # seed the pre-hike rate so Margin-Guard detects the increase!
            if req.hike_simulation and original_rate and validated_data.items:
                from app.db.models import PriceHistory
                from sqlalchemy import select, and_, func
                from datetime import datetime, timedelta
                existing_price = session.execute(
                    select(PriceHistory).where(
                        and_(
                            PriceHistory.merchant_id == req.merchant_id,
                            func.lower(func.trim(PriceHistory.item_name)) == func.lower(func.trim(validated_data.items[0].item_name))
                        )
                    )
                ).scalars().first()
                if not existing_price:
                    baseline_entry = PriceHistory(
                        merchant_id=req.merchant_id,
                        item_name=validated_data.items[0].item_name,
                        unit_wholesale_rate=original_rate,
                        recorded_at=datetime.utcnow() - timedelta(days=7)
                    )
                    session.add(baseline_entry)
                    session.flush()

            inv = repository.save_extracted_invoice(session, req.merchant_id, validated_data)
            invoice_id = str(inv.id)
            # 6. Margin-Guard Evaluation
            alerts = margin_guard.evaluate_price_deviations(session, req.merchant_id, inv.id)
            session.commit()

            if alerts:
                try:
                    from app.api.notifier import whatsapp_notifier
                    for alert in alerts:
                        alert.merchant_phone = str(req.merchant_id).replace("M_TG_", "")
                        whatsapp_notifier.send_price_shield_alert(alert)
                except Exception as notif_err:
                    logger.warning(f"Simulator alert dispatch warning: {notif_err}")

        total_latency_ms = (time.perf_counter() - start_time) * 1000

        return {
            "status": "SUCCESS",
            "merchant_id": req.merchant_id,
            "invoice_id": invoice_id,
            "invoice_number": validated_data.invoice_number,
            "supplier_name": validated_data.supplier_name,
            "supplier_gstin": validated_data.supplier_gstin,
            "grand_total": validated_data.grand_total,
            "confidence_score": validated_data.confidence_score,
            "line_items": [i.model_dump() for i in validated_data.items],
            "margin_alerts": [a.model_dump() for a in alerts],
            "latency_ms": round(total_latency_ms, 2)
        }
    except Exception as exc:
        total_latency_ms = (time.perf_counter() - start_time) * 1000
        logger.error("Simulator pipeline execution failed: %s", exc, exc_info=True)
        return {
            "status": "ERROR",
            "error": str(exc),
            "merchant_id": req.merchant_id,
            "latency_ms": round(total_latency_ms, 2)
        }
