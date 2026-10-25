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
        lower = cleaned.lower()

        # Inquiries / questions are advisory, not direct ledger writes
        if cleaned.endswith("?") or lower.startswith(("can i", "should i", "kya me", "kya hum", "kya main", "is it safe")):
            return None

        # 1. Action Detection (Give Credit vs Collect Payment)
        action = "GIVE_CREDIT"
        if re.search(r"\b(jama|paid|chukaya|vasool|collected|received|wapas|bharpai)\b", cleaned, re.I):
            action = "COLLECT_PAYMENT"

        # 2. Extract Customer Phone Number (e.g. 9876543210, +919876543210, 9845012345)
        customer_phone = None
        phone_match = re.search(r"(?:\+91[\-\s]?)?[6-9]\d{9}\b", cleaned)
        if phone_match:
            raw_phone = phone_match.group(0).replace(" ", "").replace("-", "")
            customer_phone = raw_phone if raw_phone.startswith("+91") else f"+91{raw_phone}"
            # Remove phone number from cleaned text so digits don't collide with monetary amount
            cleaned = cleaned[:phone_match.start()] + " " + cleaned[phone_match.end():]

        # 3. Extract Monetary Amount
        amount_match = re.search(r"(?:₹|rs\.?|inr|roopayi|rupaye|rupees)?\s*(\d+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|inr|roopayi|rupaye|rupees)?", cleaned, re.I)
        if not amount_match:
            # Fallback to Gemini if regex cannot find monetary amount
            if settings.GEMINI_API_KEY:
                return self._parse_khata_with_gemini(text)
            return None
        amount = float(amount_match.group(1))

        # 4. Extract Customer Name
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
                if candidate.lower() not in {"paytm", "gpay", "phonepe", "cash", "upi", "give", "paid", "credit", "kannada", "phone"}:
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
            transcription=text.strip(),
            confidence=confidence,
            customer_phone=customer_phone,
        )

    def _parse_khata_with_gemini(self, text: str) -> Optional[VoiceKhataIntent]:
        """Fallback to Google Gemini for conversational Khata entries."""
        try:
            import json
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            prompt = (
                "Extract customer credit (Udhaar) ledger entry from this Indian retail text.\n"
                "Output ONLY a raw JSON object matching this schema:\n"
                "{\n"
                '  "customer_name": str,\n'
                '  "amount": float,\n'
                '  "action": "GIVE_CREDIT" | "COLLECT_PAYMENT",\n'
                '  "customer_phone": str | null\n'
                "}\n"
                f'Text: "{text}"'
            )
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL or "gemini-3.5-flash-lite",
                contents=prompt,
            )
            if resp.text:
                clean_json = resp.text.strip().replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_json)
                amt = float(data.get("amount") or 0.0)
                if amt > 0:
                    return VoiceKhataIntent(
                        customer_name=data.get("customer_name") or "Customer",
                        amount=amt,
                        action=data.get("action") or "GIVE_CREDIT",
                        transcription=text.strip(),
                        confidence=0.98,
                        customer_phone=data.get("customer_phone"),
                    )
        except Exception as e:
            logger.warning(f"[VoiceKhataParser] Gemini Khata fallback failed: {e}")
        return None

    def parse_counter_sale(
        self, text: str, merchant_id: str = "M_DEMO_001"
    ) -> Optional[CounterSaleEvent]:
        """
        Parses itemized counter sales shorthand into CounterSaleEvent.
        Examples:
          - "28 units of sunflower oil at price 8000" -> 28 units at ₹285.71 each, Total ₹8000
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

        # Pattern Special: <qty> [unit]? [of]? <multi-word item> (?:at price|price|at|for|rate|rs|₹) <total_or_rate>
        # e.g. "28 units of sunflower oil at price 8000" or "5 kg of basmati rice for 600"
        pat_qty_item_price = re.search(
            r"^(?:sold|becha)?\s*(\d+(?:\.\d+)?)\s*(bag|bags|kg|packet|pack|packets|ltr|litre|litres|bottle|bottles|pcs|units|box|boxes)?\s*(?:of\s+)?([A-Za-z\s]+?)\s+(?:at\s+price|price|at|for|rate|rs\.?|₹|inr)\s*(\d+(?:\.\d+)?)$",
            cleaned,
            re.I
        )
        if pat_qty_item_price:
            qty = float(pat_qty_item_price.group(1))
            unit = pat_qty_item_price.group(2) or "units"
            item_name = pat_qty_item_price.group(3).strip()
            total_or_rate = float(pat_qty_item_price.group(4))
            
            # If total_or_rate is clearly total price (e.g. 8000 for 28 units), divide to find unit price
            line_tot = total_or_rate
            unit_price = round(line_tot / qty, 2) if qty > 0 else line_tot
            items.append(
                CounterItemSale(
                    item_name=item_name,
                    quantity=qty,
                    unit=unit,
                    unit_retail_price=max(unit_price, 0.01),
                    line_total=max(line_tot, 0.01),
                )
            )
            total_amount = line_tot

        # Pattern 0: [Payment]? [Currency]? <Total_Amount> [Currency]? <Item_Name> <Qty> [Unit]?
        # Examples: "12000 ruppes ashirwad atta 8 bags", "paytm 300 oil 2", "150 rs sugar 3 kg"
        if not items:
            pat_amt_item_qty = re.search(
                r"^(?:(?:paytm|cash|upi|gpay|phonepe)\s+)?(?:₹|rs\.?|inr|rupees|ruppes|rupaye)?\s*(\d+(?:\.\d+)?)\s*(?:(?:₹|rs\.?|inr|rupees|ruppes|rupaye)\s+)?([A-Za-z\s]+?)\s+(\d+(?:\.\d+)?)\s*(bag|bags|kg|packet|pack|packets|ltr|litre|litres|bottle|bottles|pcs|units|box|boxes)?$",
                cleaned,
                re.I,
            )
            if pat_amt_item_qty:
                tot = float(pat_amt_item_qty.group(1))
                item_name = pat_amt_item_qty.group(2).strip()
                qty = float(pat_amt_item_qty.group(3))
                unit = pat_amt_item_qty.group(4) or "units"
                unit_price = round(tot / qty, 2) if qty > 0 else tot
                items.append(
                    CounterItemSale(
                        item_name=item_name,
                        quantity=qty,
                        unit=unit,
                        unit_retail_price=max(unit_price, 0.01),
                        line_total=max(tot, 0.01),
                    )
                )
                total_amount = tot

        # Pattern 1: Explicit Payment prefix + Total Amount + Item + Qty (e.g. "Paytm 300 Oil 2")
        if not items:
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
                        unit_retail_price=max(unit_price, 0.01),
                        line_total=max(tot, 0.01),
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
                        unit_retail_price=max(rate, 0.01),
                        line_total=max(line_total, 0.01),
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
                        unit_retail_price=max(rate, 0.01),
                        line_total=max(line_total, 0.01),
                    )
                )
                total_amount = line_total

        # If items detected via local fast path, construct event
        if items:
            return CounterSaleEvent(
                merchant_id=merchant_id,
                amount_paid=total_amount if payment_method != PaymentMethod.KHATA_CREDIT else 0.0,
                payment_method=payment_method,
                items=items,
                credit_amount=total_amount if payment_method == PaymentMethod.KHATA_CREDIT else 0.0,
                timestamp=datetime.utcnow(),
            )

        # Fallback to Gemini with strict arithmetic derivation
        if settings.GEMINI_API_KEY:
            gemini_event = self._parse_with_gemini(cleaned, merchant_id)
            if gemini_event:
                return gemini_event

        return None

    def _parse_with_gemini(self, text: str, merchant_id: str) -> Optional[CounterSaleEvent]:
        """Fallback to Google Gemini for complex, unstructured sales text with arithmetic normalization."""
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
                "IMPORTANT: If user specifies a total price for multiple units (e.g. '28 units of sunflower oil at price 8000'), "
                "set line_total = 8000 and calculate unit_retail_price = line_total / quantity (285.71). "
                "Never leave unit_retail_price or line_total as 0.\n"
                f'Text: "{text}"'
            )
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL or "gemini-3.5-flash-lite",
                contents=prompt,
            )
            if resp.text:
                clean_json = resp.text.strip().replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_json)

                raw_items = data.get("items", [])
                clean_items: List[CounterItemSale] = []
                total_derived = 0.0

                for it in raw_items:
                    name = str(it.get("item_name") or "Retail Item").strip()
                    unit = str(it.get("unit") or "units").strip()
                    try:
                        qty = float(it.get("quantity") or 1.0)
                    except (ValueError, TypeError):
                        qty = 1.0
                    if qty <= 0:
                        qty = 1.0

                    try:
                        tot = float(it.get("line_total") or 0.0)
                    except (ValueError, TypeError):
                        tot = 0.0

                    try:
                        rate = float(it.get("unit_retail_price") or 0.0)
                    except (ValueError, TypeError):
                        rate = 0.0

                    # Arithmetic Reconciliation (Zero Hallucination / Zero Division Error)
                    if rate <= 0 and tot > 0:
                        rate = round(tot / qty, 2)
                    elif tot <= 0 and rate > 0:
                        tot = round(qty * rate, 2)
                    elif rate <= 0 and tot <= 0:
                        raw_paid = float(data.get("amount_paid") or 0.0)
                        if raw_paid > 0:
                            tot = raw_paid
                            rate = round(tot / qty, 2)
                        else:
                            rate = 1.0
                            tot = qty

                    rate = max(rate, 0.01)
                    tot = max(tot, round(qty * rate, 2))
                    total_derived += tot

                    clean_items.append(
                        CounterItemSale(
                            item_name=name,
                            quantity=qty,
                            unit=unit,
                            unit_retail_price=rate,
                            line_total=tot,
                        )
                    )

                if clean_items:
                    amt_paid = float(data.get("amount_paid") or total_derived)
                    if amt_paid <= 0:
                        amt_paid = total_derived

                    method_str = str(data.get("payment_method") or "CASH").upper()
                    try:
                        pay_method = PaymentMethod(method_str)
                    except ValueError:
                        pay_method = PaymentMethod.CASH

                    return CounterSaleEvent(
                        merchant_id=merchant_id,
                        amount_paid=amt_paid if pay_method != PaymentMethod.KHATA_CREDIT else 0.0,
                        payment_method=pay_method,
                        items=clean_items,
                        credit_amount=amt_paid if pay_method == PaymentMethod.KHATA_CREDIT else 0.0,
                        timestamp=datetime.utcnow(),
                    )
        except Exception as e:
            logger.error(f"[VoiceKhataParser] Gemini fallback failed: {e}")
        return None


# Module-level singleton
voice_khata_parser = VoiceKhataParser()
parse_voice_khata = voice_khata_parser.parse_voice_khata
parse_counter_sale = voice_khata_parser.parse_counter_sale
