"""Phase 2: government workflow, against real Postgres + PostGIS test databases.

Acceptance criteria covered (brief §14):
* a ward ticket is visible to that ward's official and to the municipality, district
  and state officials above it, and invisible to a sibling ward's official
* a government API response never contains a reporter id or identity field
* a ticket past its SLA is escalated one level and the new level gets an alert
* a ticket closes only after the fix proof passes the vision check and the reporter
  confirmation rule is met; a dispute reopens it
"""

from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from sqlalchemy import text

from app.db import core_engine
from app.notifications.service import get_email_sender
from app.tickets.sla import run_sla_sweep
from tests.images import blank_photo, road_photo
from tests.test_phase1_flow import (
    DEG_PER_M_LAT,
    FORBIDDEN_KEYS,
    ON_NH12,
    REPORTER_ID_RE,
    WARD1,
    _walk,
    login,
    phone,
    submit,
)

pytestmark = pytest.mark.db
PASSWORD = "roadwatch-demo"


def gov_login(client, who: str, totp_code: str | None = None) -> dict:
    r = client.post("/api/v1/gov/auth/login", json={
        "email": f"{who}@demo.roadwatch.in", "password": PASSWORD, "totp_code": totp_code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_ticket(client, reporters: int = 1, at=WARD1, seed: int = 0) -> str:
    ref = None
    for i in range(reporters):
        headers = login(client, phone(500 + seed + i))
        r = submit(client, headers, lat=at[0] + i * 3 * DEG_PER_M_LAT, lon=at[1], seed=5000 + seed + i)
        assert r.json()["status"] == "verified", r.json()
        ref = r.json()["ticket_ref"]
    return ref


def reporter_headers(client, seed: int, count: int) -> list[dict]:
    """Log the same phones back in (same person → same reporter id)."""
    return [login(client, phone(500 + seed + i)) for i in range(count)]


def upload_fix(client, headers, ref, *, lat=WARD1[0], lon=WARD1[1], photo=None, seed=9000):
    return client.post(
        f"/api/v1/gov/tickets/{ref}/fix-proof", headers=headers,
        files={"photo": ("fix.jpg", photo or road_photo(seed), "image/jpeg")},
        data={"lat": str(lat), "lon": str(lon),
              "captured_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
              "capture_source": "in_app_camera"},
    )


def notifications(client, headers) -> list[dict]:
    return client.get("/api/v1/gov/notifications", headers=headers).json()


# --- Auth ------------------------------------------------------------------------------


def test_official_login_rejects_bad_password(client):
    r = client.post("/api/v1/gov/auth/login",
                    json={"email": "kmc@demo.roadwatch.in", "password": "wrong"})
    assert r.status_code == 401
    me = client.get("/api/v1/gov/me", headers=gov_login(client, "kmc")).json()
    assert me["node"] == "Kolkata Municipal Corporation" and me["node_level"] == "municipality"


def test_two_factor_login(client):
    headers = gov_login(client, "kmc")
    secret = client.post("/api/v1/gov/auth/2fa/setup", headers=headers).json()["secret"]
    assert client.post("/api/v1/gov/auth/2fa/enable", headers=headers,
                       json={"code": "000000"}).status_code == 400
    assert client.post("/api/v1/gov/auth/2fa/enable", headers=headers,
                       json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    r = client.post("/api/v1/gov/auth/login",
                    json={"email": "kmc@demo.roadwatch.in", "password": PASSWORD})
    assert r.status_code == 401  # password alone is no longer enough
    gov_login(client, "kmc", totp_code=pyotp.TOTP(secret).now())


def test_citizen_and_official_tokens_are_not_interchangeable(client):
    citizen = login(client, phone(1))
    official = gov_login(client, "kmc")
    assert client.get("/api/v1/gov/tickets", headers=citizen).status_code == 401
    assert client.get("/api/v1/citizen/reports", headers=official).status_code == 401


# --- Acceptance: access control -----------------------------------------------------------


def test_ward_ticket_visible_up_the_hierarchy_but_not_to_sibling_ward(client):
    ref = make_ticket(client)
    for who in ("kmc.ward001", "kmc", "district.kolkata", "state"):
        h = gov_login(client, who)
        assert [t["ref"] for t in client.get("/api/v1/gov/tickets", headers=h).json()] == [ref], who
        assert client.get(f"/api/v1/gov/tickets/{ref}", headers=h).status_code == 200, who
    for who in ("kmc.ward002", "hmc"):
        h = gov_login(client, who)
        assert client.get("/api/v1/gov/tickets", headers=h).json() == [], who
        assert client.get(f"/api/v1/gov/tickets/{ref}", headers=h).status_code == 404, who
        assert client.post(f"/api/v1/gov/tickets/{ref}/status", headers=h,
                           json={"status": "acknowledged"}).status_code == 404, who


def test_highway_ticket_visible_to_road_authority(client):
    ref = make_ticket(client, at=ON_NH12, seed=10)
    h = gov_login(client, "nhai")
    assert ref in [t["ref"] for t in client.get("/api/v1/gov/tickets", headers=h).json()]


def test_new_ticket_alerts_ward_official_by_inbox_and_email(client):
    get_email_sender().sent.clear()
    ref = make_ticket(client, seed=20)
    inbox = notifications(client, gov_login(client, "kmc.ward001"))
    assert [n["kind"] for n in inbox] == ["new_ticket"] and inbox[0]["ticket_ref"] == ref
    assert any(to == "kmc.ward001@demo.roadwatch.in" for to, _, _ in get_email_sender().sent)
    assert notifications(client, gov_login(client, "kmc.ward002")) == []


# --- Acceptance: no identity in government responses --------------------------------------


def test_government_responses_never_expose_identity(client):
    ref = make_ticket(client, reporters=3, seed=30)
    h = gov_login(client, "kmc")
    client.post(f"/api/v1/gov/tickets/{ref}/notes", headers=h, json={"text": "Crew booked"})
    with core_engine().connect() as c:
        reporter_ids = c.execute(text("SELECT reporter_id FROM reporters")).scalars().all()
    assert len(reporter_ids) == 3

    urls = ["/api/v1/gov/tickets", f"/api/v1/gov/tickets/{ref}", "/api/v1/gov/me",
            f"/api/v1/gov/tickets/{ref}/assignees", "/api/v1/gov/notifications",
            "/api/v1/gov/tickets/export.csv", f"/api/v1/public/tickets/{ref}/timeline"]
    for url in urls:
        resp = client.get(url, headers=h)
        assert resp.status_code == 200, url
        raw = resp.text
        assert not REPORTER_ID_RE.search(raw), url
        assert not any(rid in raw for rid in reporter_ids), url
        assert "98300" not in raw, url
        if resp.headers["content-type"].startswith("application/json"):
            for path, key, _ in _walk(resp.json()):
                assert key not in FORBIDDEN_KEYS, f"{url}: {path}"

    detail = client.get(f"/api/v1/gov/tickets/{ref}", headers=h).json()
    attached = [e for e in detail["timeline"] if e["type"] == "report_attached"]
    assert len(attached) == 3 and all(e["by"] == "citizen" for e in attached)


# --- Lifecycle & assignment ------------------------------------------------------------------


def test_status_lifecycle_and_audit_trail(client):
    ref = make_ticket(client, seed=40)
    h = gov_login(client, "kmc.ward001")

    def move(status):
        return client.post(f"/api/v1/gov/tickets/{ref}/status", headers=h,
                           json={"status": status, "note": f"-> {status}"})

    assert move("acknowledged").status_code == 200
    assert move("in_progress").status_code == 200
    for forbidden in ("resolved", "fix_submitted", "open"):
        assert move(forbidden).status_code == 409
    public_types = [e["type"] for e in client.get(f"/api/v1/public/tickets/{ref}/timeline").json()]
    assert public_types == ["ticket_created", "status_changed", "status_changed"]


def test_assignment_only_to_officials_covering_the_area(client):
    ref = make_ticket(client, seed=50)
    kmc = gov_login(client, "kmc")
    assignees = {a["name"]: a["id"] for a in
                 client.get(f"/api/v1/gov/tickets/{ref}/assignees", headers=kmc).json()}
    assert "KMC Ward 1 Officer (demo)" in assignees
    assert "KMC Ward 2 Officer (demo)" not in assignees

    with core_engine().connect() as c:
        ward2_id = c.execute(text(
            "SELECT id FROM officials WHERE email = 'kmc.ward002@demo.roadwatch.in'")).scalar()
    r = client.post(f"/api/v1/gov/tickets/{ref}/assign", headers=kmc,
                    json={"official_id": str(ward2_id)})
    assert r.status_code == 422
    r = client.post(f"/api/v1/gov/tickets/{ref}/assign", headers=kmc,
                    json={"official_id": assignees["KMC Ward 1 Officer (demo)"]})
    assert r.status_code == 200 and r.json()["assigned_to"] == "KMC Ward 1 Officer (demo)"
    ward1 = gov_login(client, "kmc.ward001")
    assert "assigned" in [n["kind"] for n in notifications(client, ward1)]
    mine = client.get("/api/v1/gov/tickets?assigned_to_me=true", headers=ward1).json()
    assert [t["ref"] for t in mine] == [ref]


# --- Acceptance: SLA escalation --------------------------------------------------------------


def _set(ref: str, sql: str, **params) -> None:
    with core_engine().begin() as c:
        c.execute(text(f"UPDATE tickets SET {sql} WHERE public_ref = :ref"), {"ref": ref, **params})


def test_breached_sla_escalates_one_level_and_alerts_new_level(client):
    ref = make_ticket(client, seed=60)
    _set(ref, "sla_due_at = now() - interval '1 hour'")
    assert run_sla_sweep().escalated == [ref]

    t = client.get(f"/api/v1/public/tickets/{ref}").json()
    assert t["escalation_level"] == 1 and t["responsible_area"] == "Kolkata Municipal Corporation"
    assert "escalated" in [n["kind"] for n in notifications(client, gov_login(client, "kmc"))]
    assert "escalated" in [e["type"] for e in
                           client.get(f"/api/v1/public/tickets/{ref}/timeline").json()]

    # Fresh deadline at the new level: nothing happens until it passes too.
    assert run_sla_sweep().escalated == []
    _set(ref, "sla_due_at = now() - interval '1 hour'")
    run_sla_sweep()
    t = client.get(f"/api/v1/public/tickets/{ref}").json()
    assert t["escalation_level"] == 2 and t["responsible_area"] == "Kolkata"


def test_sla_warning_at_80_percent(client):
    ref = make_ticket(client, seed=70)
    _set(ref, "sla_started_at = now() - interval '90 hours', sla_due_at = now() + interval '10 hours'")
    assert run_sla_sweep().warned == [ref]
    assert run_sla_sweep().warned == []  # only once
    kinds = [n["kind"] for n in notifications(client, gov_login(client, "kmc.ward001"))]
    assert "sla_warning" in kinds


# --- Acceptance: fix proof + reporter confirmation ----------------------------------------------


def test_fix_proof_refused_when_far_away_or_not_repaired(client):
    ref = make_ticket(client, seed=80)
    h = gov_login(client, "kmc.ward001")
    far = upload_fix(client, h, ref, lat=WARD1[0] + 200 * DEG_PER_M_LAT)
    assert far.status_code == 422 and "m from the reported spot" in far.json()["detail"]
    blank = upload_fix(client, h, ref, photo=blank_photo())
    assert blank.status_code == 422 and "not fixed" in blank.json()["detail"]
    gallery = client.post(
        f"/api/v1/gov/tickets/{ref}/fix-proof", headers=h,
        files={"photo": ("f.jpg", road_photo(1), "image/jpeg")},
        data={"lat": str(WARD1[0]), "lon": str(WARD1[1]),
              "captured_at": datetime.now(UTC).isoformat(), "capture_source": "gallery"})
    assert gallery.status_code == 422
    assert client.get(f"/api/v1/public/tickets/{ref}").json()["status"] == "open"


def test_fix_confirmed_by_majority_resolves(client):
    ref = make_ticket(client, reporters=3, seed=90)
    r = upload_fix(client, gov_login(client, "kmc.ward001"), ref)
    assert r.status_code == 200 and r.json()["status"] == "fix_submitted"

    citizens = reporter_headers(client, 90, 3)
    pending = client.get("/api/v1/citizen/confirmations", headers=citizens[0]).json()
    assert [p["ticket_ref"] for p in pending] == [ref] and pending[0]["fix_photos"]
    kinds = [n["kind"] for n in client.get("/api/v1/citizen/notifications", headers=citizens[0]).json()]
    assert "fix_confirmation_request" in kinds

    # A citizen who did not report this ticket cannot vote.
    outsider = login(client, phone(999))
    assert client.post(f"/api/v1/citizen/tickets/{ref}/confirm", headers=outsider,
                       json={"response": "yes"}).status_code == 403

    r1 = client.post(f"/api/v1/citizen/tickets/{ref}/confirm", headers=citizens[0], json={"response": "yes"})
    assert r1.json()["ticket_status"] == "fix_submitted"  # 1 of 3: not yet 50%
    r2 = client.post(f"/api/v1/citizen/tickets/{ref}/confirm", headers=citizens[1], json={"response": "yes"})
    assert r2.json()["ticket_status"] == "resolved"  # 2 of 3 ≥ 50%

    detail = client.get(f"/api/v1/gov/tickets/{ref}", headers=gov_login(client, "kmc")).json()
    assert detail["confirmations"] == {"reporters": 3, "yes": 2, "no": 0, "partly": 0}
    assert client.get(f"/api/v1/public/tickets/{ref}").json()["resolved_on"] is not None


def test_disputed_fix_reopens_and_escalates(client):
    ref = make_ticket(client, reporters=3, seed=100)
    assert upload_fix(client, gov_login(client, "kmc.ward001"), ref).status_code == 200
    citizens = reporter_headers(client, 100, 3)
    client.post(f"/api/v1/citizen/tickets/{ref}/confirm", headers=citizens[0], json={"response": "no"})
    r = client.post(f"/api/v1/citizen/tickets/{ref}/confirm", headers=citizens[1], json={"response": "partly"})
    assert r.json()["ticket_status"] == "reopened"
    t = client.get(f"/api/v1/public/tickets/{ref}").json()
    assert t["escalation_level"] == 1 and t["responsible_area"] == "Kolkata Municipal Corporation"
    types = [e["type"] for e in client.get(f"/api/v1/public/tickets/{ref}/timeline").json()]
    assert types[-3:] == ["fix_submitted", "reopened", "escalated"]


def test_no_disputes_within_window_resolves(client):
    ref = make_ticket(client, reporters=2, seed=110)
    assert upload_fix(client, gov_login(client, "kmc.ward001"), ref).status_code == 200
    assert run_sla_sweep().decided == []  # window still open
    later = datetime.now(UTC) + timedelta(days=8)
    assert run_sla_sweep(now=later).decided == [ref]
    assert client.get(f"/api/v1/public/tickets/{ref}").json()["status"] == "resolved"
