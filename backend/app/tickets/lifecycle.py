"""Ticket lifecycle: status changes, audit events, escalation.

    open ──▶ acknowledged ──▶ in_progress ──▶ fix_submitted ──▶ resolved
      └──────────────────────────▲    ▲              │
                                 │    │              ▼ (reporters dispute the fix)
                              reopened ◀─────────────┘

Officials may move tickets forward by hand only as far as in_progress. fix_submitted
happens only through an accepted fix proof, and resolved only through the close rule
(app/tickets/resolution.py) — nobody can mark a ticket "resolved" by clicking a button.

Every change writes a TicketEvent (the audit trail). Events flagged public=True appear
on the public ticket timeline.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import (
    ActorType,
    Category,
    Jurisdiction,
    Official,
    Ticket,
    TicketEvent,
    TicketStatus,
)
from app.notifications.service import notify_officials, officials_for_node
from app.tickets.clustering import sla_hours

S = TicketStatus

# Transitions an official may make by hand.
MANUAL_TRANSITIONS: dict[str, set[str]] = {
    S.OPEN: {S.ACKNOWLEDGED, S.IN_PROGRESS},
    S.ACKNOWLEDGED: {S.IN_PROGRESS},
    S.REOPENED: {S.ACKNOWLEDGED, S.IN_PROGRESS},
    S.IN_PROGRESS: set(),
    S.FIX_SUBMITTED: set(),
    S.RESOLVED: set(),
}
# Statuses whose SLA clock is running (paused while reporters check a submitted fix).
SLA_ACTIVE = (S.OPEN.value, S.ACKNOWLEDGED.value, S.IN_PROGRESS.value, S.REOPENED.value)


class TransitionError(Exception):
    pass


def add_event(
    db: Session,
    ticket: Ticket,
    type_: str,
    *,
    official: Official | None = None,
    public: bool = False,
    **payload,
) -> TicketEvent:
    event = TicketEvent(
        ticket_id=ticket.id,
        type=type_,
        actor_type=ActorType.OFFICIAL.value if official else ActorType.SYSTEM.value,
        actor_id=str(official.id) if official else None,
        payload={**payload, "public": public},
    )
    db.add(event)
    return event


def change_status(db: Session, ticket: Ticket, new_status: str, official: Official,
                  note: str | None = None) -> None:
    allowed = MANUAL_TRANSITIONS.get(ticket.status, set())
    if new_status not in allowed:
        raise TransitionError(
            f"Cannot move a ticket from {ticket.status} to {new_status} by hand."
            + (" Submit a fix proof instead." if new_status in (S.FIX_SUBMITTED, S.RESOLVED) else "")
        )
    old = ticket.status
    ticket.status = new_status
    add_event(db, ticket, "status_changed", official=official, public=True,
              from_status=old, to_status=new_status, note=(note or "")[:1000] or None)


def current_node_index(ticket: Ticket) -> int:
    """Index in jurisdiction_path of the node currently answerable for the ticket."""
    path = ticket.jurisdiction_path
    if ticket.escalated_node_id in path:
        return path.index(ticket.escalated_node_id)
    return len(path) - 1


def restart_sla(db: Session, ticket: Ticket, now: datetime) -> None:
    category = db.get(Category, ticket.category_id)
    hours = sla_hours(db, ticket.jurisdiction_path, category, ticket.severity)
    ticket.sla_started_at = now
    ticket.sla_due_at = now + timedelta(hours=hours)
    ticket.sla_warned_at = None


def escalate(db: Session, ticket: Ticket, reason: str, now: datetime | None = None) -> int | None:
    """Move responsibility one level up the jurisdiction path, restart the SLA clock at
    the new level, record it publicly and alert the new level's officials.
    Returns the new node id (unchanged if already at the top)."""
    now = now or datetime.now(UTC)
    path = ticket.jurisdiction_path
    if not path:
        return None
    idx = current_node_index(ticket)
    new_idx = max(0, idx - 1)
    ticket.escalated_node_id = path[new_idx]
    ticket.escalation_level += 1
    restart_sla(db, ticket, now)

    node = db.get(Jurisdiction, ticket.escalated_node_id)
    add_event(db, ticket, "escalated", public=True, reason=reason,
              escalation_level=ticket.escalation_level,
              to_node=node.name, to_level=node.level, at_top=(idx == 0))
    notify_officials(
        db, officials_for_node(db, ticket.escalated_node_id), ticket, "escalated",
        f"Escalated to you: {ticket.public_ref}",
        f"Ticket {ticket.public_ref} was escalated to {node.name} ({reason}). "
        f"New deadline: {ticket.sla_due_at:%d %b %Y %H:%M} UTC.",
    )
    return ticket.escalated_node_id


def assignable_officials(db: Session, ticket: Ticket) -> list[Official]:
    """Active officials whose own scope covers this ticket."""
    from app.gov.access import ticket_scope

    candidates = db.scalars(select(Official).where(Official.is_active))
    return [o for o in candidates
            if db.scalar(select(Ticket.id).where(Ticket.id == ticket.id, ticket_scope(db, o)))]
