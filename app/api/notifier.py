"""
app/api/notifier.py
Outbound WhatsApp Cloud API Dispatcher.
Delivers instant Price-Shield Margin alerts to kirana merchants when wholesale prices rise.
"""
import logging
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings
from app.core.contracts import PriceHikeAlert

logger = logging.getLogger("sahayak.notifier")


class WhatsAppNotifier:
    def __init__(
        self,
        api_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: Optional[str] = None
    ):
        self.api_token = api_token or settings.WHATSAPP_API_TOKEN
        self.phone_number_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
        self.api_version = api_version or settings.META_GRAPH_API_VERSION
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

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

    def send_price_shield_alert(
        self,
        alert: PriceHikeAlert,
        client: Optional[httpx.Client] = None
    ) -> Dict[str, Any]:
        """
        Dispatches outbound WhatsApp alert message to merchant's phone number.
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
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        # Check if running in mock/offline mode
        if not self.api_token or self.api_token.startswith("mock_"):
            logger.info(
                f"[MOCK WHATSAPP OUTBOUND] Delivered Price-Shield alert to {recipient_phone}:\n{body_text}"
            )
            return {
                "status": "mock_delivered",
                "recipient": recipient_phone,
                "message": body_text,
                "whatsapp_message_id": f"wam.mock.{alert.merchant_id}"
            }

        try:
            http_client = client or httpx.Client(timeout=10.0)
            response = http_client.post(self.base_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            logger.info(f"WhatsApp alert successfully dispatched to {recipient_phone}: {data}")
            return {
                "status": "delivered",
                "recipient": recipient_phone,
                "meta_response": data
            }
        except httpx.HTTPError as exc:
            logger.error(f"Failed to send WhatsApp alert to {recipient_phone}: {exc}")
            return {
                "status": "error",
                "error": str(exc),
                "recipient": recipient_phone
            }


# Singleton instance
whatsapp_notifier = WhatsAppNotifier()
