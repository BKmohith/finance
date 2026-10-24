"""
app/core/config.py
Central application configuration loaded from environment variables or .env file.
Supports both Telegram Bot API and Meta WhatsApp Cloud API.
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Application Meta ---
    APP_NAME: str = "Sahayak Gateway & Ingestion Service"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # --- Communication Channel ---
    NOTIFICATION_CHANNEL: str = "telegram"  # "telegram" or "whatsapp"

    # --- Telegram Bot API ---
    TELEGRAM_BOT_TOKEN: str = "8205381745:AAFqdHI0ZmzfOArZ5NIvJG4ALEUimitGLfo"
    TELEGRAM_API_BASE: str = "https://api.telegram.org"
    ENABLE_TELEGRAM_POLLING: bool = True

    # --- Meta WhatsApp Cloud API ---
    WHATSAPP_API_TOKEN: str = "mock_token_dev_2026"
    WHATSAPP_PHONE_NUMBER_ID: str = "mock_phone_number_id"
    META_APP_SECRET: str = "mock_meta_app_secret_dev"
    WHATSAPP_VERIFY_TOKEN: str = "sahayak_hackathon_token_2026"
    META_GRAPH_API_VERSION: str = "v19.0"

    # --- Cache, Deduplication & Queue ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # --- Ingestion & Deduplication Constraints ---
    DEDUPLICATION_TTL_SECONDS: int = 172800  # 48 hours
    MAX_PAYLOAD_SIZE_BYTES: int = 16 * 1024 * 1024  # 16 MB max image upload

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
