"""Load test for clustering, routing, duplicate detection and dashboard queries.

    LOAD_CORE_DATABASE_URL=postgresql+psycopg://…/roadwatch_load \\
        python scripts/loadtest.py --tickets 100000 --out ../docs/load-test.md

Uses a SEPARATE database (it is wiped and filled with synthetic data). Steps:
1. migrate + seed the sample jurisdictions;
2. bulk-insert N tickets across Kolkata/Howrah wards, one verified report each (plus
   extra reporters on some), reporters, and SLA-breach history for ~10% of tickets;
3. time the real application functions (not re-implementations) many times and report
   median / p95 in milliseconds, plus the query plans of the hottest queries.
"""

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickets", type=int, default=100_000)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--out", default=None, help="write a Markdown report here")
    parser.add_argument("--skip-load", action="store_true", help="reuse data already in the DB")
    args = parser.parse_args()

    url = os.environ.get("LOAD_CORE_DATABASE_URL")
    if not url or "load" not in url:
        sys.exit("Set LOAD_CORE_DATABASE_URL to a dedicated database whose name contains 'load'.")
    os.environ["CORE_DATABASE_URL"] = url
    os.environ.setdefault("APP_ENV", "dev")

    from sqlalchemy import select, text, true

    from app.api import stats
    from app.api.views import build_tickets
    from app.db import core_engine, core_session
    from app.gov.access import ticket_scope
    from app.models.core import Category, Jurisdiction, JurisdictionLevel, Official, Ticket
    from app.tickets import clustering
    from app.tickets.routing import locate

    if not args.skip_load:
        load_data(args.tickets)

    import random

    rng = random.Random(1)

    def points(n):
        return [(88.30 + rng.random() * 0.11, 22.46 + rng.random() * 0.17) for _ in range(n)]

    results: list[tuple[str, list[float]]] = []

    def bench(name, fn, runs=args.runs):
        times = []
        for i in range(runs):
            t0 = time.perf_counter()
            fn(i)
            times.append((time.perf_counter() - t0) * 1000)
        results.append((name, times))
        print(f"{name:<55} median {statistics.median(times):7.1f} ms   p95 {pct(times, 95):7.1f} ms")

    with core_session() as db:
        pothole = db.scalar(select(Category).where(Category.code == "pothole"))
        kmc = db.scalar(select(Jurisdiction.id).where(Jurisdiction.lgd_code == "SAMPLE-ULB-KMC"))
        officials = {e.split("@")[0]: db.scalar(select(Official).where(Official.email == e))
                     for e in ("kmc.ward001@demo.roadwatch.in", "kmc@demo.roadwatch.in", "state@demo.roadwatch.in")}
        n_tickets = db.scalar(text("SELECT count(*) FROM tickets"))
        n_reports = db.scalar(text("SELECT count(*) FROM reports"))
    print(f"\nData: {n_tickets:,} tickets, {n_reports:,} reports\n")

    pts = points(args.runs)

    # --- Write path (per report) ------------------------------------------------------------
    def find_ticket(i):
        with core_session() as db:
            lon, lat = pts[i]
            placement = locate(db, lon, lat)
            clustering._find_open_ticket(db, pothole, lon, lat, placement)
            db.rollback()

    def routing(i):
        with core_session() as db:
            locate(db, *pts[i])

    def duplicate(i):
        with core_session() as db:
            db.execute(text("""
                SELECT id FROM reports WHERE phash IS NOT NULL
                  AND bit_count(('x' || phash)::bit(64) # ('x' || :p)::bit(64)) <= 6 LIMIT 1"""),
                {"p": f"{rng.getrandbits(64):016x}"}).first()

    bench("routing: locate ward + road authority", routing)
    bench("clustering: find open ticket within radius (locked)", find_ticket)
    bench("duplicate photo check (perceptual hash)", duplicate)

    # --- Public dashboard ----------------------------------------------------------------------
    def with_db(fn):
        def run(_):
            with core_session() as db:
                fn(db)
        return run

    everything = true()
    bench("public: summary figures", with_db(lambda db: stats.summary(db, everything)))
    bench("public: leaderboard, all wards", with_db(lambda db: stats.areas(db, everything, level=JurisdictionLevel.WARD)))
    bench("public: drill-down, wards of KMC", with_db(lambda db: stats.areas(db, everything, parent_id=kmc)))
    bench("public: authorities table", with_db(lambda db: stats.authorities(db, everything)))
    bench("public: issues by type", with_db(lambda db: stats.categories(db, everything)))
    bench("public: 12-week trend", with_db(lambda db: stats.trends(db, everything, 12)))
    bench("public: map (1,000 tickets in view, serialized)", with_db(lambda db: build_tickets(
        db, list(db.scalars(select(Ticket).order_by(Ticket.priority.desc()).limit(1000))))))

    # --- Government dashboard (scoped) ------------------------------------------------------------
    for who, official in officials.items():
        def queue(db, official=official):
            scope = ticket_scope(db, official)
            rows = db.scalars(select(Ticket).where(scope, Ticket.status != "resolved")
                              .order_by(Ticket.priority.desc()).limit(200))
            build_tickets(db, list(rows), gov=True)
        bench(f"gov: work queue top 200 ({who})", with_db(queue))
        bench(f"gov: summary ({who})", with_db(lambda db, o=official: stats.summary(db, ticket_scope(db, o))))

    # --- Query plans ---------------------------------------------------------------------------
    plans = {}
    with core_session() as db:
        ward1 = officials["kmc.ward001"]
        scope_sql = str(select(Ticket.id).where(ticket_scope(db, ward1)).compile(
            core_engine(), compile_kwargs={"literal_binds": True}))
        plans["gov scope (ward officer)"] = explain(db, scope_sql)
        lon, lat = pts[0]
        plans["clustering radius search"] = explain(db, f"""
            SELECT id FROM tickets WHERE category_id = {pothole.id} AND status <> 'resolved'
              AND ST_DWithin(location::geography, ST_SetSRID(ST_MakePoint({lon},{lat}),4326)::geography, 30)""")

    if args.out:
        write_report(args.out, n_tickets, n_reports, results, plans)
        print(f"\nReport written to {args.out}")


def pct(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))]


def explain(db, sql):
    from sqlalchemy import text

    rows = db.execute(text("EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY ON) " + sql)).scalars().all()
    return "\n".join(rows)


def load_data(n: int) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from app.db import core_engine
    from app.seed.run import run as seed

    print(f"Preparing load database with {n:,} tickets …")
    cfg = Config(str(ROOT / "alembic.ini"), ini_section="core")
    cfg.set_main_option("script_location", str(ROOT / "migrations" / "core"))
    command.upgrade(cfg, "head")
    seed(reset=True)

    t0 = time.perf_counter()
    with core_engine().begin() as c:
        c.execute(text("SET LOCAL synchronous_commit = off"))
        c.execute(text("""
            INSERT INTO reporters (reporter_id)
            SELECT 'R-' || md5('reporter' || g) FROM generate_series(1, :r) g"""), {"r": max(1000, n // 5)})
        # 90% of tickets in KMC, 10% in Howrah; realistic mix of statuses and ages.
        c.execute(text("""
            INSERT INTO tickets (id, public_ref, category_id, location, severity, priority, status,
                                 created_at, sla_started_at, sla_due_at, resolved_at,
                                 report_count, unique_reporters, updated_at)
            SELECT gen_random_uuid(), 'LT-' || lpad(g::text, 8, '0'),
                   1 + (g % 9),
                   CASE WHEN g % 10 = 0
                        THEN ST_SetSRID(ST_MakePoint(88.24 + random() * 0.04, 22.55 + random() * 0.06), 4326)
                        ELSE ST_SetSRID(ST_MakePoint(88.30 + random() * 0.11, 22.46 + random() * 0.17), 4326) END,
                   1 + (g % 5), random() * 80,
                   (ARRAY['open','acknowledged','in_progress','fix_submitted','resolved','resolved','resolved','reopened'])[1 + (g % 8)],
                   c, c, c + interval '7 days',
                   CASE WHEN g % 8 IN (4, 5, 6) THEN c + (random() * interval '20 days') END,
                   1, 1, now()
            FROM (SELECT g, now() - random() * interval '180 days' AS c FROM generate_series(1, :n) g) s"""),
            {"n": n})
        c.execute(text("""
            UPDATE tickets t SET jurisdiction_path = j.path,
                   escalated_node_id = j.id,
                   owner_node_id = j.id,
                   authority_id = (SELECT a.id FROM authorities a WHERE a.type = 'municipal'
                                   AND a.jurisdiction_id = ANY(j.path) LIMIT 1)
            FROM LATERAL (SELECT id, path FROM jurisdictions
                          WHERE geom IS NOT NULL AND ST_Covers(geom, t.location)
                          ORDER BY cardinality(path) DESC LIMIT 1) j"""))
        c.execute(text("""
            INSERT INTO reports (id, ticket_id, reporter_id, category_id, photo_original_key,
                                 photo_public_key, phash, location, gps_accuracy_m, captured_at,
                                 received_at, status, verification_score)
            SELECT gen_random_uuid(), t.id,
                   'R-' || md5('reporter' || (1 + (abs(hashtext(t.public_ref || k::text)) % :r))),
                   t.category_id, 'orig/' || t.id || '/' || k, 'pub/' || t.id || '/' || k,
                   substr(md5(t.id::text || k), 1, 16), t.location, 8, t.created_at, t.created_at,
                   'verified', 0.8
            FROM tickets t CROSS JOIN LATERAL generate_series(1, 1 + (abs(hashtext(t.public_ref)) % 3)) k"""),
            {"r": max(1000, n // 5)})
        c.execute(text("""
            UPDATE tickets t SET report_count = s.n, unique_reporters = s.u
            FROM (SELECT ticket_id, count(*) n, count(DISTINCT reporter_id) u FROM reports GROUP BY ticket_id) s
            WHERE s.ticket_id = t.id"""))
        c.execute(text("""
            INSERT INTO ticket_events (ticket_id, type, actor_type, payload, created_at)
            SELECT id, 'escalated', 'system', '{"reason": "SLA breached (load test)", "public": true}'::jsonb,
                   sla_due_at FROM tickets WHERE abs(hashtext(public_ref)) % 10 = 0"""))
    with core_engine().connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text("VACUUM ANALYZE"))
    print(f"Loaded in {time.perf_counter() - t0:.1f} s\n")


def write_report(path, n_tickets, n_reports, results, plans):
    lines = [
        "# Load test results",
        "",
        f"Synthetic data: **{n_tickets:,} tickets**, **{n_reports:,} reports** across the sample",
        "Kolkata and Howrah wards, 180 days of history, ~10% with SLA breaches.",
        "Timed with the application's own functions (not re-implementations), each run many",
        "times on a single local PostgreSQL 16 + PostGIS; figures are per call.",
        "",
        "Regenerate: `LOAD_CORE_DATABASE_URL=… python scripts/loadtest.py --tickets 100000 --out ../docs/load-test.md`",
        "",
        "| Operation | Median (ms) | p95 (ms) |",
        "|---|---:|---:|",
    ]
    for name, times in results:
        lines.append(f"| {name} | {statistics.median(times):.1f} | {pct(times, 95):.1f} |")
    lines += ["", "## Query plans", ""]
    for name, plan in plans.items():
        lines += [f"### {name}", "", "```", plan, "```", ""]
    Path(path).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
