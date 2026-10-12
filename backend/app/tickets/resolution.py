"""Closing a ticket: fix proof → vision check → reporters confirm → resolved (or reopened).

1. An official uploads an "after" photo taken with the in-app camera at the site.
   Refused if taken more than FIX_PROOF_MAX_DISTANCE_M (default 50 m) away or more than
   24 h ago, or if the vision model says the damage is still there.
2. Accepted → status fix_submitted; the platform (never the government) asks every
   original reporter "Is this fixed? Yes / No / Partly".
3. The close rule (configurable per tenant, defaults from the brief):
   * resolve once "yes" answers reach ≥ 50% of ALL reporters (can no longer be outvoted);
   * reopen + escalate once "no"/"partly" answers exceed 50% of all reporters;
   * after 7 days, decide on the answers received: ≥ 50% of responders said yes →
     resolved; otherwise reopened + escalated. No answers at all → resolved ("no
     disputes within 7 days"), but only if the vision check actually passed. If the
     vision model was unavailable, silence is not enough: at least one "yes" is needed.
The government only ever sees the counts ("7 of 9 confirmed fixed"), never who answered.
"""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.imaging.sanitize import InvalidImage, sanitize
from app.models.core import (
    Category,
    FixConfirmation,
    FixProof,
    FixResponse,
    Official,
    Report,
    ReportStatus,
    Tenant,
    Ticket,
    TicketStatus,
)
from app.notifications.service import (
    notify_officials,
    notify_ticket_reporters,
    officials_for_node,
    ticket_reporter_ids,
)
from app.storage import get_store
from app.tickets.lifecycle import add_event, escalate
from app.tickets.routing import point_sql
from app.vision import get_vision_verifier
from app.vision.base import FixAssessment

FIXABLE = (TicketStatus.OPEN.value, TicketStatus.ACKNOWLEDGED.value,
           TicketStatus.IN_PROGRESS.value, TicketStatus.REOPENED.value)


class FixProofError(Exception):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def tenant_config(db: Session, ticket: Ticket) -> dict:
    config = db.scalar(select(Tenant.config).where(Tenant.root_node_id.in_(ticket.jurisdiction_path)))
    return config or {}


def _close_rule(db: Session, ticket: Ticket) -> tuple[float, int]:
    s = get_settings()
    rule = tenant_config(db, ticket).get("close_rule", {})
    return (float(rule.get("min_confirm_ratio", s.min_confirm_ratio)),
            int(rule.get("no_dispute_days", s.confirmation_window_days)))


# --- 1. Fix proof ---------------------------------------------------------------------


def submit_fix_proof(
    db: Session,
    ticket: Ticket,
    official: Official,
    photo: bytes,
    lat: float,
    lon: float,
    captured_at: datetime,
    capture_source: str,
) -> FixProof:
    """Validate and record a fix proof. Raises FixProofError when refused (the refused
    proof is still stored, for the audit trail)."""
    s = get_settings()
    now = datetime.now(UTC)
    if ticket.status not in FIXABLE:
        raise FixProofError(f"Ticket is {ticket.status}; a fix proof is not expected now.", 409)
    if capture_source != "in_app_camera":
        raise FixProofError("Fix proof must be taken with the in-app camera.")
    try:
        clean = sanitize(photo)
    except InvalidImage:
        raise FixProofError("The photo could not be read.") from None

    proof_id = uuid.uuid4()
    key = f"fixes/{ticket.id}/{proof_id}.jpg"
    get_store().put(s.s3_bucket_public, key, clean.jpeg, "image/jpeg")
    proof = FixProof(
        id=proof_id, ticket_id=ticket.id, official_id=official.id, photo_keys=[key],
        location=from_shape(Point(lon, lat), srid=4326), captured_at=captured_at,
    )
    db.add(proof)

    max_m = float(tenant_config(db, ticket).get("fix_proof_max_distance_m", s.fix_proof_max_distance_m))
    distance = db.scalar(
        text(f"SELECT ST_Distance(location::geography, {point_sql()}::geography) FROM tickets WHERE id = :id"),
        {"lon": lon, "lat": lat, "id": ticket.id},
    )
    reason = None
    if distance > max_m:
        reason = f"Photo was taken {distance:.0f} m from the reported spot (limit {max_m:.0f} m)."
    elif captured_at > now + timedelta(minutes=5) or now - captured_at > timedelta(hours=s.fix_proof_max_age_hours):
        reason = f"Photo must be taken within the last {s.fix_proof_max_age_hours} hours."

    vision = None
    if reason is None:
        before = db.scalar(
            select(Report.photo_public_key).where(
                Report.ticket_id == ticket.id, Report.status == ReportStatus.VERIFIED.value,
                Report.photo_public_key.is_not(None),
            ).order_by(Report.received_at).limit(1)
        )
        category = db.get(Category, ticket.category_id)
        if before is None:
            vision = FixAssessment("none", False, False, 0.0, "No before-photo to compare.",
                                   error="no before photo")
        else:
            before_jpeg = get_store().get(s.s3_bucket_public, before)
            vision = get_vision_verifier().assess_fix(before_jpeg, clean.jpeg, category.code)
        proof.vision_result = vision.as_dict() | {"distance_m": round(distance, 1)}
        if vision.verdict == "failed":
            reason = f"The vision check says the damage is not fixed: {vision.reason}"

    if reason:
        proof.accepted = False
        proof.rejection_reason = reason
        add_event(db, ticket, "fix_proof_rejected", official=official, reason=reason)
        db.commit()
        raise FixProofError(reason)

    proof.accepted = True
    ticket.status = TicketStatus.FIX_SUBMITTED.value
    ticket.fix_submitted_at = now
    db.execute(text("DELETE FROM fix_confirmations WHERE ticket_id = :id"), {"id": ticket.id})
    add_event(db, ticket, "fix_submitted", official=official, public=True,
              vision=vision.verdict, photo=key)
    notify_ticket_reporters(
        db, ticket, "fix_confirmation_request", f"Is it fixed? {ticket.public_ref}",
        "The authority says the problem you reported has been repaired. "
        "Please check and answer: Yes / No / Partly.",
    )
    return proof


# --- 2. Reporter confirmations -----------------------------------------------------------


@dataclass
class ConfirmationTally:
    reporters: int
    yes: int
    no: int
    partly: int

    @property
    def responded(self) -> int:
        return self.yes + self.no + self.partly

    @property
    def disputed(self) -> int:
        return self.no + self.partly


def tally(db: Session, ticket: Ticket) -> ConfirmationTally:
    counts = dict(db.execute(
        select(FixConfirmation.response, func.count())
        .where(FixConfirmation.ticket_id == ticket.id)
        .group_by(FixConfirmation.response)
    ).all())
    return ConfirmationTally(
        reporters=len(ticket_reporter_ids(db, ticket)),
        yes=counts.get(FixResponse.YES.value, 0),
        no=counts.get(FixResponse.NO.value, 0),
        partly=counts.get(FixResponse.PARTLY.value, 0),
    )


class ConfirmationError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def record_confirmation(db: Session, ticket: Ticket, reporter_id: str, response: str) -> str:
    """Store a reporter's answer (they may change it until the ticket is decided).
    Returns the ticket's status afterwards."""
    if ticket.status != TicketStatus.FIX_SUBMITTED.value:
        raise ConfirmationError("This ticket is not waiting for confirmation.", 409)
    if reporter_id not in ticket_reporter_ids(db, ticket):
        raise ConfirmationError("Only citizens who reported this issue can confirm the fix.", 403)
    if response not in {r.value for r in FixResponse}:
        raise ConfirmationError("Answer must be yes, no or partly.", 422)
    db.execute(
        insert(FixConfirmation)
        .values(ticket_id=ticket.id, reporter_id=reporter_id, response=response)
        .on_conflict_do_update(
            index_elements=["ticket_id", "reporter_id"],
            set_={"response": response, "created_at": func.now()},
        )
    )
    evaluate_resolution(db, ticket)
    return ticket.status


# --- 3. Close rule -----------------------------------------------------------------------


def _latest_vision_verdict(db: Session, ticket: Ticket) -> str:
    result = db.scalar(
        select(FixProof.vision_result).where(FixProof.ticket_id == ticket.id, FixProof.accepted)
        .order_by(FixProof.created_at.desc()).limit(1)
    )
    return (result or {}).get("verdict", "unavailable")


def _resolve(db: Session, ticket: Ticket, t: ConfirmationTally, now: datetime, why: str) -> None:
    ticket.status = TicketStatus.RESOLVED.value
    ticket.resolved_at = now
    add_event(db, ticket, "resolved", public=True, reason=why,
              confirmed=t.yes, disputed=t.disputed, reporters=t.reporters)
    notify_ticket_reporters(db, ticket, "ticket_resolved", f"Resolved: {ticket.public_ref}",
                            "Thank you. The issue you reported is marked as resolved.")
    notify_officials(db, officials_for_node(db, ticket.escalated_node_id, ticket.authority_id),
                     ticket, "ticket_resolved", f"Resolved: {ticket.public_ref}",
                     f"{t.yes} of {t.reporters} reporters confirmed the fix.")


def _reopen(db: Session, ticket: Ticket, t: ConfirmationTally, now: datetime, why: str) -> None:
    ticket.status = TicketStatus.REOPENED.value
    ticket.fix_submitted_at = None
    add_event(db, ticket, "reopened", public=True, reason=why,
              confirmed=t.yes, disputed=t.disputed, reporters=t.reporters)
    escalate(db, ticket, "fix disputed by reporters", now, reason_code="fix_disputed")
    notify_ticket_reporters(db, ticket, "ticket_reopened", f"Reopened: {ticket.public_ref}",
                            "Reporters said the fix was not complete, so the ticket was reopened "
                            "and escalated.")


def evaluate_resolution(db: Session, ticket: Ticket, now: datetime | None = None) -> None:
    """Apply the close rule to a fix_submitted ticket. Safe to call repeatedly."""
    if ticket.status != TicketStatus.FIX_SUBMITTED.value:
        return
    now = now or datetime.now(UTC)
    min_ratio, window_days = _close_rule(db, ticket)
    t = tally(db, ticket)
    vision = _latest_vision_verdict(db, ticket)
    needed = max(1, math.ceil(t.reporters * min_ratio))

    if t.yes >= needed:
        _resolve(db, ticket, t, now, f"{t.yes} of {t.reporters} reporters confirmed the fix")
        return
    if t.disputed > t.reporters * (1 - min_ratio):
        _reopen(db, ticket, t, now, f"{t.disputed} of {t.reporters} reporters disputed the fix")
        return

    window_over = ticket.fix_submitted_at and now - ticket.fix_submitted_at >= timedelta(days=window_days)
    if not window_over:
        return
    if t.responded == 0:
        if vision == "passed":
            _resolve(db, ticket, t, now, f"no disputes within {window_days} days")
        else:
            _reopen(db, ticket, t, now, "fix could not be verified (no confirmations, "
                                        "vision check unavailable)")
    elif t.yes / t.responded >= min_ratio:
        _resolve(db, ticket, t, now, f"{t.yes} of {t.responded} responding reporters confirmed")
    else:
        _reopen(db, ticket, t, now, f"{t.disputed} of {t.responded} responding reporters disputed")
