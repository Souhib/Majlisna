import json
import os
from pathlib import Path
from typing import Annotated

from dotenv import dotenv_values, load_dotenv
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _get_env_file() -> tuple[str, ...]:
    """Determine which .env files to load based on MAJLISNA_ENV."""
    env = os.getenv("MAJLISNA_ENV")
    if not env:
        selector_path = Path(".env")
        if selector_path.exists():
            load_dotenv(selector_path, override=False)
            selector = dotenv_values(selector_path)
            env = selector.get("MAJLISNA_ENV", "development")
        else:
            env = "development"

    env_file = f".env.{env}"
    load_dotenv(env_file, override=False)
    return (".env", env_file)


class Settings(BaseSettings):
    """Application settings with multi-environment support."""

    model_config = SettingsConfigDict(env_file=_get_env_file(), env_file_encoding="utf-8")

    # Legacy selector variable. Not read by the app (the selector logic uses
    # MAJLISNA_ENV), but the `.env` files still carry an `IPG_ENV=...` line from
    # before the rename. Because BaseSettings forbids extra inputs, this field
    # must exist to absorb that line — removing it makes Settings() fail to load.
    ipg_env: str = "development"

    # Database
    database_url: str

    # Direct PostgreSQL URL that BYPASSES PgBouncer, for admin scripts that run
    # DDL (scripts/generate_fake_data.py).
    #
    # asyncpg caches type introspection per connection. Under PgBouncer's
    # transaction pooling, a DROP/CREATE of every table invalidates those types
    # while pooled server connections keep the stale cache, and the next bulk
    # INSERT dies with "could not resolve query result and/or argument types in
    # N attempts". Reproducible 3/3 through PgBouncer, 3/3 fine when direct.
    #
    # Empty means "use database_url" — correct for SQLite dev, where there is no
    # PgBouncer in the path.
    direct_database_url: str = ""

    # Redis (Socket.IO cross-worker pub/sub)
    redis_url: str = "redis://redis:6379/0"

    # JWT Authentication
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    jwt_encryption_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # Environment
    environment: str = "development"

    # Logging
    log_level: str = "DEBUG"
    logfire_token: str = ""

    # Server
    port: int = 5111

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Sentry
    sentry_dsn: str = ""

    # Email (Resend)
    resend_api_key: str = ""
    from_email: str = "Majlisna <noreply@majlisna.app>"

    # Google OAuth
    google_client_id_web: str = ""

    # CORS
    #
    # Typed as the list it actually is. It used to be declared `str` with an
    # "after" validator returning a list, which made the annotation a lie: mypy
    # (and any reader) saw a str, so `x in settings.cors_origins` type-checked as a
    # SUBSTRING test rather than membership, and serialising Settings emitted a
    # PydanticSerializationUnexpectedValue warning on every test run.
    #
    # `NoDecode` is what makes `list[str]` usable here: without it pydantic-settings
    # treats a list field as complex and tries `json.loads` on the raw env value
    # BEFORE validators run, so a plain `a,b` string raises SettingsError. With it,
    # the raw string reaches the "before" validator below.
    cors_origins: Annotated[list[str], NoDecode] = []

    # Emails allowed to reach the game-content endpoints (undercover words and
    # term pairs, codenames word packs). Comma-separated or a JSON array.
    #
    # There is no admin column on User and no migration mechanism, so membership
    # is configuration rather than data. Empty means NOBODY is an admin — content
    # is seeded by scripts/generate_fake_data.py, so a deployment that never sets
    # this loses nothing. Fail-closed is deliberate: those endpoints previously
    # accepted any logged-in user, i.e. any player could DELETE every word in the
    # game, and could read the full term-pair list — which, next to the word
    # their own role hands them, reveals the opposing word outright.
    admin_emails: Annotated[list[str], NoDecode] = []

    # Auth flags
    # When True, email/password users must verify their email before they can log
    # in. Off by default so enabling it is a deliberate choice (requires working
    # SMTP and a tested verification flow, and would lock out unverified accounts).
    require_email_verification: bool = False

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Reject the default dev JWT secret in production.

        Must be a model-level (mode="after") validator: a field_validator on
        jwt_secret_key cannot see `environment` because that field is declared
        later, so `info.data` would not yet contain it and the guard would
        silently never trigger.
        """
        if self.environment == "production" and self.jwt_secret_key == "dev-secret-key-change-in-production":
            msg = "JWT_SECRET_KEY must be changed from the default value in production"
            raise ValueError(msg)
        return self

    @field_validator("cors_origins", "admin_emails", mode="before")
    @classmethod
    def parse_string_list(cls, v: object) -> list[str]:
        """Accept a JSON array, a comma-separated string, or an actual list.

        Runs in "before" mode because the fields are declared `list[str]` (see
        cors_origins) — the raw env value arrives here as a str, while a default or a
        direct `Settings(cors_origins=[...])` arrives already as a list.
        """
        if v is None:
            return []
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        text = str(v).strip()
        if not text:
            return []
        if text.startswith("["):
            return [str(item).strip() for item in json.loads(text) if str(item).strip()]
        return [item.strip() for item in text.split(",") if item.strip()]
