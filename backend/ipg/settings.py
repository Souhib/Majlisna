import json
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_env_file() -> tuple[str, ...]:
    """Determine which .env files to load based on IPG_ENV."""
    env = os.getenv("IPG_ENV")
    if not env:
        selector_path = Path(".env")
        if selector_path.exists():
            load_dotenv(selector_path, override=False)
            selector = dotenv_values(selector_path)
            env = selector.get("IPG_ENV", "development")
        else:
            env = "development"

    env_file = f".env.{env}"
    load_dotenv(env_file, override=False)
    return (".env", env_file)


class Settings(BaseSettings):
    """Application settings with multi-environment support."""

    model_config = SettingsConfigDict(env_file=_get_env_file(), env_file_encoding="utf-8")

    # Environment Selector
    ipg_env: str = "development"

    # Database
    database_url: str

    # JWT Authentication
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    jwt_encryption_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Environment
    environment: str = "development"

    # Logging
    log_level: str = "DEBUG"
    logfire_token: str = ""

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Redis
    redis_url: str = ""

    # Sentry
    sentry_dsn: str = ""

    # CORS
    cors_origins: str = ""

    @field_validator("cors_origins")
    @classmethod
    def parse_cors_origins(cls, v: str) -> list[str]:
        """Parse JSON arrays or comma-separated strings into lists."""
        if v.startswith("["):
            return json.loads(v)
        return [item.strip() for item in v.split(",") if item.strip()]
