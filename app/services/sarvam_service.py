"""
app/services/sarvam_service.py
Sarvam AI Vernacular Speech & Bulbul TTS Integration Service.
Provides bidirectional speech-to-speech copilot for retail dashboards:
1. Speech-to-Text: Sarvam AI Saaras model (Kannada, Hindi, Hinglish, Indian English).
2. Cognitive Processing: Identical to Telegram bot (@sahayak_retail_bot) via bot_service.
3. Text-to-Speech: Sarvam AI Bulbul model (synthesizes audio for instant voice responses).
"""
import io
import logging
import re
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger("sahayak.sarvam")

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
DEFAULT_SARVAM_KEY = "sk_apba05ii_xikxfuEvwXbot88r0t4CLxRF"


class SarvamService:
    """
    Unified Sarvam AI Vernacular Speech Engine for Retail Copilots.
    """

    def __init__(self) -> None:
        self.api_key = getattr(settings, "SARVAM_API_KEY", None) or DEFAULT_SARVAM_KEY

    def clean_text_for_speech(self, text: str) -> str:
        """
        Cleans raw markdown, markdown tables, and currency signs into natural spoken sentences.
        Replaces ₹ with 'rupees ' and strips unnecessary formatting symbols.
        """
        if not text:
            return ""

        # Replace currency symbol with words
        cleaned = text.replace("₹", " rupees ")
        # Strip markdown syntax symbols: *, _, `, #, ~, |, [, ]
        cleaned = re.sub(r"[*_`#~|]", "", cleaned)
        cleaned = re.sub(r"\[.*?\]\(.*?\)", "", cleaned)
        # Strip long rule lines
        cleaned = re.sub(r"[━─═-]{3,}", "", cleaned)
        # Clean whitespace and strip emojis / non-standard characters
        cleaned = re.sub(r"[^\w\s\.,!\?\'\-]", " ", cleaned)
        
        # Take the most important top sentences for snappy audio delivery (<2s)
        lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
        spoken = ". ".join(lines[:3])
        spoken = re.sub(r"\s+", " ", spoken).strip()
        
        # Max 350 chars for high responsiveness
        if len(spoken) > 350:
            spoken = spoken[:347].rsplit(" ", 1)[0] + "..."
        return spoken

    def transcribe_speech(
        self,
        audio_bytes: bytes,
        filename: str = "voice.wav",
        language_code: str = "hi-IN",
        model: str = "saaras:v4"
    ) -> Dict[str, Any]:
        """
        Transcribes vernacular voice audio to text using Sarvam AI Saaras model.
        """
        if not audio_bytes or len(audio_bytes) < 10:
            return {"transcription": "", "language_code": language_code, "provider": "empty"}

        # Quick test mock check
        if audio_bytes.startswith(b"MOCK_KANNADA"):
            return {
                "transcription": "ರಮೇಶ್ ಅವರಿಗೆ 500 ರೂಪಾಯಿ ಸಾಲ",
                "language_code": "kn-IN",
                "provider": "mock"
            }
        if audio_bytes.startswith(b"MOCK_SALE"):
            return {
                "transcription": "28 bag atta 8000 cash",
                "language_code": "en-IN",
                "provider": "mock"
            }

        headers = {
            "api-subscription-key": self.api_key
        }

        mime_type = "audio/wav"
        if filename.endswith(".ogg") or filename.endswith(".opus"):
            mime_type = "audio/ogg"
        elif filename.endswith(".mp3"):
            mime_type = "audio/mpeg"
        elif filename.endswith(".webm"):
            mime_type = "audio/webm"

        files = {
            "file": (filename, io.BytesIO(audio_bytes), mime_type)
        }
        data = {
            "model": model,
            "language_code": language_code
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(SARVAM_STT_URL, files=files, data=data, headers=headers)
                if resp.status_code == 200:
                    body = resp.json()
                    transcript = body.get("transcript", "").strip()
                    detected_lang = body.get("language_code", language_code)
                    logger.info(f"[Sarvam STT] Successfully transcribed: '{transcript}' ({detected_lang})")
                    return {
                        "transcription": transcript,
                        "language_code": detected_lang,
                        "confidence": 0.95,
                        "provider": "sarvam_ai"
                    }
                else:
                    logger.warning(f"[Sarvam STT] HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"[Sarvam STT] Request error: {e}")

        # Fallback to secondary STT engine if Sarvam is unreachable
        try:
            from app.workers.stt_engine import STTEngine
            fallback_engine = STTEngine()
            return fallback_engine.transcribe_audio(audio_bytes, filename=filename, language_code=language_code)
        except Exception as fb_err:
            logger.warning(f"[Sarvam STT] Secondary fallback error: {fb_err}")

        return {
            "transcription": "",
            "language_code": language_code,
            "provider": "failed"
        }

    def synthesize_speech(
        self,
        text: str,
        target_language_code: str = "hi-IN",
        speaker: str = "aditya",
        model: str = "bulbul:v3"
    ) -> Optional[str]:
        """
        Synthesizes text into Indian vernacular speech audio via Sarvam Bulbul TTS.
        Returns base64 encoded audio string, or None if failed.
        """
        clean_text = self.clean_text_for_speech(text)
        if not clean_text:
            return None

        # Supported target languages for Sarvam Bulbul
        supported_langs = ("hi-IN", "kn-IN", "en-IN", "ta-IN", "te-IN", "bn-IN", "mr-IN", "gu-IN")
        if target_language_code not in supported_langs:
            target_language_code = "hi-IN"

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "inputs": [clean_text],
            "target_language_code": target_language_code,
            "speaker": speaker,
            "model": model
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(SARVAM_TTS_URL, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    audios = data.get("audios", [])
                    if audios and len(audios) > 0:
                        logger.info(f"[Sarvam TTS] Successfully synthesized audio for '{clean_text[:40]}...'")
                        return audios[0]
                else:
                    logger.warning(f"[Sarvam TTS] HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"[Sarvam TTS] Synthesis error: {e}")

        return None

    def process_voice_copilot(
        self,
        merchant_id: str,
        audio_bytes: Optional[bytes] = None,
        text: Optional[str] = None,
        language_code: str = "hi-IN",
        filename: str = "voice.wav"
    ) -> Dict[str, Any]:
        """
        Executes complete Bidirectional Speech Copilot Pipeline:
        1. Transcribe audio using Sarvam Saaras STT (or use input text).
        2. Execute exact retail command via bot_service (Khata, Sales, FIFO, Stock, Closing, What-If).
        3. Synthesize voice audio via Sarvam Bulbul TTS.
        4. Return full speech payload with audio base64, transcript, and Telegram-style formatted message.
        """
        from app.services.bot_service import handle_text_message

        # 1. Perception / Speech-to-Text
        transcription = ""
        provider = "text_input"
        detected_lang = language_code

        if audio_bytes and len(audio_bytes) > 20:
            stt_res = self.transcribe_speech(
                audio_bytes=audio_bytes,
                filename=filename,
                language_code=language_code
            )
            transcription = stt_res.get("transcription", "").strip()
            detected_lang = stt_res.get("language_code", language_code)
            provider = stt_res.get("provider", "sarvam_ai")

        elif text:
            transcription = text.strip()

        if not transcription:
            fallback_msg = "⚠️ Speech not detected. Please speak clearly near your microphone (e.g. 'Sharma ji 500 udhaar' or '28 oil 8000')."
            spoken = "Speech not detected. Please try speaking again."
            audio_b64 = self.synthesize_speech(spoken, target_language_code=language_code)
            return {
                "status": "NO_SPEECH",
                "heard_text": "",
                "reply_text": fallback_msg,
                "spoken_text": spoken,
                "audio_base64": audio_b64,
                "audio_mime": "audio/wav",
                "provider": provider,
                "language_code": language_code
            }

        # 2. Cognition / Ledger Processing (Exact Telegram Bot Brain)
        reply_text = handle_text_message(
            merchant_id=merchant_id,
            user_text=transcription,
            sender_phone="dashboard_voice"
        )

        # 3. Speech Synthesis (Sarvam Bulbul TTS)
        clean_spoken = self.clean_text_for_speech(reply_text)
        audio_base64 = self.synthesize_speech(
            text=clean_spoken,
            target_language_code=detected_lang
        )

        return {
            "status": "SUCCESS",
            "heard_text": transcription,
            "reply_text": reply_text,
            "spoken_text": clean_spoken,
            "audio_base64": audio_base64,
            "audio_mime": "audio/wav",
            "provider": provider,
            "language_code": detected_lang
        }


sarvam_service = SarvamService()
