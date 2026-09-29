"""Platform-admin API (the RoadWatch operator, not government): moderation and audit.

Moderation works on REPORTS, not people. An admin reviewing a fake or abusive report can
ban "whoever sent this report" without ever seeing a reporter id, phone number or any
identity: the ban is applied inside the identity service (vault + opaque id), and the
admin only sees anonymous history counts ("this sender: 14 reports, 11 rejected").

Only officials with role=platform_admin can call these endpoints.
"""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.api.deps import current_official
from app.db import get_core_db
from app.identity.service import set_reporter_ban
from app.models.core import (
    AuditLog,
    Category,
    Official,
    OfficialRole,
    Report,
    Reporter,
    ReportStatus,
    RoadSegment,
    Ticket,
    TicketEvent,
)
from app.security.vault_crypto import keyed_hash
from app.tickets.clustering import recount_ticket

router = APIRouter(prefix="/api/v1/admin", tags=["platform admin"])


def current_platform_admin(official: Official = Depends(current_official)) -> Official:
    if official.role != OfficialRole.PLATFORM_ADMIN.value:
        raise HTTPException(403, "Platform administrators only.")
    return official


class SenderHistory(BaseModel):
    """Anonymous track record of whoever sent a report — never who they are."""

    reports: int
    verified: int
    rejected: int
    banned: bool


class ModerationRow(BaseModel):
    report_id: uuid.UUID
    ticket_ref: str | None
    category: str
    status: str
    verification_score: float | None
    rejection_reason: str | None
    received_on: date
    sender: SenderHistory


def _sender_history(db: Session, reporter_ids: set[str]) -> dict[str, SenderHistory]:
    if not reporter_ids:
        return {}
    rows = db.execute(
        select(Report.reporter_id, func.count(),
               func.count().filter(Report.status == ReportStatus.VERIFIED.value),
               func.count().filter(Report.status == ReportStatus.REJECTED.value))
        .where(Report.reporter_id.in_(reporter_ids)).group_by(Report.reporter_id)
    ).all()
    banned = dict(db.execute(select(Reporter.reporter_id, Reporter.banned)
                             .where(Reporter.reporter_id.in_(reporter_ids))).all())
    return {rid: SenderHistory(reports=n, verified=v, rejected=r, banned=bool(banned.get(rid)))
            for rid, n, v, r in rows}


@router.get("/reports", response_model=list[ModerationRow])
def moderation_queue(
    status: ReportStatus | None = None,
    limit: int = Query(100, ge=1, le=500),
    admin: Official = Depends(current_platform_admin),
    db: Session = Depends(get_core_db),
) -> list[ModerationRow]:
    """Recent reports with their verification outcome and the sender's anonymous history."""
    query = (select(Report, Category.code, Ticket.public_ref)
             .join(Category, Category.id == Report.category_id)
             .outerjoin(Ticket, Ticket.id == Report.ticket_id)
             .order_by(Report.received_at.desc()).limit(limit))
    if status:
        query = query.where(Report.status == status.value)
    rows = db.execute(query).all()
    history = _sender_history(db, {r.reporter_id for r, _, _ in rows})
    return [ModerationRow(
        report_id=r.id, ticket_ref=ref, category=code, status=r.status,
        verification_score=r.verification_score, rejection_reason=r.rejection_reason,
        received_on=r.received_at.date(), sender=history[r.reporter_id],
    ) for r, code, ref in rows]


class BanIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    withdraw_reports: bool = Field(True, description="Also withdraw this sender's reports from tickets")


class BanOut(BaseModel):
    banned: bool
    reports_withdrawn: int
    tickets_recounted: list[str]


def _reporter_of(db: Session, report_id: uuid.UUID) -> str:
    reporter_id = db.scalar(select(Report.reporter_id).where(Report.id == report_id))
    if reporter_id is None:
        raise HTTPException(404, "Report not found.")
    return reporter_id


@router.post("/reports/{report_id}/ban-sender", response_model=BanOut)
def ban_sender(report_id: uuid.UUID, body: BanIn,
               admin: Official = Depends(current_platform_admin),
               db: Session = Depends(get_core_db)) -> BanOut:
    """Ban whoever sent this report. Blocks their account and re-registration with the
    same phone number; optionally withdraws all their reports and recounts the tickets."""
    reporter_id = _reporter_of(db, report_id)
    set_reporter_ban(reporter_id, True)

    withdrawn, recounted = 0, []
    if body.withdraw_reports:
        reports = list(db.scalars(select(Report).where(
            Report.reporter_id == reporter_id, Report.status != ReportStatus.REJECTED.value
        ).with_for_update()))
        ticket_ids = {r.ticket_id for r in reports if r.ticket_id}
        for r in reports:
            r.status = ReportStatus.REJECTED.value
            r.rejection_reason = "Withdrawn: sender banned for abuse."
            r.verification_details = {**(r.verification_details or {}),
                                      "rejection": {"code": "withdrawn", "params": {}}}
        withdrawn = len(reports)
        db.flush()
        for ticket in db.scalars(select(Ticket).where(Ticket.id.in_(ticket_ids)).with_for_update()):
            road_class = (db.scalar(select(RoadSegment.road_class).where(RoadSegment.id == ticket.road_segment_id))
                          if ticket.road_segment_id else None)
            recount_ticket(db, ticket, road_class)
            db.add(TicketEvent(ticket_id=ticket.id, type="reports_withdrawn", actor_type="system",
                               payload={"unique_reporters": ticket.unique_reporters,
                                        "report_count": ticket.report_count}))
            recounted.append(ticket.public_ref)
    db.commit()
    audit.record("reporter_banned", actor_type="platform", actor_id=str(admin.id),
                 target=f"report:{report_id}",
                 details={"reason": body.reason, "reports_withdrawn": withdrawn, "tickets": recounted})
    return BanOut(banned=True, reports_withdrawn=withdrawn, tickets_recounted=sorted(recounted))


class UnbanIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


@router.post("/reports/{report_id}/unban-sender", response_model=BanOut)
def unban_sender(report_id: uuid.UUID, body: UnbanIn,
                 admin: Official = Depends(current_platform_admin),
                 db: Session = Depends(get_core_db)) -> BanOut:
    """Lift a ban (withdrawn reports stay withdrawn; the person can report again)."""
    set_reporter_ban(_reporter_of(db, report_id), False)
    audit.record("reporter_unbanned", actor_type="platform", actor_id=str(admin.id),
                 target=f"report:{report_id}", details={"reason": body.reason})
    return BanOut(banned=False, reports_withdrawn=0, tickets_recounted=[])


class AuditRow(BaseModel):
    id: int
    created_at: datetime
    actor_type: str
    actor_id: str | None
    action: str
    target: str | None
    success: bool
    details: dict


@router.get("/audit", response_model=list[AuditRow])
def audit_log(
    action: str | None = None,
    success: bool | None = None,
    limit: int = Query(200, ge=1, le=1000),
    admin: Official = Depends(current_platform_admin),
    db: Session = Depends(get_core_db),
) -> list[AuditRow]:
    """Security events, newest first. Citizen entries show a pseudonym, never the reporter id."""
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        query = query.where(AuditLog.action == action)
    if success is not None:
        query = query.where(AuditLog.success == success)
    return [AuditRow(id=a.id, created_at=a.created_at, actor_type=a.actor_type,
                     actor_id=_mask(a), action=a.action, target=a.target, success=a.success,
                     details=a.details)
            for a in db.scalars(query)]


def _mask(entry: AuditLog) -> str | None:
    """Citizen ids are replaced by a stable pseudonym: an admin can tell 'same sender'
    across events without ever holding the real reporter id."""
    if entry.actor_type == "citizen" and entry.actor_id:
        return "citizen-" + keyed_hash(entry.actor_id, "admin-view")[:12]
    return entry.actor_id
