"""
app/workers/voice_khata.py
Agent 1: Conversational Entity Extractor for Customer Khata and Counter Sales.
Laptop 3 Domain (Perception & Entity Parsing).

Normalizes messy conversational voice/text transcripts into strict, frozen Pydantic contracts:
  - VoiceKhataIntent (Udhaar credit given or repaid)
  - CounterSaleEvent (Immediate itemized counter cash/UPI sales)
"""
import re
import logging
from typing import Optional, List
from datetime import datetime

from app.core.contracts import (
    VoiceKhataIntent,
    CounterSaleEvent,
    CounterItemSale,
    PaymentMethod,
)
from app.workers.config import settings

logger = logging.getLogger(__name__)


class VoiceKhataParser:
    """
    Parses conversational text into frozen Pydantic contracts.
    Supports Kannada, Hindi, Hinglish, and English retail formats.
    """

    # --- Kannada Transliteration/Mapping Dictionary ---
    KANNADA_NAMES = {
        "ರಮೇಶ್": "Ramesh",
        "ಸುರೇಶ್": "Suresh",
        "ಮಹೇಶ್": "Mahesh",
        "ಕುಮಾರ್": "Kumar",
        "ಶರ್ಮಾ": "Sharma",
    }

    def parse_voice_khata(
        self, text: str, confidence: float = 0.95
    ) -> Optional[VoiceKhataIntent]:
        """
        Parses Udhaar / store credit intent.
        Returns VoiceKhataIntent or None if not a Khata message.
        """
        if not text or not text.strip():
            return None

        cleaned = text.strip()

        # 1. Action Detection (Give Credit vs Collect Payment)
        action = "GIVE_CREDIT"
        if re.search(r"\b(jama|paid|chukaya|vasool|collected|received|wapas|bharpai)\b", cleaned, re.I):
            action = "COLLECT_PAYMENT"

        # 2. Extract Monetary Amount
        amount_match = re.search(r"(?:₹|rs\.?|inr|roopayi|rupaye|rupees)?\s*(\d+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|inr|roopayi|rupaye|rupees)?", cleaned, re.I)
        if not amount_match:
            return None
        amount = float(amount_match.group(1))

        # 3. Extract Customer Name
        customer_name = "Customer"

        # Check Kannada Name Patterns
        for kn_name, en_name in self.KANNADA_NAMES.items():
            if kn_name in cleaned:
                customer_name = en_name
                break

        # Check English/Hinglish Name Patterns (e.g., "Sharma ji", "Ramesh", "Gupta")
        if customer_name == "Customer":
            # Match names preceding "ji", "bhai", "seth", "avarige"
            name_match = re.search(r"([A-Z][a-z]+(?:\s+(?:ji|bhai|seth|singh|kumar|gowda))?)\b", cleaned)
            if name_match:
                candidate = name_match.group(1).strip()
                # Ensure it's not a payment keyword
                if candidate.lower() not in {"paytm", "gpay", "phonepe", "cash", "upi", "give", "paid", "credit", "kannada"}:
                    customer_name = candidate
            else:
                # Kannada suffix "avarige" (e.g., "Ramesh avarige")
                kn_suffix = re.search(r"(\w+)\s+(?:avarige|ge|ko|ne)\b", cleaned, re.I)
                if kn_suffix:
                    candidate = kn_suffix.group(1).strip()
                    if candidate.lower() not in {"paytm", "cash", "upi"}:
                        customer_name = self.KANNADA_NAMES.get(candidate, candidate)

        return VoiceKhataIntent(
            customer_name=customer_name,
            amount=amount,
            action=action,
            transcription=cleaned,
            confidence=confidence,
        )

    def parse_counter_sale(
        self, text: str, merchant_id: str = "M_DEMO_001"
    ) -> Optional[CounterSaleEvent]:
        """
        Parses itemized counter sales shorthand into CounterSaleEvent.
        Examples:
          - "25 bag atta 450 cash" -> 25 bags of atta at ₹450 each (total ₹11,250), Cash
          - "Paytm 300 Oil 2" -> 2 units of Oil totaling ₹300, Paytm UPI
          - "5 packet milk 30 upi" -> 5 packets of milk at ₹30 each (total ₹150), UPI
          - "10 sugar 42 cash" -> 10 units of sugar at ₹42 each (total ₹420), Cash
        """
        if not text or not text.strip():
            return None

        cleaned = text.strip()

        # 1. Detect Payment Method
        payment_method = PaymentMethod.CASH
        if re.search(r"\b(paytm|upi|gpay|phonepe|qr)\b", cleaned, re.I):
            payment_method = PaymentMethod.PAYTM_UPI
        elif re.search(r"\b(khata|udhaar|credit)\b", cleaned, re.I):
            payment_method = PaymentMethod.KHATA_CREDIT

        # 2. Extract Items, Quantities, and Rates
        items: List[CounterItemSale] = []
        total_amount = 0.0

        # Pattern 1: Explicit Payment prefix + Total Amount + Item + Qty (e.g. "Paytm 300 Oil 2")
        pat_pay = re.search(
            r"\b(?:paytm|cash|upi|gpay|phonepe)\s+(\d+(?:\.\d+)?)\s+([A-Za-z]+)\s+(\d+(?:\.\d+)?)\b",
            cleaned,
            re.I,
        )
        if pat_pay:
            tot = float(pat_pay.group(1))
            item_name = pat_pay.group(2).strip()
            qty = float(pat_pay.group(3))
            unit_price = round(tot / qty, 2) if qty > 0 else tot
            items.append(
                CounterItemSale(
                    item_name=item_name,
                    quantity=qty,
                    unit="units",
                    unit_retail_price=unit_price,
                    line_total=tot,
                )
            )
            total_amount = tot

        # Pattern 2: <qty> <unit> <item_name> <unit_rate> (e.g. "25 bag atta 450 cash" or "5 packet milk 30 upi")
        if not items:
            pat_a = re.search(
                r"(\d+(?:\.\d+)?)\s*(bag|bags|kg|packet|pack|packets|ltr|litre|litres|bottle|bottles|pcs|units)?\s+([A-Za-z]+)\s+(\d+(?:\.\d+)?)",
                cleaned,
                re.I,
            )
            if pat_a:
                qty = float(pat_a.group(1))
                unit = pat_a.group(2) or "units"
                item_name = pat_a.group(3).strip()
                rate = float(pat_a.group(4))
                line_total = qty * rate
                items.append(
                    CounterItemSale(
                        item_name=item_name,
                        quantity=qty,
                        unit=unit,
                        unit_retail_price=rate,
                        line_total=line_total,
                    )
                )
                total_amount = line_total

        # Pattern C: "sold 10 sugar 42" or "10 sugar 42"
        if not items:
            pat_c = re.search(
                r"(?:sold|becha)?\s*(\d+(?:\.\d+)?)\s+([A-Za-z]+)\s+(\d+(?:\.\d+)?)",
                cleaned,
                re.I,
            )
            if pat_c:
                qty = float(pat_c.group(1))
                item_name = pat_c.group(2).strip()
                rate = float(pat_c.group(3))
                line_total = qty * rate
                items.append(
                    CounterItemSale(
                        item_name=item_name,
                        quantity=qty,
                        unit="units",
                        unit_retail_price=rate,
                        line_total=line_total,
                    )
                )
                total_amount = line_total

        # If items detected, construct event
        if items:
            return CounterSaleEvent(
                merchant_id=merchant_id,
                amount_paid=total_amount if payment_method != PaymentMethod.KHATA_CREDIT else 0.0,
                payment_method=payment_method,
                items=items,
                credit_amount=total_amount if payment_method == PaymentMethod.KHATA_CREDIT else 0.0,
                timestamp=datetime.utcnow(),
            )

        # Fallback to Gemini if regex fails
        if settings.GEMINI_API_KEY:
            gemini_event = self._parse_with_gemini(cleaned, merchant_id)
            if gemini_event:
                return gemini_event

        return None

    def _parse_with_gemini(self, text: str, merchant_id: str) -> Optional[CounterSaleEvent]:
        """Fallback to Google Gemini for complex, unstructured sales text."""
        try:
            import json
            from google import genai

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            prompt = (
                "Extract counter sale details from this Indian retail text. "
                "Output ONLY a raw JSON object matching this schema:\n"
                "{\n"
                '  "amount_paid": float,\n'
                '  "payment_method": "CASH" | "PAYTM_UPI" | "KHATA_CREDIT",\n'
                '  "items": [\n'
                '    {"item_name": str, "quantity": float, "unit": str, "unit_retail_price": float, "line_total": float}\n'
                "  ]\n"
                "}\n"
                f'Text: "{text}"'
            )
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
            )
            if resp.text:
                clean_json = resp.text.strip().replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_json)
                items = [CounterItemSale(**item) for item in data.get("items", [])]
                return CounterSaleEvent(
                    merchant_id=merchant_id,
                    amount_paid=data.get("amount_paid", 0.0),
                    payment_method=PaymentMethod(data.get("payment_method", "CASH")),
                    items=items,
                    timestamp=datetime.utcnow(),
                )
        except Exception as e:
            logger.error(f"[VoiceKhataParser] Gemini fallback failed: {e}")
        return None


# Module-level singleton
voice_khata_parser = VoiceKhataParser()
parse_voice_khata = voice_khata_parser.parse_voice_khata
parse_counter_sale = voice_khata_parser.parse_counter_sale
