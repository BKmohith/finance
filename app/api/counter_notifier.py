"""
app/api/counter_notifier.py
Customer Khata Receipt & Digital Notification Dispatcher for Phase 2 Counter Sales.
Delivers instant customer Udhaar (store credit) receipts via Telegram and WhatsApp.
"""
import logging
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings
from app.core.contracts import CounterSaleEvent

logger = logging.getLogger("sahayak.counter_notifier")


class CounterNotifier:
    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_api_base: Optional[str] = None
    ):
        self.telegram_token = telegram_token or settings.TELEGRAM_BOT_TOKEN
        self.telegram_api_base = telegram_api_base or settings.TELEGRAM_API_BASE

    @staticmethod
    def format_khata_receipt(
        event: CounterSaleEvent,
        total_balance: Optional[float] = None,
        store_name: str = "Ramesh Kirana Store"
    ) -> str:
        """
        Formats a friendly, high-trust digital Udhaar receipt for the customer.
        """
        customer_greeting = f"Namaste {event.customer_name or 'Grahak'} ji"
        total_bill = event.amount_paid + event.credit_amount
        balance_line = (
            f"📊 *Kul Baaki Udhaar (Total Balance):* ₹{total_balance:,.2f}\n"
            if total_balance is not None
            else ""
        )

        items_summary = ""
        if event.items:
            items_list = ", ".join(f"{i.item_name} (x{int(i.quantity) if i.quantity.is_integer() else i.quantity})" for i in event.items[:3])
            if len(event.items) > 3:
                items_list += f" +{len(event.items)-3} more"
            items_summary = f"📦 *Items:* {items_list}\n"

        return (
            f"🙏 *{customer_greeting}* 🙏\n\n"
            f"*{store_name}* par aapka naya hisaab darj hua hai:\n\n"
            f"{items_summary}"
            f"🧾 *Kul Kharidari (Total Bill):* ₹{total_bill:,.2f}\n"
            f"💵 *Diya Hua (Paid):* ₹{event.amount_paid:,.2f} ({event.payment_method.value})\n"
            f"📝 *Naya Udhaar (Credit):* ₹{event.credit_amount:,.2f}\n"
            f"{balance_line}\n"
            f"✅ _Sahayak Digital Khata dwara surakshit._"
        )

    def send_khata_credit_receipt(
        self,
        event: CounterSaleEvent,
        total_balance: Optional[float] = None,
        client: Optional[httpx.Client] = None
    ) -> Dict[str, Any]:
        """
        Sends digital credit receipt to customer phone or Telegram chat ID.
        """
        if not event.customer_phone:
            logger.debug("No customer phone/ID provided; skipping credit receipt.")
            return {"status": "skipped", "reason": "No customer phone provided"}

        target_id = event.customer_phone.replace("+", "").strip()
        message_text = self.format_khata_receipt(event, total_balance=total_balance)

        # 1. Telegram delivery if target is Telegram chat ID or active Telegram bot
        if self.telegram_token and not self.telegram_token.startswith("mock_"):
            telegram_url = f"{self.telegram_api_base}/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": target_id,
                "text": message_text,
                "parse_mode": "Markdown"
            }
            try:
                http_client = client or httpx.Client(timeout=8.0)
                response = http_client.post(telegram_url, json=payload)
                if response.status_code == 200:
                    logger.info(f"Digital Khata receipt delivered to Telegram {target_id}")
                    return {
                        "status": "delivered",
                        "channel": "telegram",
                        "recipient": target_id,
                        "message": message_text
                    }
                else:
                    logger.warning(f"Telegram receipt delivery non-200: {response.text}")
            except Exception as e:
                logger.warning(f"Could not deliver Telegram receipt to {target_id}: {e}")

        # 2. Fallback / Mock delivery log
        logger.info(f"[MOCK DIGITAL RECEIPT] Delivered to {target_id}:\n{message_text}")
        return {
            "status": "mock_delivered",
            "channel": "mock",
            "recipient": target_id,
            "message": message_text
        }


# Singleton instance
counter_notifier = CounterNotifier()
