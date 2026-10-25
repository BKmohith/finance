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
import re
import time
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import httpx

from app.api.deduplication import deduplication_engine
from app.api.routes import (
    router as api_router,
    send_telegram_text,
    edit_telegram_text,
    send_telegram_chat_action
)
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


async def download_telegram_file(file_id: str) -> Optional[bytes]:
    """Downloads an audio or image file directly from Telegram servers."""
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN.startswith("mock_"):
        return None
    url = f"{settings.TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/getFile"
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(url, params={"file_id": file_id})
            if resp.status_code == 200:
                file_path = resp.json().get("result", {}).get("file_path")
                if file_path:
                    dl_url = f"{settings.TELEGRAM_API_BASE}/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}"
                    dl_resp = await client.get(dl_url)
                    if dl_resp.status_code == 200:
                        return dl_resp.content
    except Exception as e:
        logger.warning(f"Failed to download Telegram file {file_id}: {e}")
    return None


from app.services.bot_service import format_counter_sale_receipt


def get_merchant_id_for_chat(chat_id: int | str) -> Optional[str]:
    """Resolves Telegram chat_id to Supabase Merchant ID, or None if unregistered."""
    from app.db.repository import get_registered_merchant_for_chat
    m = get_registered_merchant_for_chat(chat_id)
    return m["id"] if m else None


async def telegram_long_poll_worker():
    """
    Background worker that continuously pulls updates from Telegram.
    Supports:
    1. Wholesale Invoices (Photos & PDF/Images) with Gemini Flash Vision + Margin-Guard
    2. Speech Bot / Vernacular Voice Notes (Kannada, Hindi, Hinglish) via Sarvam AI STT + Jev Router
    3. Counter Sales (Text Shorthand & Voice) with Agent 4 FIFO Stock Depletion
    4. Customer Khata (Udhaar given & repayments collected)
    5. Quick commands: /stock, /khata, /simulate, /help
    """
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN.startswith("mock_"):
        logger.info("Telegram polling disabled (mock token).")
        return

    logger.info("Telegram Long-Polling started for @sahayak_retail_bot (All Phase 2 Features Active)!")

    # Register official bot commands menu in Telegram UI
    try:
        cmd_url = f"{settings.TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/setMyCommands"
        bot_commands = [
            {"command": "start", "description": "Welcome & Store Status"},
            {"command": "login", "description": "Authenticate store (Merchant ID)"},
            {"command": "logout", "description": "Lock & sign out of store"},
            {"command": "whoami", "description": "View active store profile"},
            {"command": "margin", "description": "Agent 1: Price-Hike Defense (Pure SQL)"},
            {"command": "stock", "description": "Agent 2: Shelf Stock & Locked Capital (Pure SQL)"},
            {"command": "liquidity", "description": "Agent 3: Cash, Udhaar & Payables (Pure SQL)"},
            {"command": "closing", "description": "Agent 6: 10:15 PM Closing Debrief (LLM)"},
            {"command": "whatif", "description": "Agent 7: What-If Stress Simulator (LLM)"},
            {"command": "khata", "description": "Active Customer Udhaar Ledger"},
            {"command": "simulate", "description": "Test Live Price-Shield Simulation"},
            {"command": "help", "description": "Overview of Sahayak Copilot"}
        ]
        async with httpx.AsyncClient(timeout=10.0) as init_client:
            await init_client.post(cmd_url, json={"commands": bot_commands})
        logger.info("Telegram bot commands menu registered successfully.")
    except Exception as e:
        logger.warning(f"Could not register Telegram commands: {e}")

    offset = None
    url = f"{settings.TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates"

    async def _periodic_chat_action(c_id: int | str, action: str = "typing"):
        """Maintains the Telegram top-bar status (typing/upload_document) every 4s until cancelled."""
        try:
            while True:
                send_telegram_chat_action(c_id, action)
                await asyncio.sleep(4.0)
        except asyncio.CancelledError:
            pass

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

                        text = message.get("text", "").strip()
                        photos = message.get("photo", [])
                        document = message.get("document")
                        voice = message.get("voice")
                        audio = message.get("audio")

                        contact = message.get("contact")

                        # ----------------------------------------------------
                        # A. ACCOUNT LINKING & UNLINKING (Deep-link & Commands)
                        # ----------------------------------------------------
                        is_link_cmd = False
                        target_m_id = None

                        # 1. Contact Card Share (e.g. user taps Share Contact)
                        if contact and contact.get("phone_number"):
                            is_link_cmd = True
                            target_m_id = contact.get("phone_number")

                        # 2. Text command parsing (/start M_..., /link M_..., M_..., 10-digit phone)
                        elif text:
                            parts = text.split()
                            cmd = parts[0].lower() if parts else ""

                            # /start M_... or /link M_... or /login M_... or connect M_...
                            if cmd in ("/start", "/link", "/login", "/auth", "/activate", "/register", "link", "login", "auth", "activate", "connect", "register") and len(parts) > 1:
                                is_link_cmd = True
                                target_m_id = parts[1].strip()
                            elif cmd.startswith(("/start_", "/link_", "/login_")):
                                is_link_cmd = True
                                target_m_id = cmd.split("_", 1)[1].strip()
                            # Direct Merchant ID pattern: M_XXXX_YYYY
                            elif re.search(r"\bM_[A-Za-z0-9_]+\b", text, re.IGNORECASE):
                                is_link_cmd = True
                                target_m_id = re.search(r"\bM_[A-Za-z0-9_]+\b", text, re.IGNORECASE).group(0).strip()
                            # 10-digit Indian phone number: 9845012345 or +919845012345
                            elif re.search(r"\b(?:\+91|91)?([6-9]\d{9})\b", text):
                                is_link_cmd = True
                                target_m_id = re.search(r"\b(?:\+91|91)?([6-9]\d{9})\b", text).group(1).strip()

                        if is_link_cmd and target_m_id:
                            from app.db.repository import link_chat_to_merchant
                            linked_merchant = link_chat_to_merchant(chat_id, target_m_id)
                            if linked_merchant:
                                welcome_msg = (
                                    f"🎉 *Store Account Connected!*\n\n"
                                    f"🏪 *Store:* {linked_merchant['name']}\n"
                                    f"🆔 *Merchant ID:* `{linked_merchant['id']}`\n"
                                    f"📍 *Location:* {linked_merchant.get('city') or 'Bengaluru'}\n"
                                    f"🔒 *Ledger Security:* 100% Private ACID Store Ledger Active\n\n"
                                    f"Welcome! Only you can view or manage this store's listings and Khata.\n\n"
                                    f"*Quick Start Actions:*\n"
                                    f" • 🎙️ *Voice Note:* Speak _\"Sharma ji 500 udhaar\"_\n"
                                    f" • 📸 *Wholesale Bill:* Send photo of distributor invoice\n"
                                    f" • 💵 *Record Sale:* _\"28 units sunflower oil 8000\"_\n"
                                    f" • 📊 *Daily Report:* _\"create report of the day\"_\n"
                                    f" • 📦 *Shelf Stock:* `/stock`\n"
                                    f" • 🔒 *Sign Out:* `/logout`"
                                )
                                send_telegram_text(chat_id, welcome_msg)
                            else:
                                err_msg = (
                                    f"❌ *Store Not Found for:* `{target_m_id}`\n\n"
                                    f"Please check your Merchant ID or registered phone number from: http://localhost:8000/login.html\n\n"
                                    f"Once checked, reply with: `/login <YOUR_MERCHANT_ID>`"
                                )
                                send_telegram_text(chat_id, err_msg)
                            continue

                        # Check /logout or /unlink command
                        if text and text.lower() in ("/logout", "logout", "/unlink", "unlink", "/exit", "exit", "/signout", "signout"):
                            from app.db.repository import unlink_chat_from_merchant, get_registered_merchant_for_chat
                            if get_registered_merchant_for_chat(chat_id):
                                unlink_chat_from_merchant(chat_id)
                                send_telegram_text(
                                    chat_id,
                                    "🔒 *Logged Out Successfully*\n\n"
                                    "Your Telegram account has been disconnected and your store ledger is now locked.\n\n"
                                    "🔑 *To Log In Again:*\n"
                                    "Reply with your **Merchant ID** (e.g. `M_MOHITH_A5AN`) or your registered 10-digit phone number."
                                )
                            else:
                                send_telegram_text(chat_id, "ℹ️ You are not currently logged into any store.")
                            continue

                        # Check /whoami or /myaccount or /profile command
                        if text and text.lower() in ("/whoami", "/myaccount", "/profile", "/status"):
                            from app.db.repository import get_registered_merchant_for_chat
                            current_m = get_registered_merchant_for_chat(chat_id)
                            if current_m:
                                send_telegram_text(
                                    chat_id,
                                    f"🏪 *Linked Store Account*\n\n"
                                    f"• Store: *{current_m['name']}*\n"
                                    f"• Merchant ID: `{current_m['id']}`\n"
                                    f"• Phone: {current_m.get('phone') or 'N/A'}\n"
                                    f"• City: {current_m.get('city') or 'N/A'}\n"
                                    f"• Isolation: Dedicated Tenant Database Ledger (RLS Active)\n\n"
                                    f"👉 To switch stores, reply with `/login <NEW_MERCHANT_ID>`\n"
                                    f"👉 To log out, send `/logout`."
                                )
                            else:
                                send_telegram_text(chat_id, "⛔ Your Telegram account is not logged into any store.\nReply with your **Merchant ID** to authenticate.")
                            continue

                        # Check /login or /auth command alone without arguments
                        if text and text.lower() in ("/login", "login", "/auth", "auth", "/connect", "connect"):
                            from app.db.repository import get_registered_merchant_for_chat
                            current_m = get_registered_merchant_for_chat(chat_id)
                            if current_m:
                                send_telegram_text(
                                    chat_id,
                                    f"🏪 *Already Logged In*\n\n"
                                    f"You are connected to *{current_m['name']}* (`{current_m['id']}`).\n\n"
                                    f"👉 To switch stores, reply with: `/login <NEW_MERCHANT_ID>`\n"
                                    f"👉 To log out, send `/logout`."
                                )
                            else:
                                send_telegram_text(
                                    chat_id,
                                    "🔑 *Store Authentication Required*\n\n"
                                    "Please reply with your **Merchant ID** (e.g. `M_MOHITH_A5AN`) or your **registered 10-digit phone number** to log into your store."
                                )
                            continue

                        # Check /start command alone
                        if text and text.lower() in ("/start", "start"):
                            from app.db.repository import get_registered_merchant_for_chat
                            current_m = get_registered_merchant_for_chat(chat_id)
                            if current_m:
                                welcome_back = (
                                    f"👋 *Namaste, {current_m['name']}!*\n\n"
                                    f"🏪 *Active Store:* {current_m['name']} (`{current_m['id']}`)\n"
                                    f"🔒 *Ledger Security:* 100% Private ACID Store Ledger Active\n\n"
                                    f"*Quick Actions:*\n"
                                    f" • 🎙️ *Voice Note:* Speak _\"Sharma ji 500 udhaar\"_\n"
                                    f" • 📸 *Wholesale Bill:* Send photo of distributor invoice\n"
                                    f" • 💵 *Record Sale:* _\"28 units sunflower oil 8000\"_\n"
                                    f" • 📊 *Daily Report:* _\"create report of the day\"_\n"
                                    f" • 📦 *Shelf Stock:* `/stock`\n"
                                    f" • 🔒 *Sign Out:* `/logout`"
                                )
                                send_telegram_text(chat_id, welcome_back)
                            else:
                                auth_prompt = (
                                    "👋 *Namaste! Welcome to Sahayak (सहायक) Retail Copilot*\n\n"
                                    "I am your autonomous store manager for counter sales, customer Udhaar, and wholesale pricing.\n\n"
                                    "🔐 *Authentication Required:*\n"
                                    "To access your store's private ledger, please authenticate.\n\n"
                                    "👉 Reply with your **Merchant ID** (e.g. `M_MOHITH_A5AN`) or your **registered 10-digit phone number**.\n\n"
                                    "🌐 Don't have a store ID yet? Register at: http://localhost:8000/login.html"
                                )
                                send_telegram_text(chat_id, auth_prompt)
                            continue

                        # ----------------------------------------------------
                        # B. GATEKEEPER: BLOCK UNREGISTERED / UNAUTHENTICATED CHATS
                        # ----------------------------------------------------
                        from app.db.repository import get_registered_merchant_for_chat
                        merchant_info = get_registered_merchant_for_chat(chat_id)
                        if not merchant_info:
                            access_denied_msg = (
                                "⛔ *Authentication Required*\n\n"
                                "Your Telegram chat is not logged into any Sahayak retail ledger.\n\n"
                                "🔑 *How to Authenticate:*\n"
                                "1️⃣ Find your Merchant ID on: http://localhost:8000/login.html\n"
                                "2️⃣ Reply here with: `/login <YOUR_MERCHANT_ID>` (or your 10-digit phone number)\n\n"
                                "Once authenticated, you can record voice sales, upload wholesale bills, and track Khata!"
                            )
                            send_telegram_text(chat_id, access_denied_msg)
                            continue

                        # User is registered & authorized!
                        merchant_id = merchant_info["id"]

                        # ====================================================
                        # 1. SPEECH BOT: VERNACULAR VOICE NOTES & AUDIO CLIPS
                        # ====================================================
                        if voice or audio:
                            target_audio = voice or audio
                            file_id = target_audio.get("file_id")

                            async def _process_voice_tg(c_id, m_id, f_id):
                                action_task = asyncio.create_task(_periodic_chat_action(c_id, "typing"))
                                try:
                                    from app.services.bot_service import handle_voice_bytes
                                    audio_bytes = await download_telegram_file(f_id)
                                    if not audio_bytes:
                                        send_telegram_text(c_id, "⚠️ Could not download audio clip from Telegram. Please try speaking again.")
                                        return
                                    reply = await asyncio.to_thread(
                                        handle_voice_bytes,
                                        merchant_id=m_id,
                                        audio_bytes=audio_bytes,
                                        filename="voice.ogg"
                                    )
                                    send_telegram_text(c_id, reply)
                                except Exception as err:
                                    logger.error(f"Voice processing error in Telegram: {err}", exc_info=True)
                                    send_telegram_text(c_id, f"⚠️ Voice processing error: {err}")
                                finally:
                                    action_task.cancel()

                            asyncio.create_task(_process_voice_tg(chat_id, merchant_id, file_id))
                            continue

                        # ====================================================
                        # 2. WHOLESALE BILL PHOTOS & DOCUMENTS (WITH LIVE PROGRESS)
                        # ====================================================
                        elif photos or (document and document.get("mime_type", "").startswith("image/")):
                            best_photo = photos[-1] if photos else document
                            media_id = best_photo.get("file_id")
                            media_hash = best_photo.get("file_unique_id")

                            async def _handle_image_tg(c_id, m_id, med_id, m_hash):
                                action_task = asyncio.create_task(_periodic_chat_action(c_id, "upload_document"))
                                status_msg_id = None
                                try:
                                    # 1. Microsecond Perceptual Deduplication
                                    is_dup, key = deduplication_engine.is_duplicate_media(m_id, m_hash)
                                    if is_dup:
                                        send_telegram_text(
                                            c_id,
                                            "🛡️ *Duplicate Dropped (<1ms)*\nYou already uploaded this invoice earlier. Duplicate skipped!"
                                        )
                                        return

                                    # Instant Live Progress Card (<50ms feedback)
                                    status_msg_id = send_telegram_text(
                                        c_id,
                                        "⏳ *Wholesale Bill Received!*\n"
                                        "• 📥 *Status:* Downloading image..."
                                    )

                                    # 2. Download Image Bytes at Entry Point
                                    img_bytes = await download_telegram_file(med_id)
                                    if not img_bytes:
                                        err_dl = "⚠️ Could not download photo from Telegram. Please try sending again."
                                        if status_msg_id:
                                            edit_telegram_text(c_id, status_msg_id, err_dl)
                                        else:
                                            send_telegram_text(c_id, err_dl)
                                        return

                                    # Update Live Status: Verifying bill
                                    if status_msg_id:
                                        edit_telegram_text(
                                            c_id,
                                            status_msg_id,
                                            "⏳ *Wholesale Bill Received!*\n"
                                            "• 🔍 *Status:* Verifying document structure (Fast CV)..."
                                        )

                                    # 3. Entry-Point Image Gatekeeper: Verify bill vs random image/meme/selfie
                                    from app.services.image_gatekeeper import classify_image_document
                                    gate_res = await asyncio.to_thread(classify_image_document, img_bytes)

                                    if not gate_res.is_invoice:
                                        logger.info(
                                            f"[TelegramEntry] Dropped non-invoice photo from chat {c_id}: "
                                            f"doc_type={gate_res.document_type}, confidence={gate_res.confidence}, reason={gate_res.reason}"
                                        )
                                        if status_msg_id:
                                            edit_telegram_text(c_id, status_msg_id, gate_res.rejection_message)
                                        else:
                                            send_telegram_text(c_id, gate_res.rejection_message)
                                        return

                                    # 4. Legitimate Bill Confirmed! Update Live Status: Gemini Flash OCR & Margin-Guard
                                    if status_msg_id:
                                        edit_telegram_text(
                                            c_id,
                                            status_msg_id,
                                            "⏳ *Wholesale Bill Confirmed!*\n"
                                            "• 🤖 *Status:* Deciphering items & rates via Gemini Flash Vision...\n"
                                            "• 🛡️ *Margin-Guard:* Calculating profit & shelf price impact..."
                                        )
                                    logger.info(f"Processing verified bill from Telegram chat {c_id}: media_id={med_id}")

                                    # 5. Process Invoice Task
                                    from app.workers.tasks import process_invoice_task
                                    res = await asyncio.to_thread(
                                        process_invoice_task,
                                        merchant_id=m_id,
                                        media_id=med_id,
                                        whatsapp_message_id=f"tg_{m_hash}",
                                        sender_phone=str(c_id)
                                    )

                                    if res.get("status") == "REJECTED_NON_INVOICE":
                                        logger.warning(f"Celery task rejected non-invoice: {res.get('reason')}")
                                        rej_msg = (
                                            "⚠️ *Invoice Not Recognized*\n"
                                            "Could not detect recognizable wholesale line items. Nothing was added to your ledger."
                                        )
                                        if status_msg_id:
                                            edit_telegram_text(c_id, status_msg_id, rej_msg)
                                        else:
                                            send_telegram_text(c_id, rej_msg)
                                        return

                                    alerts_cnt = res.get('alerts_count', 0)
                                    mg_status = (
                                        f"🛡️ *Margin-Guard:* 🚨 *{alerts_cnt} Price Spike Alert(s) Detected!* Shelf recommendations dispatched."
                                        if alerts_cnt > 0
                                        else "🛡️ *Margin-Guard:* Rates stable (<3% change). Margins protected."
                                    )
                                    final_card = (
                                        f"✅ *Invoice {res.get('invoice_number', 'Digitized')} Logged!*\n\n"
                                        f"📦 *Items Extracted:* {res.get('items_count', 0)} line items\n"
                                        f"💰 *Grand Total:* ₹{res.get('grand_total', 0):,.2f}\n"
                                        f"🔒 *Ledger Status:* Stored securely in Supabase PostgreSQL (RLS Active)\n"
                                        f"{mg_status}"
                                    )

                                    # In-place live morphing: replace loading message with completed receipt
                                    if status_msg_id:
                                        edited = edit_telegram_text(c_id, status_msg_id, final_card)
                                        if not edited:
                                            send_telegram_text(c_id, final_card)
                                    else:
                                        send_telegram_text(c_id, final_card)

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
                                    logger.error(f"Error processing Telegram invoice: {exc}", exc_info=True)
                                    err_msg = f"⚠️ Error processing bill image: {exc}"
                                    if status_msg_id:
                                        edit_telegram_text(c_id, status_msg_id, err_msg)
                                    else:
                                        send_telegram_text(c_id, err_msg)
                                finally:
                                    action_task.cancel()

                            asyncio.create_task(_handle_image_tg(chat_id, merchant_id, media_id, media_hash))
                            continue

                        # ====================================================
                        # 3. TEXT MESSAGES (WITH LIVE TYPING FEEDBACK)
                        # ====================================================
                        else:
                            if not text:
                                continue

                            async def _handle_text_tg(c_id, m_id, user_text):
                                action_task = asyncio.create_task(_periodic_chat_action(c_id, "typing"))
                                try:
                                    from app.services.bot_service import handle_text_message
                                    reply = await asyncio.to_thread(
                                        handle_text_message,
                                        merchant_id=m_id,
                                        user_text=user_text,
                                        sender_phone=str(c_id)
                                    )
                                    send_telegram_text(c_id, reply)
                                except Exception as err:
                                    logger.error(f"Telegram text handling error: {err}", exc_info=True)
                                    send_telegram_text(c_id, f"⚠️ Error processing message: {err}")
                                finally:
                                    action_task.cancel()

                            asyncio.create_task(_handle_text_tg(chat_id, merchant_id, text))
                            continue
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

# Pluggable Auth & Onboarding Router
from app.api.auth import auth_router
app.include_router(auth_router)

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

# Mount frontend directory for Retail Copilot Web App
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(FRONTEND_DIR):
    from fastapi.staticfiles import StaticFiles

    css_path = os.path.join(FRONTEND_DIR, "css")
    if os.path.exists(css_path):
        app.mount("/css", StaticFiles(directory=css_path), name="frontend_css")

    js_path = os.path.join(FRONTEND_DIR, "js")
    if os.path.exists(js_path):
        app.mount("/js", StaticFiles(directory=js_path), name="frontend_js")

    @app.get("/", tags=["Frontend"], response_class=FileResponse)
    async def serve_frontend_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/login", tags=["Frontend"], response_class=FileResponse)
    async def serve_frontend_login():
        return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))

    @app.get("/login.html", tags=["Frontend"], response_class=FileResponse)
    async def serve_frontend_login_html():
        return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))

    @app.get("/dashboard", tags=["Frontend"], response_class=FileResponse)
    async def serve_frontend_dashboard():
        return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))

    @app.get("/dashboard.html", tags=["Frontend"], response_class=FileResponse)
    async def serve_frontend_dashboard_html():
        return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
