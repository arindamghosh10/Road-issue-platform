"""Notifications: in-app inbox + email (officials) + push (citizens).

Every notification is first written to the `notifications` table (the in-app inbox),
then copied to other channels:
* officials — email (Mailpit locally, Brevo free tier when hosted)
* citizens  — a generic "you have an update" push to their phone (see
              app/identity/push.py: tokens live in the vault, never here). Citizens are
              never emailed: we don't have, and don't want, their email address.

Channel failures are logged, never raised: a mail server outage must not stop a ticket
from being escalated. Callers add rows to the current DB session and commit with the
rest of their change, so a notification exists only if the change it announces does.
Pushes wait for that commit too: they are sent after it, and dropped on rollback.
"""

import logging
import smtplib
from email.message import EmailMessage
from functools import lru_cache
from typing import Protocol

from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.core import (
    Notification,
    Official,
    RecipientType,
    Report,
    ReportStatus,
    Ticket,
)

log = logging.getLogger(__name__)


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpEmailSender:
    def send(self, to: str, subject: str, body: str) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = s.email_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            smtp.send_message(msg)


class LogEmailSender:
    """Records emails instead of sending them (tests, or no mail server)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))
        log.info("[EMAIL STUB] to=%s subject=%s", to, subject)


@lru_cache
def get_email_sender() -> EmailSender:
    return SmtpEmailSender() if get_settings().email_backend == "smtp" else LogEmailSender()


def _deliver_email(official: Official, title: str, body: str) -> None:
    try:
        get_email_sender().send(official.email, f"[RoadWatch] {title}", body)
    except (OSError, smtplib.SMTPException) as exc:
        log.warning("email to official %s failed: %s", official.id, exc)


def notify_officials(
    db: Session, officials: list[Official], ticket: Ticket | None, kind: str, title: str, body: str
) -> int:
    for official in officials:
        db.add(Notification(
            recipient_type=RecipientType.OFFICIAL.value, recipient_id=str(official.id),
            ticket_id=ticket.id if ticket else None, kind=kind, title=title, body=body,
        ))
        _deliver_email(official, title, body)
    return len(officials)


def officials_for_node(db: Session, node_id: int | None, authority_id: int | None = None) -> list[Official]:
    """Active officials attached to this node, plus (optionally) the road authority's officials."""
    conditions = []
    if node_id is not None:
        conditions.append(Official.node_id == node_id)
    if authority_id is not None:
        conditions.append(Official.authority_id == authority_id)
    if not conditions:
        return []
    return list(db.scalars(select(Official).where(Official.is_active, or_(*conditions))))


# --- Citizen push: queued on the session, sent after commit ---------------------------------

_PUSH_KEY = "roadwatch_push_reporters"


def enqueue_push(reporter_ids: list[str]) -> None:
    """Hand reporters to the worker for a push. Never raises: a broker outage must not
    turn an already-committed change into an error."""
    try:
        if get_settings().tasks_eager:
            from app.identity.push import deliver

            deliver(reporter_ids)
        else:
            from app.worker import push_task

            push_task.delay(reporter_ids)
    except Exception as exc:  # noqa: BLE001 — push must never break the workflow
        log.warning("push dispatch failed: %s", type(exc).__name__)


@event.listens_for(Session, "after_commit")
def _send_pushes_after_commit(session: Session) -> None:
    reporter_ids = session.info.pop(_PUSH_KEY, None)
    if reporter_ids:
        enqueue_push(sorted(reporter_ids))


@event.listens_for(Session, "after_rollback")
def _drop_pushes_on_rollback(session: Session) -> None:
    session.info.pop(_PUSH_KEY, None)


def notify_reporter(
    db: Session, reporter_id: str, ticket: Ticket | None, kind: str, title: str, body: str,
    params: dict | None = None,
) -> None:
    """`title`/`body` are English; the app shows its own translation keyed on `kind`
    (plus `params` and the ticket ref), falling back to this text for unknown kinds."""
    db.add(Notification(
        recipient_type=RecipientType.REPORTER.value, recipient_id=reporter_id,
        ticket_id=ticket.id if ticket else None, kind=kind, title=title, body=body,
        params=params or {},
    ))
    db.info.setdefault(_PUSH_KEY, set()).add(reporter_id)


def ticket_reporter_ids(db: Session, ticket: Ticket) -> list[str]:
    """Distinct reporters with a verified report on this ticket (internal use only)."""
    return list(db.scalars(
        select(Report.reporter_id).distinct().where(
            Report.ticket_id == ticket.id, Report.status == ReportStatus.VERIFIED.value
        )
    ))


def notify_ticket_reporters(db: Session, ticket: Ticket, kind: str, title: str, body: str) -> int:
    reporter_ids = ticket_reporter_ids(db, ticket)
    for reporter_id in reporter_ids:
        notify_reporter(db, reporter_id, ticket, kind, title, body)
    return len(reporter_ids)
