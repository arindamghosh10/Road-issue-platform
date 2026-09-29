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
    # Base URL browsers use to fetch public photos.
    s3_public_base_url: str = "http://localhost:9000/photos-public"
    storage_backend: str = "s3"  # "s3" | "local" (folder on disk) | "memory" (tests)
    local_storage_dir: str = "./data/objects"

    # --- Identity vault secrets (held by the platform, NEVER by gov tenants) ---
    # Fernet key used to encrypt phone numbers at rest in the vault.
    vault_encryption_key: str | None = None
    # Secret "pepper" for keyed hashes (HMAC) of phone / Aadhaar. See app/security.
    identity_hash_pepper: str | None = None

    # --- Citizen auth -----------------------------------------------------------
    jwt_secret: str | None = None
    citizen_token_ttl_hours: int = 24 * 30
    otp_ttl_minutes: int = 5
    otp_max_attempts: int = 5
    otp_max_requests_per_hour: int = 5

    # --- Abuse protection (Phase 5) -------------------------------------------------
    rate_limit_backend: str = "redis"  # "redis" | "memory" (tests) | "off"
    trust_proxy: bool = False  # true only behind a reverse proxy that sets X-Forwarded-For
    # Play Integrity (Android) / App Attest (iOS) verifier: "stub" returns "not checked".
    attestation_provider: str = "stub"

    # --- Background jobs ----------------------------------------------------------
    # True: verification runs inside the upload request (tests, simple demos).
    # False: queued to the Celery worker via Redis.
    tasks_eager: bool = False

    # --- Verification pipeline (see app/verification) -----------------------------
    verification_threshold: float = 0.6
    max_upload_mb: int = 10
    max_gps_accuracy_m: float = 50.0  # worse than this lowers the score
    reject_gps_accuracy_m: float = 150.0  # worse than this is rejected outright
    max_photo_age_hours: int = 24
    road_snap_max_m: float = 50.0
    # Sample data has only a few road segments, so "not near a mapped road" only lowers
    # the score. Turn on once a full OSM road network has been imported.
    require_road_snap: bool = False
    require_attestation: bool = False  # Play Integrity / App Attest (stubbed)
    duplicate_phash_max_distance: int = 6  # bits of 64; lower = stricter "same photo"

    # --- Pluggable external services ------------------------------------------
    vision_provider: str = "stub"  # "stub" | "gemini"
    gemini_api_key: str | None = None
    # Any Gemini model that accepts images; check https://ai.google.dev for current names.
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_s: float = 30.0
    otp_provider: str = "stub"  # code is printed to the server log
    street_level_provider: str = "none"  # "none" | "mapillary"
    mapillary_token: str | None = None

    # --- Email (Mailpit locally) ------------------------------------------------
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    email_backend: str = "smtp"  # "smtp" | "log" (tests: record instead of sending)
    email_from: str = "RoadWatch <no-reply@roadwatch.local>"

    # --- Government workflow ------------------------------------------------------
    official_token_ttl_hours: int = 12
    sla_sweep_interval_s: int = 300  # how often the scheduler checks deadlines
    fix_proof_max_distance_m: float = 50.0  # default; tenants can override in config
    fix_proof_max_age_hours: int = 24
    confirmation_window_days: int = 7  # "no disputes within 7 days" closes the ticket
    min_confirm_ratio: float = 0.5

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

    @property
    def effective_jwt_secret(self) -> str:
        return self.jwt_secret or self._dev_fallback("jwt_secret")


@lru_cache
def get_settings() -> Settings:
    return Settings()
