"""
app/api/notifier.py
Outbound Alert Dispatcher supporting both Telegram Bot API and Meta WhatsApp Cloud API.
Delivers instant Price-Shield Margin alerts to kirana merchants when wholesale prices rise.
"""
import logging
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings
from app.core.contracts import PriceHikeAlert

logger = logging.getLogger("sahayak.notifier")


class AlertNotifier:
    def __init__(
        self,
        telegram_token: Optional[str] = None,
        whatsapp_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        self.telegram_token = telegram_token or settings.TELEGRAM_BOT_TOKEN
        self.whatsapp_token = whatsapp_token or settings.WHATSAPP_API_TOKEN
        self.phone_number_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
        self.api_version = api_version or settings.META_GRAPH_API_VERSION

        self.whatsapp_base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        self.telegram_base_url = f"{settings.TELEGRAM_API_BASE}/bot{self.telegram_token}/sendMessage"

    @staticmethod
    def format_alert_message(alert: PriceHikeAlert) -> str:
        """
        Formats a clear, actionable Price-Shield notification tailored for Indian retailers.
        """
        loss_text = (
            f"📉 *Projected Profit Loss:* ₹{alert.estimated_loss_if_unchanged:,.2f}/mo\n"
            if alert.estimated_loss_if_unchanged > 0
            else ""
        )
        return (
            f"⚠️ *Sahayak (सहायक) Price-Shield Alert* ⚠️\n\n"
            f"Wholesale cost for *{alert.item_name}* rose from ₹{alert.old_wholesale_rate:,.2f} "
            f"to ₹{alert.new_wholesale_rate:,.2f} (*+{alert.percentage_hike:.1f}%*).\n\n"
            f"{loss_text}"
            f"🏷️ *Previous MRP:* ₹{alert.previous_mrp:,.2f}\n"
            f"🛡️ *Suggested Shelf MRP:* ₹{alert.suggested_new_mrp:,.2f} *(Protects 10-12% gross margin)*\n\n"
            f"_Reply 'UPDATE' to record new retail price._"
        )

    def send_telegram_alert(
        self,
        chat_id: str,
        alert: PriceHikeAlert,
        client: Optional[httpx.Client] = None
    ) -> Dict[str, Any]:
        """
        Sends an alert message via Telegram Bot API.
        """
        clean_chat_id = str(chat_id).replace("M_TG_", "").strip()
        message_text = self.format_alert_message(alert)
        payload = {
            "chat_id": clean_chat_id,
            "text": message_text,
            "parse_mode": "Markdown"
        }

        # Mock fallback for test environment
        if not self.telegram_token or self.telegram_token.startswith("mock_"):
            logger.info(f"[MOCK TELEGRAM OUTBOUND] Delivered alert to chat {clean_chat_id}:\n{message_text}")
            return {
                "status": "mock_delivered",
                "channel": "telegram",
                "recipient": clean_chat_id,
                "message": message_text
            }

        try:
            http_client = client or httpx.Client(timeout=10.0)
            response = http_client.post(self.telegram_base_url, json=payload)
            if response.status_code != 200:
                logger.warning(f"Telegram Markdown parse failed ({response.text}); retrying plain text")
                payload.pop("parse_mode", None)
                response = http_client.post(self.telegram_base_url, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Telegram alert dispatched to chat {clean_chat_id}: {data}")
            return {
                "status": "delivered",
                "channel": "telegram",
                "recipient": clean_chat_id,
                "telegram_response": data
            }
        except httpx.HTTPError as exc:
            logger.error(f"Failed to send Telegram alert to chat {clean_chat_id}: {exc}")
            return {
                "status": "error",
                "channel": "telegram",
                "error": str(exc),
                "recipient": clean_chat_id
            }

    def send_whatsapp_alert(
        self,
        alert: PriceHikeAlert,
        client: Optional[httpx.Client] = None
    ) -> Dict[str, Any]:
        """
        Sends an alert message via Meta WhatsApp Cloud API.
        """
        recipient_phone = alert.merchant_phone.replace("+", "").strip()
        body_text = self.format_alert_message(alert)

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": body_text
            }
        }
        headers = {
            "Authorization": f"Bearer {self.whatsapp_token}",
            "Content-Type": "application/json"
        }

        if not self.whatsapp_token or self.whatsapp_token.startswith("mock_"):
            logger.info(f"[MOCK WHATSAPP OUTBOUND] Delivered alert to {recipient_phone}:\n{body_text}")
            return {
                "status": "mock_delivered",
                "channel": "whatsapp",
                "recipient": recipient_phone,
                "message": body_text,
                "whatsapp_message_id": f"wam.mock.{alert.merchant_id}"
            }

        try:
            http_client = client or httpx.Client(timeout=10.0)
            response = http_client.post(self.whatsapp_base_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            logger.info(f"WhatsApp alert successfully dispatched to {recipient_phone}: {data}")
            return {
                "status": "delivered",
                "channel": "whatsapp",
                "recipient": recipient_phone,
                "meta_response": data
            }
        except httpx.HTTPError as exc:
            logger.error(f"Failed to send WhatsApp alert to {recipient_phone}: {exc}")
            return {
                "status": "error",
                "channel": "whatsapp",
                "error": str(exc),
                "recipient": recipient_phone
            }

    def send_price_shield_alert(
        self,
        alert: PriceHikeAlert,
        client: Optional[httpx.Client] = None
    ) -> Dict[str, Any]:
        """
        Dispatches alert based on configured channel (Telegram or Meta WhatsApp).
        """
        if settings.NOTIFICATION_CHANNEL == "telegram":
            target_id = alert.merchant_phone or alert.merchant_id
            if target_id:
                target_id = str(target_id).replace("M_TG_", "").strip()
            return self.send_telegram_alert(target_id, alert, client=client)

        return self.send_whatsapp_alert(alert, client=client)


# Aliases for backward compatibility with Laptop 2/3 contracts
WhatsAppNotifier = AlertNotifier
whatsapp_notifier = AlertNotifier()
