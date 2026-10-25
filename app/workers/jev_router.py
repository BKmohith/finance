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

# --- Tier 1: Ultra-Fast Reflex Signatures (<2ms, $0) ---

MEME_SPAM_PATTERNS = [
    r"\b(good\s*morning|good\s*night|suprabhat|shubh\s*prabhat|namaste|namaskara|jai\s*shree\s*ram|radhe\s*radhe|salam|ram\s*ram)\b",
    r"\b(have\s*a\s*(nice|great|blessed)\s*day|happy\s*(diwali|holi|eid|new\s*year|birthday))\b",
    r"\b(kya\s*haal|kaise\s*ho|sab\s*theek|what's\s*up|whats\s*up|how\s*are\s*you)\b",
    r"^(hello|hi|hey|hiya|yo|hola|helo)[\s!.,a-zA-Z]*$",
    r"\b(who\s*are\s*you|what\s*are\s*you|tell\s*me\s*a\s*joke|joke|poem|sing|who\s*is\s*the\s*president|capital\s*of)\b",
    r"^(ok|okay|k|hmm|haan|theek\s*hai|bye|goodbye|cya|see\s*you)[\s!.]*$",
]

VOICE_KHATA_PATTERNS = [
    r"\b(udhaar|udhar|khata|khate|baaki|baki|jama|credit|dues|debit|vasool|hisab|chukaya)\b",
    r"\b(ಸಾಲ|ಖಾತೆ|ಉಳಿಕೆ|ಕೊಟ್ಟಿರುವೆ|ಕೊಟ್ಟೆ|ಬಾಕಿ)\b",  # Kannada: Saala, Khate, Baaki, Kottiruva
    r"\b(give\s*credit|got\s*credit|received\s*credit|add\s*to\s*khata)\b",
]

COUNTER_SALE_PATTERNS = [
    r"\b(sold|becha|bikri|pack|packet|bag|bags|kg|kilo|litre|ltr|peti|carton|piece|pcs)\b",
    r"\b(paytm|gpay|phonepe|upi|cash|rokh|nagad)\s*\d+",
    r"\d+\s*(bag|bags|kg|packet|pack|ltr|litre|bottle|unit|units)\b",
    r"\b(atta|oil|sugar|rice|wheat|milk|doodh|tel|chai|tea|soap|biscuit|dal)\b.*\b\d+",
]

INVOICE_BILL_PATTERNS = [
    r"\b(invoice|tax\s*invoice|gstin|gst\s*no|bill\s*no|challan|distributor|wholesaler|fmcg)\b",
    r"\b(credit\s*due\s*date|payment\s*terms|consignee|buyer)\b",
]

CASH_FORECAST_PATTERNS = [
    r"\b(forecast|runway|liquidity|cash\s*crunch|cashflow)\b",
    r"\b(bachega|bachegi|kya\s*hoga|paisa\s*kitna|kitna\s*paisa)\b",
    r"\b(ಮುಂದಿನ\s*ವಾರ\s*ಹಣ\s*ಉಳಿಯುತ್ತಾ|ಹಣ\s*ಉಳಿಯುತ್ತಾ)\b",
    r"\b(what\s*if|what\s*happens|agar|delay|shortfall)\b",
]


class JevRouter:
    """
    System 1 Jev Reflex Router (<18ms Intent Classifier).
    Tier 1: <2ms deterministic reflex fast-path (Spam, Counter Sales, Khata Udhaar, Bills, Forecast).
    Tier 2: Dynamic LLM / Jev API semantic classifier (for conversational business queries & dialect nuances).
    Tier 3: Graceful heuristic fallback.
    """

    def __init__(self) -> None:
        self.openrouter_api_key = settings.OPENROUTER_API_KEY
        self.openrouter_url = "https://openrouter.ai/api/v1/chat/completions"

    def classify_media_intent(self, media_bytes: bytes, mime_type: str = "image/jpeg") -> InboundIntentClass:
        """Inspects media bytes using visual gatekeeper to distinguish INVOICE_BILL from MEME_SPAM."""
        try:
            from app.services.image_gatekeeper import classify_image_document
            res = classify_image_document(media_bytes, mime_type=mime_type)
            return InboundIntentClass.INVOICE_BILL if res.is_invoice else InboundIntentClass.MEME_SPAM
        except Exception as e:
            logger.warning(f"[JevRouter] Media classification error: {e}")
            return InboundIntentClass.MEME_SPAM

    def classify_intent(
        self, text: Optional[str] = None, media_mime_type: Optional[str] = None
    ) -> InboundIntentClass:
        """
        Classifies incoming message into InboundIntentClass.
        Guaranteed to execute in <18ms on local reflex fast-path.
        """
        start_time = time.perf_counter()

        # 1. Media Type Fast-Path (Images of paper bills with no explicit text override)
        if media_mime_type and media_mime_type.startswith("image/"):
            if not text or not text.strip():
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[JevRouter] Classified INVOICE_BILL candidate from media_type={media_mime_type} in {elapsed_ms:.2f}ms")
                return InboundIntentClass.INVOICE_BILL

        cleaned = (text or "").strip()
        if not cleaned:
            return InboundIntentClass.MEME_SPAM

        # 2. Tier 1: Fast-Path Reflex Signatures (<2ms, $0)
        # A. Check spam first (greetings, blessings without numbers)
        for pat in MEME_SPAM_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                if not re.search(r"\d+", cleaned):
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    logger.info(f"[JevRouter] Classified MEME_SPAM via fast-path in {elapsed_ms:.2f}ms")
                    return InboundIntentClass.MEME_SPAM

        # B. Check wholesale invoice keywords
        for pat in INVOICE_BILL_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[JevRouter] Classified INVOICE_BILL via fast-path in {elapsed_ms:.2f}ms")
                return InboundIntentClass.INVOICE_BILL

        # C. Check Cash Forecast keywords (e.g. "What happens if customer delays...", "bachega kya", "runway")
        for pat in CASH_FORECAST_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[JevRouter] Classified CASH_FORECAST via fast-path in {elapsed_ms:.2f}ms")
                return InboundIntentClass.CASH_FORECAST

        # D. Check Khata / Udhaar transactional keywords (e.g. "Sharma ji 500 udhaar", "ರಮೇಶ್ ಅವರಿಗೆ 500 ರೂಪಾಯಿ ಸಾಲ")
        for pat in VOICE_KHATA_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[JevRouter] Classified VOICE_KHATA via fast-path in {elapsed_ms:.2f}ms")
                return InboundIntentClass.VOICE_KHATA

        # E. Check Counter Sale shorthand (e.g. "25 bag atta 450 cash", "Paytm 300 Oil 2")
        for pat in COUNTER_SALE_PATTERNS:
            if re.search(pat, cleaned, re.IGNORECASE):
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[JevRouter] Classified COUNTER_SALE via fast-path in {elapsed_ms:.2f}ms")
                return InboundIntentClass.COUNTER_SALE

        # 3. Tier 2: Dynamic Classification via LLM (for conversational business queries & open questions)
        dynamic_intent = self._query_llm_intent(cleaned)
        if dynamic_intent:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.info(f"[JevRouter] Classified {dynamic_intent.value} via Jev dynamic tier in {elapsed_ms:.2f}ms")
            return dynamic_intent

        # 4. Tier 3: Graceful Fallback
        lower = cleaned.lower()
        if "?" in cleaned or any(k in lower for k in ["what if", "agar", "kya hoga", "bachega"]):
            return InboundIntentClass.CASH_FORECAST
        if any(k in lower for k in ["tell me", "explain", "who is", "who owes", "batao", "dikhao"]):
            return InboundIntentClass.BUSINESS_QUERY
        if any(char.isdigit() for char in cleaned):
            return InboundIntentClass.COUNTER_SALE
        return InboundIntentClass.MEME_SPAM

    def _query_llm_intent(self, text: str) -> Optional[InboundIntentClass]:
        """
        Dynamically classifies user intent without predefined rigid patterns,
        adapting to user preferences, dialects, and conversational queries via Gemini Flash.
        """
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                prompt = (
                    "You are System 1 Jev Reflex Classifier & Domain Gatekeeper for an Indian retail store copilot.\n"
                    "Classify the user message into EXACTLY ONE category:\n\n"
                    "1. MEME_SPAM (BLOCK / OFF-TOPIC): Greetings, memes, blessings, stickers, or ANY off-topic question completely unrelated to retail store operations, commerce, finance, or inventory (e.g. 'what is AI', 'who is the president', 'write a poem', 'how does python work', 'capital of India', 'tell me a joke'). All non-retail / non-business queries MUST be classified as MEME_SPAM to block them.\n"
                    "2. BUSINESS_QUERY (RETAIL STRATEGY & ANALYTICS): Any query relevant to retail business operations, store profit, sales advice, high-margin items to sell, store growth, customer dossiers, debtor history, or store stats (e.g. 'what should I sell to get more profit', 'how to increase margins', 'tell me about Sharma ji', 'who owes money', 'top debtors', 'how to grow my shop sales', 'which products have higher margin'). Jev marks these as highly relevant business queries!\n"
                    "3. CASH_FORECAST: What-if cash simulations, liquidity queries, runway forecasts, customer repayment delay queries (e.g. 'what happens if customer pays after 10 days', 'will rent be covered', 'cash in 7 days').\n"
                    "4. COUNTER_SALE: Direct recording of a counter sale, cash/UPI payment received, items sold (e.g. '28 units of sunflower oil at price 8000', 'Paytm 300 oil 2', '25 bag atta 450 cash', 'sold 10 sugar 42').\n"
                    "5. VOICE_KHATA: Direct customer credit (Udhaar) entry or repayment received (e.g. 'Sharma ji 500 udhaar', 'Ramesh 200 jama', 'give 500 credit to Suresh').\n"
                    "6. INVOICE_BILL: Distributor paper invoice, wholesale bill.\n\n"
                    f'User Message: "{text}"\n'
                    "Return ONLY the exact category name."
                )
                resp = client.models.generate_content(
                    model=settings.GEMINI_MODEL or "gemini-3.5-flash-lite",
                    contents=prompt
                )
                raw = (resp.text or "").strip().upper()
                for intent in InboundIntentClass:
                    if intent.value in raw:
                        return intent
            except Exception as e:
                logger.warning(f"[JevRouter] Dynamic LLM classification error: {e}")

        # Fallback to OpenRouter if configured
        if self.openrouter_api_key and len(text) > 10:
            return self._query_jev_api(text)

        return None

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
            "You are System 1 Jev Router for an Indian small business. "
            "Classify the following inbound message into exactly one category:\n"
            "Options: [MEME_SPAM, COUNTER_SALE, VOICE_KHATA, INVOICE_BILL, CASH_FORECAST]\n"
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
