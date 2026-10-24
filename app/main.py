"""
app/main.py
FastAPI application entrypoint for Sahayak Phase 1 Gateway.
Features:
- Dual Ingestion: WhatsApp Webhook & Telegram Bot API
- Embedded Background Long-Polling for Telegram (Zero Ngrok/Tunnel required!)
- Microsecond Redis Deduplication Engine (<1ms)
- Interactive Simulator & Swagger Docs
"""
import asyncio
from contextlib import asynccontextmanager
import logging
import os
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import httpx

from app.api.deduplication import deduplication_engine
from app.api.routes import router as api_router, send_telegram_text
from app.core.config import settings
from app.core.contracts import CELERY_INVOICE_TASK_NAME

# Configure structured logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sahayak.main")

# Background polling task handle
polling_task = None


async def telegram_long_poll_worker():
    """
    Background worker that continuously pulls updates from Telegram.
    Allows testing live on your mobile phone without needing any public IP or ngrok!
    """
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN.startswith("mock_"):
        logger.info("Telegram polling disabled (mock token).")
        return

    logger.info("Telegram Long-Polling started for @sahayak_retail_bot!")
    offset = None
    url = f"{settings.TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates"

    async with httpx.AsyncClient(timeout=35.0) as client:
        while True:
            try:
                params = {"timeout": 30}
                if offset:
                    params["offset"] = offset

                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        message = update.get("message", {})
                        chat_id = message.get("chat", {}).get("id")
                        if not chat_id:
                            continue

                        photos = message.get("photo", [])
                        document = message.get("document")

                        if photos:
                            best_photo = photos[-1]
                            media_id = best_photo.get("file_id")
                            media_hash = best_photo.get("file_unique_id")
                        elif document and document.get("mime_type", "").startswith("image/"):
                            media_id = document.get("file_id")
                            media_hash = document.get("file_unique_id")
                        else:
                            text = message.get("text", "").strip()
                            if text:
                                if text.startswith("/simulate") or text.startswith("/test") or text.startswith("/hike"):
                                    send_telegram_text(
                                        chat_id,
                                        "⚡ *Running Price-Shield Margin Simulation...*\nAnalyzing wholesale bill `sample_bill_SBT_2026_082_hike.jpg` against baseline wholesale history..."
                                    )
                                    async def _sim_tg(c_id):
                                        try:
                                            from app.workers.tasks import process_invoice_task
                                            res = await asyncio.to_thread(
                                                process_invoice_task,
                                                merchant_id=f"M_TG_{c_id}",
                                                media_id="sample_bill_SBT_2026_082_hike.jpg",
                                                whatsapp_message_id=f"tg_sim_{c_id}_{int(time.time())}",
                                                sender_phone=str(c_id)
                                            )
                                            alerts_cnt = res.get('alerts_count', 0)
                                            send_telegram_text(
                                                c_id,
                                                f"✅ *Test Invoice {res.get('invoice_number', 'Digitized')} Logged!*\n\n"
                                                f"📦 *Items Extracted:* {res.get('items_count', 0)} line items\n"
                                                f"💰 *Grand Total:* ₹{res.get('grand_total', 0):,.2f}\n"
                                                f"🛡️ *Alerts Detected:* {alerts_cnt}"
                                            )
                                            margin_alerts = res.get('margin_alerts', [])
                                            for a_dict in margin_alerts:
                                                try:
                                                    from app.core.contracts import PriceHikeAlert
                                                    from app.api.notifier import AlertNotifier
                                                    a_obj = PriceHikeAlert.model_validate(a_dict)
                                                    alert_text = AlertNotifier.format_alert_message(a_obj)
                                                    send_telegram_text(c_id, alert_text)
                                                except Exception as a_err:
                                                    logger.warning(f"Could not format alert: {a_err}")
                                        except Exception as err:
                                            logger.error(f"Telegram simulation error: {err}")
                                            send_telegram_text(c_id, f"⚠️ Simulation error: {err}")
                                    asyncio.create_task(_sim_tg(chat_id))
                                    continue
                                elif text.startswith("/start") or text.startswith("/help"):
                                    send_telegram_text(
                                        chat_id,
                                        "✨ *Namaste! Welcome to Sahayak (सहायक)*\n\n"
                                        "I am your AI retail copilot.\n"
                                        "📸 *Snap & send a photo* of any wholesale invoice to automatically:\n"
                                        " • Digitize FMCG items with Gemini Flash Vision\n"
                                        " • Audit GST & line-item arithmetic\n"
                                        " • Trigger *Price-Shield Alerts* if wholesale costs increase\n\n"
                                        "💡 *Quick Test:* Send `/simulate` to test an instant price-spike alert!"
                                    )
                                    continue
                                else:
                                    send_telegram_text(
                                        chat_id,
                                        "📸 Please send a photo of your *wholesale paper invoice*, or reply `/simulate` to test a live Price-Shield alert!"
                                    )
                                    continue
                            continue

                        # Process bill photo
                        merchant_id = f"M_TG_{chat_id}"
                        is_dup, key = deduplication_engine.is_duplicate_media(merchant_id, media_hash)
                        if is_dup:
                            send_telegram_text(
                                chat_id,
                                "🛡️ *Duplicate Dropped (<1ms)*\nYou already uploaded this invoice earlier. Duplicate skipped!"
                            )
                        else:
                            send_telegram_text(
                                chat_id,
                                "⏳ *Bill Photo Received!*\n"
                                "Deciphering Indian FMCG line items via Gemini Flash Vision & calculating margin impact..."
                            )
                            logger.info(f"Queued bill from Telegram chat {chat_id}: media_id={media_id}")

                            async def _process_tg(m_id, med_id, m_hash, c_id):
                                try:
                                    from app.workers.tasks import process_invoice_task
                                    res = await asyncio.to_thread(
                                        process_invoice_task,
                                        merchant_id=m_id,
                                        media_id=med_id,
                                        whatsapp_message_id=f"tg_{m_hash}",
                                        sender_phone=str(c_id)
                                    )
                                    alerts_cnt = res.get('alerts_count', 0)
                                    mg_status = (
                                        f"🛡️ *Margin-Guard:* 🚨 *{alerts_cnt} Price Spike Alert(s) Detected!* Shelf recommendations dispatched."
                                        if alerts_cnt > 0
                                        else "🛡️ *Margin-Guard:* Rates stable (<3% change). Margins protected."
                                    )
                                    send_telegram_text(
                                        c_id,
                                        f"✅ *Invoice {res.get('invoice_number', 'Digitized')} Logged!*\n\n"
                                        f"📦 *Items Extracted:* {res.get('items_count', 0)} line items\n"
                                        f"💰 *Grand Total:* ₹{res.get('grand_total', 0):,.2f}\n"
                                        f"🔒 *Ledger Status:* Stored securely in Supabase PostgreSQL (RLS Active)\n"
                                        f"{mg_status}"
                                    )
                                    margin_alerts = res.get('margin_alerts', [])
                                    for a_dict in margin_alerts:
                                        try:
                                            from app.core.contracts import PriceHikeAlert
                                            from app.api.notifier import AlertNotifier
                                            a_obj = PriceHikeAlert.model_validate(a_dict)
                                            alert_text = AlertNotifier.format_alert_message(a_obj)
                                            send_telegram_text(c_id, alert_text)
                                        except Exception as a_err:
                                            logger.warning(f"Could not format alert: {a_err}")
                                except Exception as exc:
                                    logger.error(f"Error processing Telegram invoice: {exc}")
                                    send_telegram_text(c_id, f"⚠️ Note: Invoice processed with note: {exc}")

                            asyncio.create_task(_process_tg(merchant_id, media_id, media_hash, chat_id))
                elif response.status_code == 409:
                    logger.warning("Telegram getUpdates 409 conflict. Waiting 4s for previous session to close...")
                    await asyncio.sleep(4.0)
                else:
                    logger.warning(f"Telegram getUpdates returned status {response.status_code}. Sleeping 3s...")
                    await asyncio.sleep(3.0)
            except asyncio.CancelledError:
                logger.info("Telegram polling worker cancelled.")
                break
            except Exception as e:
                logger.debug(f"Telegram polling loop exception: {e}")
                await asyncio.sleep(3.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global polling_task
    logger.info(f"Starting {settings.APP_NAME} in [{settings.ENVIRONMENT}] mode...")
    if settings.ENABLE_TELEGRAM_POLLING and not settings.TELEGRAM_BOT_TOKEN.startswith("mock_"):
        polling_task = asyncio.create_task(telegram_long_poll_worker())
    yield
    if polling_task:
        polling_task.cancel()
    logger.info(f"Shutting down {settings.APP_NAME}...")


app = FastAPI(
    title="Sahayak (सहायक) - Gateway & Ingest API",
    description="High-Speed Ingestion (WhatsApp & Telegram), Sub-Millisecond Deduplication & Price-Shield Margin Alerting",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(api_router)

# Pluggable Phase 2 Counter Router (Zero-Conflict Protocol)
try:
    from app.api.counter import counter_router
    app.include_router(counter_router)
except ImportError:
    pass

# Mount simulator directory if exists
SIMULATOR_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "simulator")
if os.path.exists(SIMULATOR_DIR):
    @app.get("/simulator", tags=["Simulator"], response_class=FileResponse)
    async def serve_simulator():
        index_path = os.path.join(SIMULATOR_DIR, "index.html")
        return FileResponse(index_path)

    @app.get("/counter", tags=["Simulator"], response_class=FileResponse)
    async def serve_counter_pos():
        counter_path = os.path.join(SIMULATOR_DIR, "counter.html")
        return FileResponse(counter_path)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
