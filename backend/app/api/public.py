"""Public (no login) API: categories, jurisdictions, tickets, ticket timelines.

ANONYMITY: responses are built by app/api/views.py from explicit models — aggregates and
sanitized photos only, never reporter ids, report ids, phone numbers or exact times.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from app.api import stats
from app.api.views import PublicTicket, TimelineEntry, build_tickets, build_timeline
from app.db import get_core_db
from app.models.core import Category, Jurisdiction, JurisdictionLevel, Ticket, TicketStatus

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.get("/categories")
def list_categories(db: Session = Depends(get_core_db)) -> list[dict]:
    rows = db.scalars(select(Category).order_by(Category.id))
    return [
        {"code": c.code, "name": c.name, "default_sla_hours": c.default_sla_hours} for c in rows
    ]


@router.get("/jurisdictions")
def list_jurisdictions(
    parent_id: int | None = None, db: Session = Depends(get_core_db)
) -> list[dict]:
    """Children of `parent_id` (or the roots). Used for drill-down: state → ward."""
    query = select(Jurisdiction).order_by(Jurisdiction.name)
    query = query.where(
        Jurisdiction.parent_id.is_(None) if parent_id is None else Jurisdiction.parent_id == parent_id
    )
    return [
        {"id": j.id, "lgd_code": j.lgd_code, "name": j.name, "level": j.level,
         "is_sample": j.is_sample}
        for j in db.scalars(query)
    ]


def ticket_filters(
    query,
    status: TicketStatus | None,
    category: str | None,
    jurisdiction_id: int | None,
    bbox: str | None,
    days: int | None = None,
):
    """Filters shared by the public and government ticket lists."""
    if days:
        query = query.where(Ticket.created_at >= datetime.now(UTC) - timedelta(days=days))
    if status:
        query = query.where(Ticket.status == status.value)
    if category:
        query = query.join(Category, Category.id == Ticket.category_id).where(Category.code == category)
    if jurisdiction_id is not None:
        query = query.where(Ticket.jurisdiction_path.any(jurisdiction_id))
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox.split(","))
        except ValueError:
            raise HTTPException(422, "bbox must be min_lon,min_lat,max_lon,max_lat") from None
        query = query.where(func.ST_Intersects(
            Ticket.location, func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        ))
    return query


@router.get("/tickets", response_model=list[PublicTicket])
def list_tickets(
    status: TicketStatus | None = None,
    category: str | None = None,
    jurisdiction_id: int | None = Query(None, description="Only tickets inside this area"),
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    days: int | None = Query(None, ge=1, le=3650, description="Only tickets reported in the last N days"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_core_db),
) -> list[PublicTicket]:
    query = select(Ticket).order_by(Ticket.priority.desc(), Ticket.created_at.desc()).limit(limit)
    query = ticket_filters(query, status, category, jurisdiction_id, bbox, days)
    return build_tickets(db, list(db.scalars(query)))


def _get(db: Session, ref: str) -> Ticket:
    ticket = db.scalar(select(Ticket).where(Ticket.public_ref == ref))
    if ticket is None:
        raise HTTPException(404, "Ticket not found.")
    return ticket


@router.get("/tickets/{ref}", response_model=PublicTicket)
def get_ticket(ref: str, db: Session = Depends(get_core_db)) -> PublicTicket:
    return build_tickets(db, [_get(db, ref)])[0]


# --- Dashboard statistics (see app/api/stats.py for definitions) ---------------------------


def _where(db, jurisdiction_id, category, days):
    return stats.filters(db, true(), jurisdiction_id, category, days)


FilterArgs = {
    "jurisdiction_id": Query(None, description="Only tickets inside this area"),
    "category": Query(None),
    "days": Query(None, ge=1, le=3650, description="Only tickets reported in the last N days"),
}


@router.get("/stats/summary", response_model=stats.Summary)
def stats_summary(jurisdiction_id: int | None = FilterArgs["jurisdiction_id"],
                  category: str | None = FilterArgs["category"],
                  days: int | None = FilterArgs["days"],
                  db: Session = Depends(get_core_db)) -> stats.Summary:
    return stats.summary(db, _where(db, jurisdiction_id, category, days))


@router.get("/stats/areas", response_model=list[stats.AreaRow])
def stats_areas(parent_id: int | None = Query(None, description="Children of this area"),
                level: JurisdictionLevel | None = Query(None, description="Or: every area at this level"),
                category: str | None = FilterArgs["category"],
                days: int | None = FilterArgs["days"],
                db: Session = Depends(get_core_db)) -> list[stats.AreaRow]:
    """Leaderboard / drill-down: best resolution rate first."""
    return stats.areas(db, _where(db, None, category, days), parent_id, level)


@router.get("/stats/authorities", response_model=list[stats.AuthorityRow])
def stats_authorities(jurisdiction_id: int | None = FilterArgs["jurisdiction_id"],
                      category: str | None = FilterArgs["category"],
                      days: int | None = FilterArgs["days"],
                      db: Session = Depends(get_core_db)) -> list[stats.AuthorityRow]:
    return stats.authorities(db, _where(db, jurisdiction_id, category, days))


@router.get("/stats/categories", response_model=list[stats.CategoryRow])
def stats_categories(jurisdiction_id: int | None = FilterArgs["jurisdiction_id"],
                     days: int | None = FilterArgs["days"],
                     db: Session = Depends(get_core_db)) -> list[stats.CategoryRow]:
    return stats.categories(db, _where(db, jurisdiction_id, None, days))


@router.get("/stats/trends", response_model=list[stats.TrendPoint])
def stats_trends(jurisdiction_id: int | None = FilterArgs["jurisdiction_id"],
                 category: str | None = FilterArgs["category"],
                 weeks: int = Query(12, ge=2, le=104),
                 db: Session = Depends(get_core_db)) -> list[stats.TrendPoint]:
    return stats.trends(db, _where(db, jurisdiction_id, category, None), weeks)


@router.get("/tickets/{ref}/timeline", response_model=list[TimelineEntry])
def get_timeline(ref: str, db: Session = Depends(get_core_db)) -> list[TimelineEntry]:
    """Public history: status changes, public notes, escalations, fix, confirmation result."""
    return build_timeline(db, _get(db, ref), gov=False)
