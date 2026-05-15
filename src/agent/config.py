"""Environment-based configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Immutable application settings loaded from environment."""

    model_config = {"frozen": True}

    anthropic_api_key: str = Field(min_length=1)
    unsplash_access_key: str = Field(min_length=1)
    gmail_username: str = Field(min_length=1)
    gmail_app_password: str = Field(min_length=1)
    gmail_recipient: str = Field(min_length=1)
    profile_path: Path
    db_path: Path
    log_level: str = "INFO"


_REQUIRED = (
    "ANTHROPIC_API_KEY",
    "UNSPLASH_ACCESS_KEY",
    "GMAIL_USERNAME",
    "GMAIL_APP_PASSWORD",
    "GMAIL_RECIPIENT",
    "PROFILE_PATH",
    "DB_PATH",
)


def load_settings() -> Settings:
    """Load settings from environment (and .env if present)."""
    load_dotenv(override=False)
    missing = [v for v in _REQUIRED if not os.environ.get(v)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    return Settings(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        unsplash_access_key=os.environ["UNSPLASH_ACCESS_KEY"],
        gmail_username=os.environ["GMAIL_USERNAME"],
        gmail_app_password=os.environ["GMAIL_APP_PASSWORD"],
        gmail_recipient=os.environ["GMAIL_RECIPIENT"],
        profile_path=Path(os.environ["PROFILE_PATH"]),
        db_path=Path(os.environ["DB_PATH"]),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
