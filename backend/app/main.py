"""FastAPI application entry point.

Routers:
* /api/v1/citizen — OTP sign-in, report submission, "my reports" (Phase 1)
* /api/v1/public  — categories, jurisdictions, tickets; no login, no identity data
* /api/v1/gov     — official login, scoped work queue, ticket actions, fix proofs (Phase 2)
* /api/v1/admin   — platform operator: moderation (ban by report, no identity), audit log
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import admin, citizen, gov, public
from app.config import get_settings
from app.db import core_engine, vault_engine

app = FastAPI(title="RoadWatch API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(citizen.router)
app.include_router(public.router)
app.include_router(gov.router)
app.include_router(admin.router)

_settings = get_settings()
if _settings.storage_backend == "local":
    # Running without MinIO: serve the PUBLIC (sanitized) photo folder only. Originals
    # live in a different folder and are never exposed. Point S3_PUBLIC_BASE_URL at
    # http://localhost:8000/media for this mode.
    _public_dir = Path(_settings.local_storage_dir) / _settings.s3_bucket_public
    _public_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=_public_dir), name="media")


@app.get("/health")
def health() -> dict:
    """Checks both databases are reachable. The vault is only pinged, never queried."""
    status = {}
    for name, engine in (("core_db", core_engine()), ("vault_db", vault_engine())):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            status[name] = "ok"
        except Exception as exc:  # noqa: BLE001 — report any failure as unhealthy
            status[name] = f"error: {type(exc).__name__}"
    status["status"] = "ok" if all(v == "ok" for v in status.values()) else "degraded"
    return status
