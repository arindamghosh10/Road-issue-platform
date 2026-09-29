"""Generate DEMO tickets so the dashboards have something to show (dev only).

    python -m app.seed.demo --tickets 80

Citizens are created through the real OTP stub, reports go through the real
verification pipeline (sanitize → checks → clustering), and then each ticket is
"time-travelled" into the past 12 weeks with a plausible history: some fixed on time,
some fixed late (with a recorded SLA breach), some still open or in progress. Some
areas are deliberately made to perform better than others so leaderboards differ.

Everything created is fake: synthetic photos, fake phone numbers (90000xxxxx),
sample boundaries. Refuses to run with APP_ENV=prod.
"""

import argparse
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from app.config import get_settings
from app.db import core_session
from app.identity.providers import get_otp_sender
from app.identity.service import request_otp, verify_otp
from app.models.core import Category, Jurisdiction, Ticket, TicketEvent, TicketStatus
from app.reports.service import NewReport, create_report, process_report
from app.seed.photos import road_photo
from app.tickets.clustering import sla_hours

CATEGORY_WEIGHTS = {
    "pothole": 40, "waterlogging": 14, "broken_divider": 8, "missing_signage": 8,
    "broken_railing": 7, "bridge_leak": 6, "bridge_crack": 4, "road_cave_in": 4, "other": 5,
}
# Sample road vertices, so some tickets land on NHAI / PWD roads.
ROAD_POINTS = [(22.625, 88.395), (22.66, 88.42), (22.558, 88.312), (22.52, 88.40), (22.56, 88.405)]


def _citizen(i: int) -> str:
    phone = f"90000{i:05d}"
    challenge = request_otp(phone)
    return verify_otp(challenge, get_otp_sender().last_code["+91" + phone])


def _pick_point(rng: random.Random, wards: list[Jurisdiction], hot: set[int]) -> tuple[float, float]:
    if rng.random() < 0.12:
        lat, lon = rng.choice(ROAD_POINTS)
        return lat + rng.uniform(-0.0001, 0.0001), lon + rng.uniform(-0.0001, 0.0001)
    pool = [w for w in wards if w.id in hot] if rng.random() < 0.5 else wards
    ward = rng.choice(pool)
    row = None
    with core_session() as db:
        row = db.execute(text("SELECT ST_X(c), ST_Y(c) FROM (SELECT ST_PointOnSurface(geom) c "
                              "FROM jurisdictions WHERE id = :id) s"), {"id": ward.id}).one()
    return row[1] + rng.uniform(-0.003, 0.003), row[0] + rng.uniform(-0.003, 0.003)


def _submit(reporter_id: str, category: str, lat: float, lon: float, seed: int) -> str | None:
    with core_session() as db:
        report = create_report(db, NewReport(
            reporter_id=reporter_id, category_code=category, lat=lat, lon=lon, gps_accuracy_m=8.0,
            captured_at=datetime.now(UTC) - timedelta(minutes=5), capture_source="in_app_camera",
            attestation_token=None, description="Demo report", photo=road_photo(seed),
            photo_content_type="image/jpeg",
        ))
        report_id = report.id
    process_report(report_id)
    with core_session() as db:
        return db.scalar(text("SELECT t.public_ref FROM reports r JOIN tickets t ON t.id = r.ticket_id "
                              "WHERE r.id = :id"), {"id": report_id})


def _time_travel(rng: random.Random, ref: str, performance: float, now: datetime) -> str:
    """Move a ticket's history into the past and give it a plausible outcome."""
    with core_session() as db:
        t = db.scalar(select(Ticket).where(Ticket.public_ref == ref))
        category = db.get(Category, t.category_id)
        hours = sla_hours(db, t.jurisdiction_path, category, t.severity)
        created = now - timedelta(days=rng.uniform(0, 84), hours=rng.uniform(0, 23))
        t.created_at = t.sla_started_at = created
        t.sla_due_at = created + timedelta(hours=hours)
        db.execute(text("UPDATE ticket_events SET created_at = :c WHERE ticket_id = :id"),
                   {"c": created, "id": t.id})

        # Better-performing areas fix more tickets, and faster.
        took = timedelta(hours=hours * rng.uniform(0.3, 1.0 / max(performance, 0.2)))
        fixed_at = created + took
        outcome = "open"
        if fixed_at < now and rng.random() < performance + 0.15:
            late = fixed_at > t.sla_due_at
            if late:
                t.sla_breached = True
                t.escalation_level = 1
                t.escalated_node_id = t.jurisdiction_path[-2] if len(t.jurisdiction_path) > 1 else None
                node = db.get(Jurisdiction, t.escalated_node_id) if t.escalated_node_id else None
                db.add(TicketEvent(ticket_id=t.id, type="escalated", actor_type="system",
                                   created_at=t.sla_due_at,
                                   payload={"public": True, "reason": "SLA breached (demo history)",
                                            "to_node": node.name if node else None, "escalation_level": 1}))
            t.status = TicketStatus.RESOLVED.value
            t.resolved_at = fixed_at
            db.add(TicketEvent(ticket_id=t.id, type="resolved", actor_type="system", created_at=fixed_at,
                               payload={"public": True, "reason": "demo history: reporters confirmed the fix"}))
            outcome = "resolved late" if late else "resolved"
        else:
            t.status = rng.choice([TicketStatus.OPEN, TicketStatus.ACKNOWLEDGED, TicketStatus.IN_PROGRESS]).value
            outcome = t.status
        db.commit()
        return outcome


def run(n_tickets: int, seed: int) -> None:
    if get_settings().app_env == "prod":
        sys.exit("Refusing to generate demo data with APP_ENV=prod.")
    rng = random.Random(seed)
    now = datetime.now(UTC)
    with core_session() as db:
        wards = list(db.scalars(select(Jurisdiction).where(Jurisdiction.level == "ward")))
        if not wards:
            sys.exit("Run `python -m app.seed` first.")
        offset = db.scalar(text("SELECT count(*) FROM reporters")) or 0
    hot = {w.id for w in rng.sample(wards, k=min(12, len(wards)))}
    # Each ward gets a hidden "performance" so the leaderboard has winners and laggards.
    performance = {w.id: rng.uniform(0.25, 0.95) for w in wards}

    citizens = [_citizen(offset + i) for i in range(max(20, n_tickets // 2))]
    photo_seed = uuid.uuid4().int % 10_000_000
    outcomes: dict[str, int] = {}
    made = 0
    for _ in range(n_tickets):
        category = rng.choices(list(CATEGORY_WEIGHTS), weights=list(CATEGORY_WEIGHTS.values()))[0]
        lat, lon = _pick_point(rng, wards, hot)
        photo_seed += 1
        ref = _submit(rng.choice(citizens), category, lat, lon, photo_seed)
        if ref is None:
            continue
        for extra in range(rng.choices([0, 1, 2, 4], weights=[55, 25, 12, 8])[0]):
            photo_seed += 1
            _submit(rng.choice(citizens), category, lat + (extra + 1) * 0.00004, lon, photo_seed)
        with core_session() as db:
            path = db.scalar(select(Ticket.jurisdiction_path).where(Ticket.public_ref == ref))
        perf = performance.get(path[-1], 0.6) if path else 0.6
        outcome = _time_travel(rng, ref, perf, now)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        made += 1
    print(f"Created {made} DEMO tickets over the last 12 weeks: {outcomes}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo tickets (dev only).")
    parser.add_argument("--tickets", type=int, default=80)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    run(args.tickets, args.seed)


if __name__ == "__main__":
    main()
