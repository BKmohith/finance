"""
app/workers/config.py
Dedicated worker configuration for Laptop 3 (Vision AI & OCR Worker).
Self-contained to eliminate cross-laptop git conflicts on app/core/config.py.
"""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class WorkerSettings:
    """Worker-specific configuration settings."""
    def __init__(self) -> None:
        self.GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
        self.GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        self.CELERY_RESULT_BACKEND: Optional[str] = os.getenv("CELERY_RESULT_BACKEND")


settings = WorkerSettings()
