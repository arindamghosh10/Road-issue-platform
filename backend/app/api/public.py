"""Public (no login) API: categories, jurisdictions, tickets.

ANONYMITY: responses here are built field-by-field from explicit Pydantic models. They
contain aggregates ("5 verified citizens reported this") and sanitized photos only —
never reporter ids, report ids, phone numbers or exact capture times.
tests/test_phase1_flow.py scans these responses to enforce that.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.shape import to_shape
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_core_db
from app.models.core import (
    Authority,
    Category,
    Jurisdiction,
    Report,
    ReportStatus,
    Ticket,
    TicketStatus,
)
from app.storage import public_url

router = APIRouter(prefix="/api/v1/public", tags=["public"])

MAX_PHOTOS = 6


class Area(BaseModel):
    id: int
    name: str
    level: str


class PublicTicket(BaseModel):
    ref: str
    category: str
    category_name: str
    status: str
    severity: int
    lat: float
    lon: float
    verified_reporters: int
    report_count: int
    reported_on: date
    sla_due_on: date | None
    resolved_on: date | None
    escalation_level: int
    authority: str | None
    areas: list[Area]  # state → … → ward
    photos: list[str]


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


def _serialize(db: Session, tickets: list[Ticket]) -> list[PublicTicket]:
    if not tickets:
        return []
    categories = {c.id: c for c in db.scalars(select(Category))}
    authority_ids = {t.authority_id for t in tickets if t.authority_id}
    authorities = {
        a.id: a.name for a in db.scalars(select(Authority).where(Authority.id.in_(authority_ids)))
    }
    node_ids = {n for t in tickets for n in t.jurisdiction_path}
    nodes = {j.id: j for j in db.scalars(select(Jurisdiction).where(Jurisdiction.id.in_(node_ids)))}
    photo_rows = db.execute(
        select(Report.ticket_id, Report.photo_public_key)
        .where(
            Report.ticket_id.in_([t.id for t in tickets]),
            Report.status == ReportStatus.VERIFIED.value,
            Report.photo_public_key.is_not(None),
        )
        .order_by(Report.received_at)
    ).all()
    photos: dict = {}
    for ticket_id, key in photo_rows:
        photos.setdefault(ticket_id, [])
        if len(photos[ticket_id]) < MAX_PHOTOS:
            photos[ticket_id].append(public_url(key))

    out = []
    for t in tickets:
        point = to_shape(t.location)
        category = categories[t.category_id]
        out.append(PublicTicket(
            ref=t.public_ref,
            category=category.code,
            category_name=category.name,
            status=t.status,
            severity=t.severity,
            lat=round(point.y, 6),
            lon=round(point.x, 6),
            verified_reporters=t.unique_reporters,
            report_count=t.report_count,
            reported_on=t.created_at.date(),
            sla_due_on=t.sla_due_at.date() if t.sla_due_at else None,
            resolved_on=t.resolved_at.date() if t.resolved_at else None,
            escalation_level=t.escalation_level,
            authority=authorities.get(t.authority_id),
            areas=[Area(id=nodes[n].id, name=nodes[n].name, level=nodes[n].level)
                   for n in t.jurisdiction_path if n in nodes],
            photos=photos.get(t.id, []),
        ))
    return out


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
    return _serialize(db, list(db.scalars(query)))


@router.get("/tickets/{ref}", response_model=PublicTicket)
def get_ticket(ref: str, db: Session = Depends(get_core_db)) -> PublicTicket:
    ticket = db.scalar(select(Ticket).where(Ticket.public_ref == ref))
    if ticket is None:
        raise HTTPException(404, "Ticket not found.")
    return _serialize(db, [ticket])[0]
