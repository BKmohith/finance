"""
app/workers/jev_router.py
System 1 Jev Reflex Router (<18ms Intent Classifier).
Laptop 3 Domain (Perception & Routing).

Determines payload intent:
  - MEME_SPAM: Greetings, forwards, stickers, non-business text (Drop immediately, $0)
  - COUNTER_SALE: Retail sales shorthand (e.g. "Paytm 300 Oil 2", "25 bag atta 450 cash")
  - VOICE_KHATA: Informal customer credit notes (e.g. "Sharma ji 500 udhaar", "ರಮೇಶ್ 500 ಸಾಲ")
  - INVOICE_BILL: Wholesale distributor paper invoices / bills
"""
import re
import time
import logging
from typing import Optional, Dict, Any
import httpx

from app.core.contracts import InboundIntentClass
from app.workers.config import settings

logger = logging.getLogger(__name__)

# --- Tier 1: Ultra-Fast Regex Signatures (<2ms) ---

# Greetings, good morning, memes, blessings with no business intent
MEME_SPAM_PATTERNS = [
    r"\b(good\s*morning|good\s*night|suprabhat|shubh\s*prabhat|namaste|jai\s*shree\s*ram|radhe\s*radhe|salam)\b",
    r"\b(have\s*a\s*(nice|great|blessed)\s*day|happy\s*(diwali|holi|eid|new\s*year))\b",
    r"\b(kya\s*haal|kaise\s*ho|sab\s*theek|what's\s*up)\b",
    r"^(hello|hi|hey)[\s!.,a-zA-Z]*$",
]

# Obvious customer credit / Udhaar keywords (Hindi, Hinglish, Kannada, English)
VOICE_KHATA_PATTERNS = [
    r"\b(udhaar|udhar|khata|khate|baaki|baki|jama|credit|dues|debit|vasool|hisab)\b",
    r"\b(ಸಾಲ|ಖಾತೆ|ಉಳಿಕೆ|ಕೊಟ್ಟಿರುವೆ|ಕೊಟ್ಟೆ|ಬಾಕಿ)\b",  # Kannada: Saala, Khate, Baaki, Kottiruva
    r"\b(give\s*credit|got\s*credit|received\s*credit|add\s*to\s*khata)\b",
]

# Obvious counter sales keywords (Item + Quantity + Price / Payment shorthand)
COUNTER_SALE_PATTERNS = [
    r"\b(sold|becha|bikri|pack|packet|packet|bag|bags|kg|kilo|litre|ltr|peti|carton|piece|pcs)\b",
    r"\b(paytm|gpay|phonepe|upi|cash|rokh|nagad)\s*\d+",
    r"\d+\s*(bag|bags|kg|packet|pack|ltr|litre|bottle|unit|units)\b",
    r"\b(atta|oil|sugar|rice|wheat|milk|doodh|tel|chai|tea|soap|biscuit|dal)\b.*\b\d+",
]

# Wholesale distributor bill keywords
INVOICE_BILL_PATTERNS = [
    r"\b(invoice|tax\s*invoice|gstin|gst\s*no|bill\s*no|challan|distributor|wholesaler|fmcg)\b",
    r"\b(credit\s*due\s*date|payment\s*terms|consignee|buyer)\b",
]


class JevRouter:
    """
    System 1 Jev Reflex Router.
    Tier 1: <2ms deterministic regex fast-path.
    Tier 2: TypeSafe Jev via OpenRouter API (if configured).
    Tier 3: Rule-based heuristic fallback.
    """

    def __init__(self) -> None:
        self.openrouter_api_key = settings.OPENROUTER_API_KEY
        self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"

    def classify_intent(
        self, text: Optional[str] = None, media_mime_type: Optional[str] = None
    ) -> InboundIntentClass:
        """
        Classifies incoming message into InboundIntentClass.
        Guaranteed to execute in <18ms on local fast-path.
        """
        start_time = time.perf_counter()

        # 1. Media Type Fast-Path (Images of paper bills)
        if media_mime_type and media_mime_type.startswith("image/"):
            # If text explicitly mentions credit/sale without bill context, check text; otherwise invoice
            if not text or not any(re.search(p, text, re.I) for p in VOICE_KHATA_PATTERNS + COUNTER_SALE_PATTERNS):
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[JevRouter] Classified INVOICE_BILL from media_type={media_mime_type} in {elapsed_ms:.2f}ms")
                return InboundIntentClass.INVOICE_BILL

        cleaned = (text or "").strip()
        if not cleaned:
            return InboundIntentClass.MEME_SPAM

        # 2. Tier 1: Fast-Path Regex Rules (<2ms)
        # Check spam first (greetings, blessings without numbers)
        for pat in MEME_SPAM_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                if not re.search(r"\d+", cleaned):
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    logger.info(f"[JevRouter] Classified MEME_SPAM via fast-path in {elapsed_ms:.2f}ms")
                    return InboundIntentClass.MEME_SPAM

        # Check wholesale invoice keywords
        for pat in INVOICE_BILL_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[JevRouter] Classified INVOICE_BILL via fast-path in {elapsed_ms:.2f}ms")
                return InboundIntentClass.INVOICE_BILL

        # Check Khata / Udhaar keywords
        for pat in VOICE_KHATA_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[JevRouter] Classified VOICE_KHATA via fast-path in {elapsed_ms:.2f}ms")
                return InboundIntentClass.VOICE_KHATA

        # Check Counter Sale shorthand
        for pat in COUNTER_SALE_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[JevRouter] Classified COUNTER_SALE via fast-path in {elapsed_ms:.2f}ms")
                return InboundIntentClass.COUNTER_SALE

        # 3. Tier 2: OpenRouter Jev Model Decision (if key is set)
        if self.openrouter_api_key and len(cleaned) > 10:
            try:
                jev_result = self._query_jev_api(cleaned)
                if jev_result:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    logger.info(f"[JevRouter] Classified {jev_result} via OpenRouter Jev in {elapsed_ms:.2f}ms")
                    return jev_result
            except Exception as e:
                logger.warning(f"[JevRouter] OpenRouter Jev call failed: {e}. Falling back to heuristics.")

        # 4. Tier 3: Default Heuristic Fallback
        # If text contains digits/numbers, likely a transaction; otherwise meme/spam
        if re.search(r"\d+", cleaned):
            return InboundIntentClass.COUNTER_SALE
        return InboundIntentClass.MEME_SPAM

    def _query_jev_api(self, text: str) -> Optional[InboundIntentClass]:
        """
        Calls TypeSafe Jev via OpenRouter API with a structured prompt.
        """
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "HTTP-Referer": "https://sahayak.ai",
            "X-Title": "Sahayak Jev Reflex Router",
            "Content-Type": "application/json",
        }

        prompt = (
            "You are System 1 Jev Router for an Indian Kirana retail store. "
            "Classify the following inbound message into exactly one category:\n"
            "Options: [MEME_SPAM, COUNTER_SALE, VOICE_KHATA, INVOICE_BILL]\n"
            f"Message: \"{text}\"\n"
            "Answer with ONLY the category name."
        )

        payload: Dict[str, Any] = {
            "model": "typesafe/jev-latest",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 10,
            "temperature": 0.0,
        }

        with httpx.Client(timeout=2.0) as client:
            resp = client.post(self.openrouter_url, json=payload, headers=headers)
            if resp.status_code == 200:
                answer = resp.json()["choices"][0]["message"]["content"].strip().upper()
                for intent in InboundIntentClass:
                    if intent.value in answer:
                        return intent
            # If typesafe/jev-latest isn't routeable, try gpt-4o-mini fast fallback on OpenRouter
            elif resp.status_code != 200:
                payload["model"] = "openai/gpt-4o-mini"
                resp2 = client.post(self.openrouter_url, json=payload, headers=headers)
                if resp2.status_code == 200:
                    answer = resp2.json()["choices"][0]["message"]["content"].strip().upper()
                    for intent in InboundIntentClass:
                        if intent.value in answer:
                            return intent
        return None


# Module-level singleton
jev_router = JevRouter()
classify_inbound_intent = jev_router.classify_intent
