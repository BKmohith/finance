"""
app/api/security.py
Security & Cryptographic Verification for Meta WhatsApp Cloud API Webhooks.
Implements:
1. Meta Webhook Subscription Verification (hub.challenge handshake)
2. HMAC-SHA256 Payload Signature Validation (X-Hub-Signature-256)
"""
import hashlib
import hmac
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("sahayak.security")


def verify_webhook_subscription(mode: Optional[str], token: Optional[str], challenge: Optional[str]) -> Optional[int]:
    """
    Validates Meta's GET verification request:
    GET /webhook/whatsapp?hub.mode=subscribe&hub.verify_token=...&hub.challenge=1158201444
    Returns integer challenge on success, or None on failure.
    """
    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Meta webhook subscription verified successfully.")
        try:
            return int(challenge) if challenge is not None else None
        except ValueError:
            return None
    logger.warning("Meta webhook verification failed: Invalid verify token or mode.")
    return None


def validate_hub_signature(
    request_body: bytes,
    x_hub_signature_256: Optional[str],
    secret_key: Optional[str] = None
) -> bool:
    """
    Validates Meta's POST HMAC-SHA256 signature from the 'X-Hub-Signature-256' header.
    Format: 'sha256=<hex_digest>'
    Uses hmac.compare_digest for constant-time comparison against timing attacks.
    """
    # In local testing/simulator, if no signature is provided and mock secret is active, permit simulation
    secret = secret_key or settings.META_APP_SECRET
    
    if not x_hub_signature_256:
        logger.warning("Missing X-Hub-Signature-256 header.")
        return False

    if not x_hub_signature_256.startswith("sha256="):
        logger.warning("Malformed X-Hub-Signature-256 header; must start with 'sha256='")
        return False

    expected_signature = x_hub_signature_256.split("sha256=", 1)[1].strip()

    # Compute HMAC-SHA256
    computed_mac = hmac.new(
        key=secret.encode("utf-8"),
        msg=request_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    is_valid = hmac.compare_digest(computed_mac, expected_signature)
    if not is_valid:
        logger.warning("HMAC-SHA256 signature mismatch. Unauthorized webhook payload.")
    return is_valid


def generate_test_signature(request_body: bytes, secret_key: Optional[str] = None) -> str:
    """
    Utility helper for test clients and simulators to generate valid signatures.
    """
    secret = secret_key or settings.META_APP_SECRET
    mac = hmac.new(
        key=secret.encode("utf-8"),
        msg=request_body,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={mac}"
