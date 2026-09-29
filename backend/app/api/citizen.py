"""Citizen API: phone OTP sign-in, submitting reports, tracking one's own reports.

These endpoints know the caller's opaque reporter_id (from the token) but never any
identity details — those stay in the vault.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import audit
from app.api.deps import current_reporter_id
from app.api.gov import NotificationOut, notification_rows
from app.api.views import PublicTicket, build_tickets
from app.db import get_core_db
from app.identity import push
from app.identity.service import AuthError, request_otp, verify_otp
from app.models.core import (
    ActorType,
    Category,
    FixConfirmation,
    FixProof,
    FixResponse,
    RecipientType,
    Report,
    ReportStatus,
    RoadSegment,
    Ticket,
    TicketEvent,
    TicketSighting,
    TicketStatus,
)
from app.reports.service import NewReport, ReportError, create_report, enqueue_processing
from app.security.ratelimit import client_ip, enforce
from app.security.tokens import issue_citizen_token
from app.storage import public_url
from app.tickets.priority import compute_priority
from app.tickets.resolution import ConfirmationError, record_confirmation

router = APIRouter(prefix="/api/v1/citizen", tags=["citizen"])

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


class OtpRequest(BaseModel):
    phone: str = Field(examples=["9876543210"])


class OtpRequested(BaseModel):
    challenge_id: uuid.UUID
    message: str = "Code sent."


class OtpVerify(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(min_length=4, max_length=8)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CheckOut(BaseModel):
    name: str
    passed: bool
    reason: str  # English fallback
    code: str = ""  # translatable id, e.g. "capture.too_old" ("" on reports made before codes)
    params: dict = {}


class MyReport(BaseModel):
    id: uuid.UUID
    status: str
    category: str
    submitted_on: date
    rejection_reason: str | None  # English fallback
    rejection_code: str | None = None  # translatable id (a check code, "low_score", …)
    rejection_params: dict = {}
    ticket_ref: str | None
    checks: list[CheckOut]


@router.post("/auth/otp/request", response_model=OtpRequested)
def otp_request(body: OtpRequest, request: Request) -> OtpRequested:
    # Per-IP limit here; the identity service also limits codes per phone number.
    enforce("otp_request_ip", client_ip(request), ip=client_ip(request))
    try:
        return OtpRequested(challenge_id=request_otp(body.phone))
    except AuthError as exc:
        raise HTTPException(exc.status_code, exc.message) from None


@router.post("/auth/otp/verify", response_model=TokenOut)
def otp_verify(body: OtpVerify, request: Request) -> TokenOut:
    enforce("otp_verify_ip", client_ip(request), ip=client_ip(request))
    try:
        reporter_id = verify_otp(body.challenge_id, body.code)
    except AuthError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    # Citizen audit records carry the opaque id only — never IP or phone.
    audit.record("citizen_login", actor_type="citizen", actor_id=reporter_id)
    return TokenOut(access_token=issue_citizen_token(reporter_id))


def _to_my_report(report: Report, category_code: str, ticket_ref: str | None) -> MyReport:
    details = report.verification_details or {}
    checks = details.get("checks", [])
    rejection = details.get("rejection") or {}
    return MyReport(
        id=report.id,
        status=report.status,
        category=category_code,
        submitted_on=report.received_at.date(),
        rejection_reason=report.rejection_reason,
        rejection_code=rejection.get("code") if report.rejection_reason else None,
        rejection_params=rejection.get("params", {}) if report.rejection_reason else {},
        ticket_ref=ticket_ref,
        checks=[CheckOut(name=c["name"], passed=not c["hard_fail"] and c["score"] >= 0.5,
                         reason=c["reason"], code=c.get("code", ""), params=c.get("params", {}))
                for c in checks],
    )


@router.post("/reports", response_model=MyReport, status_code=status.HTTP_202_ACCEPTED)
def submit_report(
    photo: UploadFile = File(...),
    category: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    gps_accuracy_m: float | None = Form(None),
    captured_at: datetime = Form(...),
    capture_source: str = Form(..., description='Must be "in_app_camera"; gallery uploads are refused.'),
    attestation_token: str | None = Form(None),
    description: str | None = Form(None, max_length=1000),
    reporter_id: str = Depends(current_reporter_id),
    db: Session = Depends(get_core_db),
) -> MyReport:
    """Submit a photo report. Verification runs in the background; poll GET /reports/{id}."""
    for rule in ("report_hour", "report_day"):
        enforce(rule, reporter_id, actor_type="citizen", actor_id=reporter_id)
    if capture_source != "in_app_camera":
        raise HTTPException(422, "Only photos taken with the in-app camera are accepted.")
    if (photo.content_type or "") not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(415, "Photo must be JPEG, PNG, WebP or HEIC.")
    if captured_at.tzinfo is None:
        raise HTTPException(422, "captured_at must include a timezone (ISO 8601).")
    try:
        report = create_report(db, NewReport(
            reporter_id=reporter_id, category_code=category, lat=lat, lon=lon,
            gps_accuracy_m=gps_accuracy_m, captured_at=captured_at,
            capture_source=capture_source, attestation_token=attestation_token,
            description=description, photo=photo.file.read(),
            photo_content_type=photo.content_type or "application/octet-stream",
        ))
    except ReportError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    enqueue_processing(report.id)
    return get_my_report(report.id, reporter_id, db)


@router.get("/reports", response_model=list[MyReport])
def list_my_reports(
    reporter_id: str = Depends(current_reporter_id), db: Session = Depends(get_core_db)
) -> list[MyReport]:
    rows = db.execute(
        select(Report, Category.code, Ticket.public_ref)
        .join(Category, Category.id == Report.category_id)
        .outerjoin(Ticket, Ticket.id == Report.ticket_id)
        .where(Report.reporter_id == reporter_id)
        .order_by(Report.received_at.desc())
        .limit(200)
    ).all()
    return [_to_my_report(r, code, ref) for r, code, ref in rows]


class PendingConfirmation(BaseModel):
    ticket_ref: str
    category: str
    fix_submitted_on: date | None
    fix_photos: list[str]
    my_answer: str | None


class ConfirmIn(BaseModel):
    response: FixResponse


class ConfirmOut(BaseModel):
    ticket_ref: str
    ticket_status: str


@router.get("/confirmations", response_model=list[PendingConfirmation])
def pending_confirmations(
    reporter_id: str = Depends(current_reporter_id), db: Session = Depends(get_core_db)
) -> list[PendingConfirmation]:
    """Tickets I reported whose fix is waiting for my Yes / No / Partly."""
    rows = db.execute(
        select(Ticket, Category.code, FixConfirmation.response)
        .join(Category, Category.id == Ticket.category_id)
        .outerjoin(FixConfirmation, (FixConfirmation.ticket_id == Ticket.id)
                   & (FixConfirmation.reporter_id == reporter_id))
        .where(
            Ticket.status == TicketStatus.FIX_SUBMITTED.value,
            Ticket.id.in_(select(Report.ticket_id).where(
                Report.reporter_id == reporter_id, Report.status == ReportStatus.VERIFIED.value)),
        )
    ).all()
    out = []
    for ticket, code, answer in rows:
        keys = db.scalar(
            select(FixProof.photo_keys).where(FixProof.ticket_id == ticket.id, FixProof.accepted)
            .order_by(FixProof.created_at.desc()).limit(1)
        ) or []
        out.append(PendingConfirmation(
            ticket_ref=ticket.public_ref, category=code,
            fix_submitted_on=ticket.fix_submitted_at.date() if ticket.fix_submitted_at else None,
            fix_photos=[public_url(k) for k in keys], my_answer=answer,
        ))
    return out


@router.post("/tickets/{ref}/confirm", response_model=ConfirmOut)
def confirm_fix(
    ref: str,
    body: ConfirmIn,
    reporter_id: str = Depends(current_reporter_id),
    db: Session = Depends(get_core_db),
) -> ConfirmOut:
    """Answer "Is this fixed?" for a ticket I reported. The government only sees totals."""
    enforce("confirm_hour", reporter_id, actor_type="citizen", actor_id=reporter_id)
    ticket = db.scalar(select(Ticket).where(Ticket.public_ref == ref).with_for_update())
    if ticket is None:
        raise HTTPException(404, "Ticket not found.")
    try:
        status_after = record_confirmation(db, ticket, reporter_id, body.response.value)
    except ConfirmationError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    db.commit()
    return ConfirmOut(ticket_ref=ticket.public_ref, ticket_status=status_after)


SIGHTING_MAX_DISTANCE_M = 150.0
SIGHTING_MAX_ACCURACY_M = 100.0


class NearbyTicket(PublicTicket):
    distance_m: float
    i_reported: bool
    i_saw: bool


@router.get("/tickets/nearby", response_model=list[NearbyTicket])
def nearby_tickets(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: float = Query(1500, gt=0, le=5000),
    reporter_id: str = Depends(current_reporter_id),
    db: Session = Depends(get_core_db),
) -> list[NearbyTicket]:
    """Issues around me, nearest first: unresolved ones plus those fixed in the last 30 days."""
    here = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    distance = func.ST_Distance(func.Geography(Ticket.location), func.Geography(here))
    recent_fix = Ticket.resolved_at >= datetime.now(UTC) - timedelta(days=30)
    rows = db.execute(
        select(Ticket, distance)
        .where(func.ST_DWithin(func.Geography(Ticket.location), func.Geography(here), radius_m),
               (Ticket.status != TicketStatus.RESOLVED.value) | recent_fix)
        .order_by(distance).limit(100)
    ).all()
    tickets = [t for t, _ in rows]
    ids = [t.id for t in tickets]
    mine = set(db.scalars(select(Report.ticket_id).where(
        Report.reporter_id == reporter_id, Report.ticket_id.in_(ids)))) if ids else set()
    seen = set(db.scalars(select(TicketSighting.ticket_id).where(
        TicketSighting.reporter_id == reporter_id, TicketSighting.ticket_id.in_(ids)))) if ids else set()
    views = build_tickets(db, tickets)
    return [NearbyTicket(**v.model_dump(), distance_m=round(float(d), 1),
                         i_reported=t.id in mine, i_saw=t.id in seen)
            for v, (t, d) in zip(views, rows, strict=True)]


class SightingIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    gps_accuracy_m: float = Field(gt=0)


class SightingOut(BaseModel):
    ticket_ref: str
    also_seen: int


@router.post("/tickets/{ref}/seen", response_model=SightingOut)
def i_see_this_too(
    ref: str,
    body: SightingIn,
    reporter_id: str = Depends(current_reporter_id),
    db: Session = Depends(get_core_db),
) -> SightingOut:
    """ "I see this too": confirm an existing issue while standing near it (no photo).
    One per citizen per ticket; counts publicly as a sighting, not a verified report."""
    enforce("sighting_hour", reporter_id, actor_type="citizen", actor_id=reporter_id)
    ticket = db.scalar(select(Ticket).where(Ticket.public_ref == ref).with_for_update())
    if ticket is None:
        raise HTTPException(404, "Ticket not found.")
    if ticket.status == TicketStatus.RESOLVED.value:
        raise HTTPException(409, "This issue is already resolved.")
    if body.gps_accuracy_m > SIGHTING_MAX_ACCURACY_M:
        raise HTTPException(422, "GPS location is too imprecise. Try again outdoors.")
    if db.scalar(select(Report.id).where(Report.ticket_id == ticket.id,
                                         Report.reporter_id == reporter_id).limit(1)):
        raise HTTPException(409, "You already reported this issue.")
    here = func.ST_SetSRID(func.ST_MakePoint(body.lon, body.lat), 4326)
    distance = float(db.scalar(select(func.ST_Distance(
        func.Geography(Ticket.location), func.Geography(here))).where(Ticket.id == ticket.id)))
    if distance > SIGHTING_MAX_DISTANCE_M:
        raise HTTPException(422, f"You need to be within {SIGHTING_MAX_DISTANCE_M:.0f} m of the issue "
                                 f"(you are about {distance:.0f} m away).")
    inserted = db.execute(
        insert(TicketSighting)
        .values(ticket_id=ticket.id, reporter_id=reporter_id, distance_m=round(distance, 1))
        .on_conflict_do_nothing()
        .returning(TicketSighting.ticket_id)
    ).first()
    if inserted is None:
        raise HTTPException(409, "You already confirmed this issue.")
    ticket.seen_count += 1
    road_class = (db.scalar(select(RoadSegment.road_class).where(RoadSegment.id == ticket.road_segment_id))
                  if ticket.road_segment_id else None)
    ticket.priority = compute_priority(
        ticket.severity, ticket.unique_reporters, road_class,
        (datetime.now(UTC) - ticket.created_at).total_seconds() / 86400, ticket.seen_count)
    db.add(TicketEvent(ticket_id=ticket.id, type="sighting", actor_type=ActorType.CITIZEN.value,
                       actor_id=reporter_id, payload={"also_seen": ticket.seen_count}))
    db.commit()
    return SightingOut(ticket_ref=ticket.public_ref, also_seen=ticket.seen_count)


@router.get("/notifications", response_model=list[NotificationOut])
def my_notifications(
    unread_only: bool = False,
    reporter_id: str = Depends(current_reporter_id),
    db: Session = Depends(get_core_db),
) -> list[NotificationOut]:
    return notification_rows(db, RecipientType.REPORTER.value, reporter_id, unread_only)


class PushTokenIn(BaseModel):
    token: str = Field(max_length=250, examples=["ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"])
    platform: str = Field(examples=["android"])
    lang: str = Field("en", examples=["hi"], description="App language for the push text: en, hi or bn.")


class PushTokenRef(BaseModel):
    token: str = Field(max_length=250)


@router.put("/push-token", status_code=status.HTTP_204_NO_CONTENT)
def register_push_token(body: PushTokenIn, reporter_id: str = Depends(current_reporter_id)) -> None:
    """Receive a push when there's news on your reports. The token is kept encrypted in
    the identity vault, never with reports; pushes say only "you have an update"."""
    enforce("push_token_hour", reporter_id, actor_type="citizen", actor_id=reporter_id)
    try:
        push.register_token(reporter_id, body.token, body.platform, body.lang)
    except push.PushError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/push-token/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_push_token(body: PushTokenRef, reporter_id: str = Depends(current_reporter_id)) -> None:
    """Stop pushes to this device (called on sign-out)."""
    enforce("push_token_hour", reporter_id, actor_type="citizen", actor_id=reporter_id)
    push.unregister_token(reporter_id, body.token)


@router.get("/reports/{report_id}", response_model=MyReport)
def get_my_report(
    report_id: uuid.UUID,
    reporter_id: str = Depends(current_reporter_id),
    db: Session = Depends(get_core_db),
) -> MyReport:
    db.expire_all()  # the worker may have updated the row since this session loaded it
    row = db.execute(
        select(Report, Category.code, Ticket.public_ref)
        .join(Category, Category.id == Report.category_id)
        .outerjoin(Ticket, Ticket.id == Report.ticket_id)
        .where(Report.id == report_id, Report.reporter_id == reporter_id)
    ).first()
    if row is None:
        raise HTTPException(404, "Report not found.")
    return _to_my_report(*row)
