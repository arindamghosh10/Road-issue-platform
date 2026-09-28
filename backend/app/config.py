"""Application settings, read from environment variables (or a `.env` file).

Every external service is selected by a setting (e.g. VISION_PROVIDER) so a free/stub
implementation can be swapped for a paid one without code changes. Defaults are chosen
so the whole stack runs offline with no API keys.
"""

import base64
import hashlib
import logging
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"  # "dev" | "test" | "prod"

    # --- Databases --------------------------------------------------------------
    # Two physically separate Postgres instances. The core DB never holds personal
    # data; the vault DB holds identity data and is only used by the auth service.
    core_database_url: str = "postgresql+psycopg://roadwatch_core:core_dev_pw@localhost:5432/roadwatch_core"
    vault_database_url: str = "postgresql+psycopg://roadwatch_vault:vault_dev_pw@localhost:5433/roadwatch_vault"

    redis_url: str = "redis://localhost:6379/0"

    # --- Object storage (MinIO locally, Cloudflare R2 when hosted) -------------
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "roadwatch"
    s3_secret_key: str = "roadwatch_dev_pw"
    s3_bucket_original: str = "photos-original"  # raw uploads, never shown to gov/public
    s3_bucket_public: str = "photos-public"  # sanitized copies (EXIF stripped, blurred)

    # --- Identity vault secrets (held by the platform, NEVER by gov tenants) ---
    # Fernet key used to encrypt phone numbers at rest in the vault.
    vault_encryption_key: str | None = None
    # Secret "pepper" for keyed hashes (HMAC) of phone / Aadhaar. See app/security.
    identity_hash_pepper: str | None = None

    # --- Pluggable external services ------------------------------------------
    vision_provider: str = "stub"  # "stub" | "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    otp_provider: str = "stub"  # code is printed to the server log
    street_level_provider: str = "none"  # "none" | "mapillary"
    mapillary_token: str | None = None

    # --- Email (Mailpit locally) ------------------------------------------------
    smtp_host: str = "localhost"
    smtp_port: int = 1025

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    def _dev_fallback(self, name: str) -> str:
        """Deterministic dev-only secret so `docker compose up` works with no setup.

        Refused outside dev/test: production must set real secrets explicitly.
        """
        if self.app_env not in ("dev", "test"):
            raise RuntimeError(f"{name.upper()} must be set when APP_ENV={self.app_env}")
        log.warning("Using a DEV-ONLY fallback for %s. Never use this in production.", name)
        return base64.urlsafe_b64encode(hashlib.sha256(f"roadwatch-dev-{name}".encode()).digest()).decode()

    @property
    def effective_vault_key(self) -> str:
        return self.vault_encryption_key or self._dev_fallback("vault_encryption_key")

    @property
    def effective_pepper(self) -> str:
        return self.identity_hash_pepper or self._dev_fallback("identity_hash_pepper")


@lru_cache
def get_settings() -> Settings:
    return Settings()
