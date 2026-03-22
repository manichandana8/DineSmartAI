"""
Load `.env` from the project root (folder that contains `main.py`), then read settings
from the process environment. This works no matter which directory you start uvicorn from.
"""

from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

if _ENV_FILE.is_file():
    # .env wins over the shell so an empty `export GOOGLE_PLACES_API_KEY=` cannot block your real key.
    load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # LLM: Gemini (Google AI Studio / GCP-style API key) — preferred when set
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_AI_API_KEY"),
    )
    gemini_model: str = "gemini-2.0-flash"

    # LLM fallback: OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    google_places_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_PLACES_API_KEY", "GOOGLE_MAPS_API_KEY"),
    )
    # Retell AI — outbound calls for agent-handled reservations / phone orders (Bearer API key).
    retell_api_key: str = Field(default="", validation_alias=AliasChoices("RETELL_API_KEY"))
    retell_from_number: str = Field(
        default="",
        description="E.164 from-number registered in Retell (e.g. +14155550100).",
        validation_alias=AliasChoices("RETELL_FROM_NUMBER"),
    )
    retell_agent_id: str = Field(
        default="",
        description="Optional override_agent_id for create-phone-call when not bound to the number.",
        validation_alias=AliasChoices("RETELL_AGENT_ID"),
    )
    public_base_url: str = Field(
        default="",
        description="Public URL for booking portal links (e.g. https://yourapp.com). Falls back to http://127.0.0.1:8000.",
        validation_alias=AliasChoices("PUBLIC_BASE_URL", "PUBLIC_APP_URL"),
    )
    resend_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("RESEND_API_KEY"),
    )
    booking_from_email: str = Field(
        default="",
        description="From address for Resend (verify domain in Resend dashboard).",
        validation_alias=AliasChoices("BOOKING_FROM_EMAIL"),
    )
    booking_demo_notify_email: str = Field(
        default="",
        description="Optional inbox that always receives booking emails (demo / QA).",
        validation_alias=AliasChoices("BOOKING_DEMO_NOTIFY_EMAIL"),
    )
    database_url: str = "sqlite:///./smartdine.db"

    cors_origins: str = "*"
    trusted_hosts: str = ""

    host: str = "127.0.0.1"
    port: int = 8000

    @field_validator(
        "google_places_api_key",
        "openai_api_key",
        "gemini_api_key",
        "retell_api_key",
        "retell_from_number",
        "retell_agent_id",
        "public_base_url",
        "resend_api_key",
        "booking_from_email",
        "booking_demo_notify_email",
        mode="before",
    )
    @classmethod
    def strip_whitespace(cls, v: object) -> str:
        if v is None:
            return ""
        s = str(v).strip().strip('"').strip("'")
        return s.lstrip("\ufeff")

    def cors_origin_list(self) -> List[str]:
        raw = (self.cors_origins or "*").strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def trusted_host_list(self) -> Optional[List[str]]:
        raw = (self.trusted_hosts or "").strip()
        if not raw:
            return None
        return [h.strip() for h in raw.split(",") if h.strip()]


def get_settings() -> Settings:
    """New instance each time so edits to `.env` apply after restart (no stale cache)."""
    return Settings()
