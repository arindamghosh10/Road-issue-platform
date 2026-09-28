"""FastAPI application entry point.

Phase 0 exposes only a health check and a couple of read-only public endpoints so the
seeded data can be inspected. Reporting, auth and gov workflows arrive in Phases 1–2.
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import core_engine, get_core_db, vault_engine
from app.models.core import Category, Jurisdiction

app = FastAPI(title="RoadWatch API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/v1/public/categories")
def list_categories(db: Session = Depends(get_core_db)) -> list[dict]:
    rows = db.scalars(select(Category).order_by(Category.id))
    return [
        {"code": c.code, "name": c.name, "default_sla_hours": c.default_sla_hours} for c in rows
    ]


@app.get("/api/v1/public/jurisdictions")
def list_jurisdictions(
    parent_id: int | None = None, db: Session = Depends(get_core_db)
) -> list[dict]:
    """Children of `parent_id` (or the roots). Used for drill-down: state → ward."""
    query = select(Jurisdiction).order_by(Jurisdiction.name)
    query = query.where(
        Jurisdiction.parent_id.is_(None) if parent_id is None else Jurisdiction.parent_id == parent_id
    )
    return [
        {
            "id": j.id,
            "lgd_code": j.lgd_code,
            "name": j.name,
            "level": j.level,
            "is_sample": j.is_sample,
        }
        for j in db.scalars(query)
    ]
