"""Government API: official login (+ optional 2FA), scoped work queue, ticket actions,
fix proofs, notifications, CSV export.

Every ticket lookup goes through app/gov/access.py, so an official can only see and act
on tickets under their own node (or on roads their authority owns). Tickets outside
their scope return 404, exactly like tickets that don't exist.

Nothing here exposes citizen identity: responses come from app/api/views.py, which
carries only aggregates and sanitized photos.
"""

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app import audit
from app.api import stats
from app.api.deps import current_official
from app.api.public import ticket_filters
from app.api.views import GovTicket, TimelineEntry, build_tickets, build_timeline
from app.db import get_core_db
from app.gov.access import get_scoped_ticket, ticket_scope
from app.models.core import (
    Jurisdiction,
    JurisdictionLevel,
    Notification,
    Official,
    OfficialRole,
    RecipientType,
    Ticket,
    TicketStatus,
)
from app.notifications.service import notify_officials
from app.security import totp
from app.security.passwords import verify_password
from app.security.ratelimit import client_ip, enforce
from app.security.tokens import issue_official_token
from app.tickets.lifecycle import TransitionError, add_event, assignable_officials, change_status
from app.tickets.resolution import FixProofError, submit_fix_proof, tally

router = APIRouter(prefix="/api/v1/gov", tags=["government"])


# --- Auth ---------------------------------------------------------------------------


class LoginIn(BaseModel):
    email: str
    password: str
    totp_code: str | None = Field(None, description="Required once 2FA is enabled")


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    node_id: int | None
    node: str | None
    node_level: str | None
    authority_id: int | None
    totp_enabled: bool


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_core_db)) -> TokenOut:
    ip = client_ip(request)
    email = body.email.strip().lower()
    # Two limits: per IP (one machine trying many accounts) and per account (many
    # machines guessing one password).
    enforce("gov_login_ip", ip, ip=ip)
    enforce("gov_login_email", email, ip=ip)
    official = db.scalar(select(Official).where(Official.email == email))
    # Same message for unknown email and wrong password: don't reveal which accounts exist.
    if official is None or not official.is_active or not verify_password(body.password, official.password_hash):
        audit.record("official_login", actor_type="official",
                     actor_id=str(official.id) if official else None, target=email[:128],
                     success=False, ip=ip, details={"reason": "bad_credentials"})
        raise HTTPException(401, "Wrong email or password.")
    if official.totp_enabled and not totp.verify(official.totp_secret, body.totp_code):
        audit.record("official_login", actor_type="official", actor_id=str(official.id),
                     success=False, ip=ip, details={"reason": "bad_2fa"})
        raise HTTPException(401, "Two-factor code required or incorrect.")
    audit.record("official_login", actor_type="official", actor_id=str(official.id), ip=ip,
                 details={"2fa": official.totp_enabled})
    return TokenOut(access_token=issue_official_token(str(official.id)))


@router.get("/me", response_model=MeOut)
def me(official: Official = Depends(current_official), db: Session = Depends(get_core_db)) -> MeOut:
    node = db.get(Jurisdiction, official.node_id) if official.node_id else None
    return MeOut(id=official.id, name=official.name, email=official.email, role=official.role,
                 node_id=official.node_id, node=node.name if node else None, node_level=node.level if node else None,
                 authority_id=official.authority_id, totp_enabled=official.totp_enabled)


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str  # render as a QR code for the authenticator app


@router.post("/auth/2fa/setup", response_model=TotpSetupOut)
def totp_setup(official: Official = Depends(current_official),
               db: Session = Depends(get_core_db)) -> TotpSetupOut:
    if official.totp_enabled:
        raise HTTPException(409, "Two-factor login is already enabled.")
    official.totp_secret = totp.new_secret()
    db.commit()
    return TotpSetupOut(secret=official.totp_secret,
                        otpauth_uri=totp.provisioning_uri(official.totp_secret, official.email))


class TotpEnableIn(BaseModel):
    code: str


@router.post("/auth/2fa/enable")
def totp_enable(body: TotpEnableIn, official: Official = Depends(current_official),
                db: Session = Depends(get_core_db)) -> dict:
    if not official.totp_secret or not totp.verify(official.totp_secret, body.code):
        raise HTTPException(400, "Code incorrect. Run setup, scan the QR code, then try again.")
    official.totp_enabled = True
    db.commit()
    audit.record("official_2fa_enabled", actor_type="official", actor_id=str(official.id))
    return {"totp_enabled": True}


# --- Tickets ------------------------------------------------------------------------


def _scoped(db: Session, official: Official, ref: str) -> Ticket:
    ticket = get_scoped_ticket(db, official, ref)
    if ticket is None:
        raise HTTPException(404, "Ticket not found.")
    return ticket


def _require_actor(official: Official) -> None:
    if official.role not in (OfficialRole.OFFICIAL.value, OfficialRole.GOV_ADMIN.value):
        raise HTTPException(403, "Your role cannot change tickets.")


def _queue_query(db: Session, official: Official, status, category, jurisdiction_id, bbox,
                 open_only: bool, days: int | None = None):
    query = select(Ticket).where(ticket_scope(db, official))
    if open_only and status is None:
        query = query.where(Ticket.status != TicketStatus.RESOLVED.value)
    query = ticket_filters(query, status, category, jurisdiction_id, bbox, days)
    # Work queue order: fix-submitted last (waiting on citizens), then highest priority,
    # then nearest deadline.
    waiting = case((Ticket.status == TicketStatus.FIX_SUBMITTED.value, 1), else_=0)
    return query.order_by(waiting, Ticket.priority.desc(), Ticket.sla_due_at.asc().nulls_last())


@router.get("/tickets", response_model=list[GovTicket])
def work_queue(
    status: TicketStatus | None = None,
    category: str | None = None,
    jurisdiction_id: int | None = None,
    bbox: str | None = None,
    open_only: bool = Query(True, description="Hide resolved tickets unless status is given"),
    assigned_to_me: bool = False,
    days: int | None = Query(None, ge=1, le=3650),
    limit: int = Query(200, ge=1, le=1000),
    official: Official = Depends(current_official),
    db: Session = Depends(get_core_db),
) -> list[GovTicket]:
    """Tickets in this official's area, most urgent first."""
    query = _queue_query(db, official, status, category, jurisdiction_id, bbox, open_only, days)
    if assigned_to_me:
        query = query.where(Ticket.assigned_official_id == official.id)
    return build_tickets(db, list(db.scalars(query.limit(limit))), gov=True)


@router.get("/tickets/export.csv")
def export_csv(
    status: TicketStatus | None = None,
    category: str | None = None,
    jurisdiction_id: int | None = None,
    official: Official = Depends(current_official),
    db: Session = Depends(get_core_db),
) -> StreamingResponse:
    enforce("gov_export_hour", str(official.id), actor_type="official", actor_id=str(official.id))
    query = _queue_query(db, official, status, category, jurisdiction_id, None, open_only=False)
    tickets = build_tickets(db, list(db.scalars(query.limit(50_000))), gov=True)
    audit.record("csv_export", actor_type="official", actor_id=str(official.id),
                 details={"rows": len(tickets), "status": status.value if status else None,
                          "category": category, "jurisdiction_id": jurisdiction_id})
    buf = io.StringIO()
    writer = csv.writer(buf)
    columns = ["ref", "category", "status", "severity", "priority", "verified_reporters",
               "report_count", "lat", "lon", "ward", "municipality", "district", "authority",
               "responsible_area", "escalation_level", "assigned_to", "created_at",
               "sla_due_at", "resolved_on"]
    writer.writerow(columns)
    for t in tickets:
        by_level = {a.level: a.name for a in t.areas}
        writer.writerow([
            t.ref, t.category, t.status, t.severity, t.priority, t.verified_reporters,
            t.report_count, t.lat, t.lon, by_level.get("ward"), by_level.get("municipality"),
            by_level.get("district"), t.authority, t.responsible_area, t.escalation_level,
            t.assigned_to, t.created_at.isoformat(),
            t.sla_due_at.isoformat() if t.sla_due_at else "", t.resolved_on or "",
        ])
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="roadwatch-tickets.csv"'},
    )


class GovTicketDetail(BaseModel):
    ticket: GovTicket
    timeline: list[TimelineEntry]
    confirmations: dict  # {"reporters": 5, "yes": 3, "no": 1, "partly": 0} — counts only


@router.get("/tickets/{ref}", response_model=GovTicketDetail)
def ticket_detail(ref: str, official: Official = Depends(current_official),
                  db: Session = Depends(get_core_db)) -> GovTicketDetail:
    ticket = _scoped(db, official, ref)
    t = tally(db, ticket)
    return GovTicketDetail(
        ticket=build_tickets(db, [ticket], gov=True)[0],
        timeline=build_timeline(db, ticket, gov=True),
        confirmations={"reporters": t.reporters, "yes": t.yes, "no": t.no, "partly": t.partly},
    )


class StatusIn(BaseModel):
    status: TicketStatus
    note: str | None = Field(None, max_length=1000)


@router.post("/tickets/{ref}/status", response_model=GovTicket)
def set_status(ref: str, body: StatusIn, official: Official = Depends(current_official),
               db: Session = Depends(get_core_db)) -> GovTicket:
    _require_actor(official)
    ticket = _scoped(db, official, ref)
    try:
        change_status(db, ticket, body.status.value, official, body.note)
    except TransitionError as exc:
        raise HTTPException(409, str(exc)) from None
    db.commit()
    return build_tickets(db, [ticket], gov=True)[0]


class AssignIn(BaseModel):
    official_id: uuid.UUID


class AssigneeOut(BaseModel):
    id: uuid.UUID
    name: str


@router.get("/tickets/{ref}/assignees", response_model=list[AssigneeOut])
def list_assignees(ref: str, official: Official = Depends(current_official),
                   db: Session = Depends(get_core_db)) -> list[AssigneeOut]:
    ticket = _scoped(db, official, ref)
    return [AssigneeOut(id=o.id, name=o.name) for o in assignable_officials(db, ticket)
            if o.tenant_id == official.tenant_id]


@router.post("/tickets/{ref}/assign", response_model=GovTicket)
def assign(ref: str, body: AssignIn, official: Official = Depends(current_official),
           db: Session = Depends(get_core_db)) -> GovTicket:
    _require_actor(official)
    ticket = _scoped(db, official, ref)
    target = db.get(Official, body.official_id)
    allowed = {o.id for o in assignable_officials(db, ticket) if o.tenant_id == official.tenant_id}
    if target is None or target.id not in allowed:
        raise HTTPException(422, "That official does not cover this ticket's area.")
    ticket.assigned_official_id = target.id
    add_event(db, ticket, "assigned", official=official, assigned_to=target.name)
    if target.id != official.id:
        notify_officials(db, [target], ticket, "assigned", f"Assigned to you: {ticket.public_ref}",
                         f"{official.name} assigned ticket {ticket.public_ref} to you.")
    db.commit()
    return build_tickets(db, [ticket], gov=True)[0]


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    public: bool = Field(False, description="Public notes appear on the public timeline")


@router.post("/tickets/{ref}/notes", response_model=list[TimelineEntry])
def add_note(ref: str, body: NoteIn, official: Official = Depends(current_official),
             db: Session = Depends(get_core_db)) -> list[TimelineEntry]:
    _require_actor(official)
    ticket = _scoped(db, official, ref)
    add_event(db, ticket, "note", official=official, public=body.public, note=body.text.strip())
    db.commit()
    return build_timeline(db, ticket, gov=True)


@router.post("/tickets/{ref}/fix-proof", response_model=GovTicket)
def fix_proof(
    ref: str,
    photo: UploadFile = File(...),
    lat: float = Form(...),
    lon: float = Form(...),
    captured_at: datetime = Form(...),
    capture_source: str = Form(..., description='Must be "in_app_camera"'),
    official: Official = Depends(current_official),
    db: Session = Depends(get_core_db),
) -> GovTicket:
    """Upload an after-repair photo taken at the site. Accepted → fix_submitted and the
    original reporters are asked to confirm. Refused → 422 with the reason."""
    _require_actor(official)
    enforce("gov_fix_proof_hour", str(official.id), actor_type="official", actor_id=str(official.id))
    ticket = _scoped(db, official, ref)
    if captured_at.tzinfo is None:
        raise HTTPException(422, "captured_at must include a timezone (ISO 8601).")
    try:
        submit_fix_proof(db, ticket, official, photo.file.read(), lat, lon, captured_at,
                         capture_source)
    except FixProofError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    db.commit()
    return build_tickets(db, [ticket], gov=True)[0]


# --- Dashboard statistics (scoped to the official's area) ------------------------------


def _scoped_where(db: Session, official: Official, jurisdiction_id, category, days):
    return stats.filters(db, ticket_scope(db, official), jurisdiction_id, category, days)


@router.get("/stats/summary", response_model=stats.Summary)
def stats_summary(jurisdiction_id: int | None = None, category: str | None = None,
                  days: int | None = Query(None, ge=1, le=3650),
                  official: Official = Depends(current_official),
                  db: Session = Depends(get_core_db)) -> stats.Summary:
    return stats.summary(db, _scoped_where(db, official, jurisdiction_id, category, days))


@router.get("/stats/areas", response_model=list[stats.AreaRow])
def stats_areas(parent_id: int | None = None, level: JurisdictionLevel | None = None,
                category: str | None = None, days: int | None = Query(None, ge=1, le=3650),
                official: Official = Depends(current_official),
                db: Session = Depends(get_core_db)) -> list[stats.AreaRow]:
    """Drill-down: children of `parent_id` (default: the official's own area)."""
    if parent_id is None and level is None:
        parent_id = official.node_id
    return stats.areas(db, _scoped_where(db, official, None, category, days), parent_id, level)


@router.get("/stats/authorities", response_model=list[stats.AuthorityRow])
def stats_authorities(jurisdiction_id: int | None = None, category: str | None = None,
                      days: int | None = Query(None, ge=1, le=3650),
                      official: Official = Depends(current_official),
                      db: Session = Depends(get_core_db)) -> list[stats.AuthorityRow]:
    return stats.authorities(db, _scoped_where(db, official, jurisdiction_id, category, days))


@router.get("/stats/categories", response_model=list[stats.CategoryRow])
def stats_categories(jurisdiction_id: int | None = None,
                     days: int | None = Query(None, ge=1, le=3650),
                     official: Official = Depends(current_official),
                     db: Session = Depends(get_core_db)) -> list[stats.CategoryRow]:
    return stats.categories(db, _scoped_where(db, official, jurisdiction_id, None, days))


@router.get("/stats/trends", response_model=list[stats.TrendPoint])
def stats_trends(jurisdiction_id: int | None = None, category: str | None = None,
                 weeks: int = Query(12, ge=2, le=104),
                 official: Official = Depends(current_official),
                 db: Session = Depends(get_core_db)) -> list[stats.TrendPoint]:
    return stats.trends(db, _scoped_where(db, official, jurisdiction_id, category, None), weeks)


@router.get("/stats/ageing", response_model=list[stats.AgeingBucket])
def stats_ageing(jurisdiction_id: int | None = None, category: str | None = None,
                 official: Official = Depends(current_official),
                 db: Session = Depends(get_core_db)) -> list[stats.AgeingBucket]:
    """Open backlog by age."""
    return stats.ageing(db, _scoped_where(db, official, jurisdiction_id, category, None))


# --- Notifications ------------------------------------------------------------------


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    ticket_ref: str | None
    created_at: datetime
    read: bool
    params: dict = {}  # values for the app's translated text, keyed on `kind`


def notification_rows(db: Session, recipient_type: str, recipient_id: str, unread_only: bool):
    query = (
        select(Notification, Ticket.public_ref)
        .outerjoin(Ticket, Ticket.id == Notification.ticket_id)
        .where(Notification.recipient_type == recipient_type,
               Notification.recipient_id == recipient_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(200)
    )
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    return [NotificationOut(id=n.id, kind=n.kind, title=n.title, body=n.body, ticket_ref=ref,
                            created_at=n.created_at, read=n.read_at is not None, params=n.params)
            for n, ref in db.execute(query)]


@router.get("/notifications", response_model=list[NotificationOut])
def my_notifications(unread_only: bool = False, official: Official = Depends(current_official),
                     db: Session = Depends(get_core_db)) -> list[NotificationOut]:
    return notification_rows(db, RecipientType.OFFICIAL.value, str(official.id), unread_only)


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, official: Official = Depends(current_official),
              db: Session = Depends(get_core_db)) -> dict:
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_type != RecipientType.OFFICIAL.value or n.recipient_id != str(official.id):
        raise HTTPException(404, "Notification not found.")
    n.read_at = n.read_at or datetime.now().astimezone()
    db.commit()
    return {"read": True}
