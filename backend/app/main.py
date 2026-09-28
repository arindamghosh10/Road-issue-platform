"""FastAPI application entry point.

Routers:
* /api/v1/citizen — OTP sign-in, report submission, "my reports" (Phase 1)
* /api/v1/public  — categories, jurisdictions, tickets; no login, no identity data
Government endpoints arrive in Phase 2.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import citizen, public
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
