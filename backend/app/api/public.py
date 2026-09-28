"""Public (no login) API: categories, jurisdictions, tickets, ticket timelines.

ANONYMITY: responses are built by app/api/views.py from explicit models — aggregates and
sanitized photos only, never reporter ids, report ids, phone numbers or exact times.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.views import PublicTicket, TimelineEntry, build_tickets, build_timeline
from app.db import get_core_db
from app.models.core import Category, Jurisdiction, Ticket, TicketStatus

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
):
    """Filters shared by the public and government ticket lists."""
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
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_core_db),
) -> list[PublicTicket]:
    query = select(Ticket).order_by(Ticket.priority.desc(), Ticket.created_at.desc()).limit(limit)
    query = ticket_filters(query, status, category, jurisdiction_id, bbox)
    return build_tickets(db, list(db.scalars(query)))


def _get(db: Session, ref: str) -> Ticket:
    ticket = db.scalar(select(Ticket).where(Ticket.public_ref == ref))
    if ticket is None:
        raise HTTPException(404, "Ticket not found.")
    return ticket


@router.get("/tickets/{ref}", response_model=PublicTicket)
def get_ticket(ref: str, db: Session = Depends(get_core_db)) -> PublicTicket:
    return build_tickets(db, [_get(db, ref)])[0]


@router.get("/tickets/{ref}/timeline", response_model=list[TimelineEntry])
def get_timeline(ref: str, db: Session = Depends(get_core_db)) -> list[TimelineEntry]:
    """Public history: status changes, public notes, escalations, fix, confirmation result."""
    return build_timeline(db, _get(db, ref), gov=False)
