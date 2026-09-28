"""Clustering: merge verified reports of the same issue into one ticket.

A verified report joins an existing unresolved ticket when:
* same category, AND
* within the category's radius (30 m for potholes, 150 m for bridge issues…), OR — for
  bridge categories — on the same mapped bridge segment regardless of distance.
Otherwise a new ticket is opened.

Concurrency: two reports of the same pothole can arrive at the same moment. A Postgres
advisory lock per category serialises the "find or create" step, so they cannot both
create a ticket.
"""

import math
import secrets
from datetime import UTC, datetime, timedelta

import h3
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.core import (
    ActorType,
    Category,
    Report,
    ReportStatus,
    SlaRule,
    Tenant,
    Ticket,
    TicketEvent,
    TicketStatus,
)
from app.tickets.priority import compute_priority
from app.tickets.routing import Placement, point_sql

H3_RESOLUTION = 9  # ~0.1 km² hexagons: used for fast area aggregation on dashboards
BRIDGE_CATEGORIES = {"bridge_leak", "bridge_crack", "broken_railing"}
CLOSED_STATUSES = (TicketStatus.RESOLVED.value,)
REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion


def new_public_ref() -> str:
    return "RW-" + "".join(secrets.choice(REF_ALPHABET) for _ in range(8))


def sla_hours(db: Session, path: list[int], category: Category, severity: int) -> int:
    """Tenant-specific SLA if a tenant covers this area, else the category default."""
    hours = db.scalar(
        select(SlaRule.hours)
        .join(Tenant, Tenant.id == SlaRule.tenant_id)
        .where(
            Tenant.root_node_id.in_(path),
            SlaRule.category_id == category.id,
            SlaRule.severity == severity,
        )
        .limit(1)
    )
    return hours or int(category.default_sla_hours[str(severity)])


def _find_open_ticket(
    db: Session, category: Category, lon: float, lat: float, placement: Placement
) -> Ticket | None:
    same_bridge = placement.is_bridge and category.code in BRIDGE_CATEGORIES
    ticket_id = db.scalar(
        text(f"""
            SELECT id FROM tickets
            WHERE category_id = :category_id
              AND status <> ALL(:closed)
              AND (
                ST_DWithin(location::geography, {point_sql()}::geography, :radius)
                OR (:same_bridge AND road_segment_id = :segment_id)
              )
            ORDER BY ST_Distance(location::geography, {point_sql()}::geography)
            LIMIT 1
            FOR UPDATE
        """),
        {
            "category_id": category.id,
            "closed": list(CLOSED_STATUSES),
            "lon": lon,
            "lat": lat,
            "radius": category.cluster_radius_m,
            "same_bridge": same_bridge,
            "segment_id": placement.road_segment_id,
        },
    )
    return db.get(Ticket, ticket_id) if ticket_id else None


def attach_to_ticket(
    db: Session,
    report: Report,
    category: Category,
    lon: float,
    lat: float,
    severity: int,
    placement: Placement,
) -> tuple[Ticket, bool]:
    """Attach a verified report to a ticket. Returns (ticket, created_new).

    The report must already have status=verified. The caller commits.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": 7_000_000 + category.id})
    now = datetime.now(UTC)

    ticket = _find_open_ticket(db, category, lon, lat, placement)
    created = ticket is None
    if created:
        ticket = Ticket(
            public_ref=new_public_ref(),
            category_id=category.id,
            location=from_shape(Point(lon, lat), srid=4326),
            h3_cell=h3.latlng_to_cell(lat, lon, H3_RESOLUTION),
            severity=severity,
            status=TicketStatus.OPEN.value,
            jurisdiction_path=placement.jurisdiction_path,
            authority_id=placement.authority_id,
            road_segment_id=placement.road_segment_id,
            owner_node_id=placement.owner_node_id,
            sla_due_at=now + timedelta(hours=sla_hours(db, placement.jurisdiction_path, category, severity)),
        )
        db.add(ticket)
        db.flush()
        db.add(TicketEvent(
            ticket_id=ticket.id, type="ticket_created", actor_type=ActorType.SYSTEM.value,
            payload={"category": category.code, "severity": severity},
        ))

    report.ticket_id = ticket.id
    db.flush()

    # Recount from the reports themselves so the numbers can never drift.
    counts = db.execute(
        select(func.count(), func.count(func.distinct(Report.reporter_id))).where(
            Report.ticket_id == ticket.id,
            Report.status == ReportStatus.VERIFIED.value,
        )
    ).one()
    ticket.report_count, ticket.unique_reporters = int(counts[0]), int(counts[1])
    ticket.severity = max(ticket.severity, severity)
    age_days = 0.0 if created else (now - ticket.created_at).total_seconds() / 86400
    ticket.priority = compute_priority(
        ticket.severity, ticket.unique_reporters, placement.road_class, age_days
    )
    db.add(TicketEvent(
        ticket_id=ticket.id, type="report_attached",
        # actor_id is the opaque reporter id: kept for the internal audit trail only and
        # stripped from every gov/public API response.
        actor_type=ActorType.CITIZEN.value, actor_id=report.reporter_id,
        payload={"report_count": ticket.report_count, "unique_reporters": ticket.unique_reporters},
    ))
    return ticket, created


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Haversine distance, handy in tests and sanity checks."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
