"""SLA engine: the scheduled job that keeps deadlines honest.

Runs every SLA_SWEEP_INTERVAL_S seconds (Celery beat, see app/worker.py). Each run:
1. Warns the responsible officials when 80% of a ticket's SLA time has passed.
2. Escalates tickets past their deadline one level up the jurisdiction path
   (ward → municipality → district → state), restarts the clock at the new level,
   records the breach publicly and alerts the new level.
3. Closes the confirmation window of fix_submitted tickets (resolve or reopen).
4. Refreshes priority, which grows with ticket age.

Each ticket is processed in its own transaction with FOR UPDATE SKIP LOCKED, so two
scheduler runs (or a scheduler and an official editing a ticket) never collide.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import core_session
from app.models.core import RoadSegment, Ticket, TicketStatus
from app.notifications.service import notify_officials, officials_for_node
from app.tickets.lifecycle import SLA_ACTIVE, escalate
from app.tickets.priority import compute_priority
from app.tickets.resolution import evaluate_resolution, tenant_config

log = logging.getLogger(__name__)
DEFAULT_WARNING_RATIO = 0.8


@dataclass
class SweepResult:
    warned: list[str] = field(default_factory=list)
    escalated: list[str] = field(default_factory=list)
    decided: list[str] = field(default_factory=list)


def _ids(where) -> list:
    with core_session() as db:
        return list(db.scalars(select(Ticket.id).where(where)))


def run_sla_sweep(now: datetime | None = None) -> SweepResult:
    now = now or datetime.now(UTC)
    result = SweepResult()

    # 1 + 2 + 4: tickets whose SLA clock is running.
    for ticket_id in _ids(Ticket.status.in_(SLA_ACTIVE)):
        with core_session() as db:
            ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id)
                               .with_for_update(skip_locked=True))
            if ticket is None or ticket.status not in SLA_ACTIVE or ticket.sla_due_at is None:
                continue
            road_class = (db.scalar(select(RoadSegment.road_class)
                                    .where(RoadSegment.id == ticket.road_segment_id))
                          if ticket.road_segment_id else None)
            ticket.priority = compute_priority(ticket.severity, ticket.unique_reporters, road_class,
                                               (now - ticket.created_at).total_seconds() / 86400,
                                               ticket.seen_count)

            if ticket.sla_due_at <= now:
                overdue_h = (now - ticket.sla_due_at).total_seconds() / 3600
                escalate(db, ticket, f"SLA breached ({overdue_h:.0f} h overdue)", now)
                result.escalated.append(ticket.public_ref)
            elif ticket.sla_warned_at is None and ticket.sla_started_at is not None:
                ratio = float(tenant_config(db, ticket).get("sla_warning_ratio", DEFAULT_WARNING_RATIO))
                total = (ticket.sla_due_at - ticket.sla_started_at).total_seconds()
                if total > 0 and (now - ticket.sla_started_at).total_seconds() >= ratio * total:
                    ticket.sla_warned_at = now
                    hours_left = (ticket.sla_due_at - now).total_seconds() / 3600
                    notify_officials(
                        db, officials_for_node(db, ticket.escalated_node_id, ticket.authority_id),
                        ticket, "sla_warning", f"Deadline approaching: {ticket.public_ref}",
                        f"About {hours_left:.0f} h left before {ticket.public_ref} is escalated.",
                    )
                    result.warned.append(ticket.public_ref)
            db.commit()

    # 3: confirmation windows.
    for ticket_id in _ids(Ticket.status == TicketStatus.FIX_SUBMITTED.value):
        with core_session() as db:
            ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id)
                               .with_for_update(skip_locked=True))
            if ticket is None:
                continue
            before = ticket.status
            evaluate_resolution(db, ticket, now)
            if ticket.status != before:
                result.decided.append(ticket.public_ref)
            db.commit()

    if result.escalated or result.warned or result.decided:
        log.info("SLA sweep: warned=%d escalated=%d decided=%d",
                 len(result.warned), len(result.escalated), len(result.decided))
    return result
