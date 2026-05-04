from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Tuple, Type

from pydantic import field_validator
from pydantic_settings import BaseSettings, DotEnvSettingsSource, EnvSettingsSource, SettingsConfigDict


def _comma_split_decode(field_name: str, field: Any, value: Any) -> Any:
    """Decode a list[str] field from either JSON or a comma-separated string."""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        raise


class _CommaSplittingEnvSource(EnvSettingsSource):
    """EnvSettingsSource that falls back to comma-splitting for list[str] fields."""

    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        return _comma_split_decode(field_name, field, value)


class _CommaSplittingDotEnvSource(DotEnvSettingsSource):
    """DotEnvSettingsSource that falls back to comma-splitting for list[str] fields."""

    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        return _comma_split_decode(field_name, field, value)


class Settings(BaseSettings):
    PROJECT_NAME: str = "Rental Price Tracker"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = ""
    DATABASE_HOST: str = "db"
    DATABASE_PORT: str = "5432"
    DATABASE_NAME: str = "rental_tracker"
    DATABASE_USER: str = "user"
    DATABASE_PASSWORD: str = "password"

    # Backend
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_RELOAD: bool = True
    # Frontend base URL used in notification links (no trailing slash)
    APP_BASE_URL: str = "http://localhost:3000"

    # CORS - comma-separated string in .env, validated into a list
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Scraping
    SCRAPE_INTERVAL_MINUTES: int = 60

    # Google Maps API
    GOOGLE_MAPS_API_KEY: str = ""

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"

    # Notification services
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "noreply@apttrack.app"
    # ECDSA public key from SendGrid dashboard → Settings → Mail Settings →
    # Event Webhook → Signature Verification.  Paste the full PEM block.
    # If empty, the webhook endpoint accepts all requests (dev/test only).
    SENDGRID_WEBHOOK_VERIFICATION_KEY: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ADMIN_CHAT_ID: str = ""  # chat_id for nightly scrape-digest messages
    TELEGRAM_WEBHOOK_SECRET: str = ""  # random string sent as X-Telegram-Bot-Api-Secret-Token header

    # API
    API_BASE_URL: str = "http://localhost:8000/api/v1"
    API_VERSION: str = "v1"

    # Logging
    LOG_LEVEL: str = "INFO"

    # MiniMax
    MINIMAX_API_KEY: str = ""

    # Demo subscription created on new user registration
    DEFAULT_DEMO_CITY: str = "San Jose"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def check_jwt_secret(cls, v: str) -> str:
        import os
        import warnings

        if v == "change-me-in-production":
            reload_flag = str(os.environ.get("BACKEND_RELOAD", "true")).lower()
            if reload_flag != "true":
                raise ValueError(
                    "JWT_SECRET_KEY is still set to the default value. "
                    "Set a strong secret in your .env before running in production."
                )
            warnings.warn(
                "JWT_SECRET_KEY is using the default value — change it in .env before deploying!",
                stacklevel=2,
            )
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> Tuple[Any, ...]:
        return (
            init_settings,
            _CommaSplittingEnvSource(settings_cls),
            _CommaSplittingDotEnvSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()
