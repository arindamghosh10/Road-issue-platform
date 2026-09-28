"""Response models for tickets, shared by the public and government APIs.

ANONYMITY: every field is copied explicitly from the database into these models. They
carry aggregates ("5 verified citizens reported this", "3 of 5 confirmed fixed") and
sanitized photos — never reporter ids, report ids, phone numbers, citizen actor ids or
exact report times. tests/test_phase1_flow.py and tests/test_phase2_gov.py scan every
public and government response to enforce this.
"""

import uuid
from datetime import date, datetime

from geoalchemy2.shape import to_shape
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import (
    ActorType,
    Authority,
    Category,
    Jurisdiction,
    Official,
    Report,
    ReportStatus,
    Ticket,
    TicketEvent,
)
from app.storage import public_url

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
    also_seen: int  # "I see this too" taps by citizens on site (no photo)
    reported_on: date
    sla_due_on: date | None
    resolved_on: date | None
    escalation_level: int
    responsible_area: str | None  # the level currently answerable (moves up on escalation)
    authority: str | None
    areas: list[Area]  # state → … → ward
    photos: list[str]


class GovTicket(PublicTicket):
    priority: float
    sla_due_at: datetime | None
    sla_hours_left: float | None
    assigned_to: str | None  # official's name
    created_at: datetime
    fix_submitted_at: datetime | None


class TimelineEntry(BaseModel):
    type: str
    on: date  # date only: exact times could help identify who reported
    by: str  # "system", "citizen" or (gov view only) an official's name
    details: dict


def build_tickets(db: Session, tickets: list[Ticket], gov: bool = False) -> list:
    if not tickets:
        return []
    categories = {c.id: c for c in db.scalars(select(Category))}
    authority_ids = {t.authority_id for t in tickets if t.authority_id}
    authorities = {
        a.id: a.name for a in db.scalars(select(Authority).where(Authority.id.in_(authority_ids)))
    }
    node_ids = {n for t in tickets for n in t.jurisdiction_path}
    nodes = {j.id: j for j in db.scalars(select(Jurisdiction).where(Jurisdiction.id.in_(node_ids)))}
    assignee_ids = {t.assigned_official_id for t in tickets if t.assigned_official_id}
    assignees = {
        o.id: o.name for o in db.scalars(select(Official).where(Official.id.in_(assignee_ids)))
    }
    photo_rows = db.execute(
        select(Report.ticket_id, Report.photo_public_key)
        .where(
            Report.ticket_id.in_([t.id for t in tickets]),
            Report.status == ReportStatus.VERIFIED.value,
            Report.photo_public_key.is_not(None),
        )
        .order_by(Report.received_at)
    ).all()
    photos: dict[uuid.UUID, list[str]] = {}
    for ticket_id, key in photo_rows:
        bucket = photos.setdefault(ticket_id, [])
        if len(bucket) < MAX_PHOTOS:
            bucket.append(public_url(key))

    now = datetime.now().astimezone()
    out = []
    for t in tickets:
        point = to_shape(t.location)
        category = categories[t.category_id]
        responsible = nodes.get(t.escalated_node_id)
        fields = {
            "ref": t.public_ref,
            "category": category.code,
            "category_name": category.name,
            "status": t.status,
            "severity": t.severity,
            "lat": round(point.y, 6),
            "lon": round(point.x, 6),
            "verified_reporters": t.unique_reporters,
            "report_count": t.report_count,
            "also_seen": t.seen_count,
            "reported_on": t.created_at.date(),
            "sla_due_on": t.sla_due_at.date() if t.sla_due_at else None,
            "resolved_on": t.resolved_at.date() if t.resolved_at else None,
            "escalation_level": t.escalation_level,
            "responsible_area": responsible.name if responsible else None,
            "authority": authorities.get(t.authority_id),
            "areas": [Area(id=nodes[n].id, name=nodes[n].name, level=nodes[n].level)
                   for n in t.jurisdiction_path if n in nodes],
            "photos": photos.get(t.id, []),
        }
        if gov:
            out.append(GovTicket(
                **fields,
                priority=t.priority,
                sla_due_at=t.sla_due_at,
                sla_hours_left=round((t.sla_due_at - now).total_seconds() / 3600, 1)
                if t.sla_due_at else None,
                assigned_to=assignees.get(t.assigned_official_id),
                created_at=t.created_at,
                fix_submitted_at=t.fix_submitted_at,
            ))
        else:
            out.append(PublicTicket(**fields))
    return out


# Event payload keys that may be shown. Anything else (present or future) is dropped.
SAFE_PAYLOAD_KEYS = {
    "category", "severity", "report_count", "unique_reporters", "from_status", "to_status",
    "note", "reason", "escalation_level", "to_node", "to_level", "at_top", "vision",
    "confirmed", "disputed", "reporters", "photo", "assigned_to", "also_seen",
}


def build_timeline(db: Session, ticket: Ticket, gov: bool) -> list[TimelineEntry]:
    events = db.scalars(
        select(TicketEvent).where(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.id)
    )
    official_names: dict[str, str] = {}
    entries = []
    for e in events:
        payload = e.payload or {}
        if not gov and not payload.get("public"):
            continue
        if e.actor_type == ActorType.OFFICIAL.value:
            if gov and e.actor_id not in official_names:
                o = db.get(Official, uuid.UUID(e.actor_id))
                official_names[e.actor_id] = o.name if o else "official"
            by = official_names.get(e.actor_id, "official") if gov else "official"
        elif e.actor_type == ActorType.CITIZEN.value:
            by = "citizen"  # never the reporter id
        else:
            by = "system"
        details = {k: v for k, v in payload.items() if k in SAFE_PAYLOAD_KEYS and v is not None}
        if "photo" in details:
            details["photo"] = public_url(details["photo"])
        entries.append(TimelineEntry(type=e.type, on=e.created_at.date(), by=by, details=details))
    return entries
