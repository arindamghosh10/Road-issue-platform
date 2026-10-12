"""Phase 5: rate limits, abuse bans, attestation hook, audit log, and route-wide checks
that every government/public/admin endpoint needs the right login and never leaks
identity — enumerated from the app's own route table, so new endpoints are covered
automatically."""

import re
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.config import get_settings
from app.db import core_engine, core_session
from app.main import app
from app.models.core import Reporter, Ticket
from app.reports.service import NewReport, create_report, process_report
from app.security.vault_crypto import new_reporter_id
from tests.images import road_photo
from tests.test_phase1_flow import REPORTER_ID_RE, WARD1, login, phone, submit
from tests.test_phase2_gov import PASSWORD, gov_login, make_ticket, reporter_headers

pytestmark = pytest.mark.db


# --- Rate limits ---------------------------------------------------------------------------


def test_official_login_brute_force_is_rate_limited_and_audited(client):
    bad = {"email": "kmc@demo.roadwatch.in", "password": "wrong"}
    codes = [client.post("/api/v1/gov/auth/login", json=bad).status_code for _ in range(9)]
    assert codes[:8] == [401] * 8 and codes[8] == 429
    r = client.post("/api/v1/gov/auth/login", json={"email": "kmc@demo.roadwatch.in", "password": PASSWORD})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0  # even the right password waits

    with core_engine().connect() as c:
        rows = c.execute(text("SELECT action, success, ip_hash FROM audit_log ORDER BY id")).all()
    assert [a for a, _, _ in rows].count("official_login") == 8
    assert ("rate_limited", False) in {(a, s) for a, s, _ in rows}
    assert all(ip is None or re.fullmatch(r"[0-9a-f]{32}", ip) for _, _, ip in rows)  # hashed, never raw


def test_otp_requests_per_ip_are_limited(client):
    codes = [client.post("/api/v1/citizen/auth/otp/request", json={"phone": phone(3000 + i)}).status_code
             for i in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_report_flood_is_limited(client):
    headers = login(client, phone(3100))
    codes = [submit(client, headers, lat=WARD1[0] + i * 0.0006, lon=WARD1[1], seed=31000 + i).status_code
             for i in range(11)]
    assert codes[:10] == [202] * 10 and codes[10] == 429


# --- Abuse bans ------------------------------------------------------------------------------


def test_ban_by_report_withdraws_reports_and_blocks_reregistration(client):
    ref = make_ticket(client, reporters=2, seed=3200)
    abuser_headers = reporter_headers(client, 3200, 1)[0]
    my_reports = client.get("/api/v1/citizen/reports", headers=abuser_headers).json()
    report_id = my_reports[0]["id"]

    platform = gov_login(client, "platform")
    queue = client.get("/api/v1/admin/reports", headers=platform)
    assert queue.status_code == 200 and not REPORTER_ID_RE.search(queue.text)
    row = next(r for r in queue.json() if r["report_id"] == report_id)
    assert row["sender"] == {"reports": 1, "verified": 1, "rejected": 0, "banned": False}

    r = client.post(f"/api/v1/admin/reports/{report_id}/ban-sender", headers=platform,
                    json={"reason": "Submitting staged photos", "withdraw_reports": True})
    assert r.status_code == 200 and r.json() == {"banned": True, "reports_withdrawn": 1, "tickets_recounted": [ref]}

    assert client.get(f"/api/v1/public/tickets/{ref}").json()["verified_reporters"] == 1
    assert client.get("/api/v1/citizen/reports", headers=abuser_headers).status_code == 403  # token dead
    again = client.post("/api/v1/citizen/auth/otp/request", json={"phone": phone(500 + 3200)})
    assert again.status_code == 403  # same phone cannot sign back in

    audit = client.get("/api/v1/admin/audit?action=reporter_banned", headers=platform)
    assert audit.json()[0]["details"]["reason"] == "Submitting staged photos"

    r = client.post(f"/api/v1/admin/reports/{report_id}/unban-sender", headers=platform,
                    json={"reason": "Appeal accepted"})
    assert r.status_code == 200
    login(client, phone(500 + 3200))  # can sign in again


def test_admin_endpoints_are_platform_only(client):
    assert client.get("/api/v1/admin/reports").status_code == 401
    for who in ("kmc", "state", "admin"):  # even the government tenant admin
        assert client.get("/api/v1/admin/reports", headers=gov_login(client, who)).status_code == 403


def test_admin_audit_masks_citizen_ids(client):
    login(client, phone(3300))
    body = client.get("/api/v1/admin/audit?action=citizen_login", headers=gov_login(client, "platform")).text
    assert "citizen-" in body and not REPORTER_ID_RE.search(body)


# --- Device attestation hook ---------------------------------------------------------------------


@pytest.fixture
def attestation(monkeypatch):
    from app.security import attestation as mod

    def use(verdict, require=False):
        monkeypatch.setattr(get_settings(), "require_attestation", require)
        mod.get_attestation_verifier.cache_clear()
        monkeypatch.setattr(mod, "get_attestation_verifier",
                            lambda: type("V", (), {"verify": lambda self, t: verdict})())
        import app.reports.service as svc

        monkeypatch.setattr(svc, "get_attestation_verifier", mod.get_attestation_verifier)
    return use


def test_forged_attestation_is_rejected(client, attestation):
    attestation(False)
    r = submit(client, login(client, phone(3400)), lat=WARD1[0], lon=WARD1[1], seed=3400)
    assert r.json()["status"] == "rejected" and "integrity" in r.json()["rejection_reason"]


def test_required_attestation_rejects_unchecked_uploads(client, attestation):
    attestation(None, require=True)
    r = submit(client, login(client, phone(3401)), lat=WARD1[0], lon=WARD1[1], seed=3401)
    assert r.json()["status"] == "rejected" and "attestation required" in r.json()["rejection_reason"]


# --- Route-wide checks ------------------------------------------------------------------------------


def _routes(prefix: str) -> list[tuple[str, str]]:
    """Every (METHOD, path) under `prefix`, taken from the app's OpenAPI schema — the
    same list the API docs show — so it can't silently miss routers."""
    paths = app.openapi()["paths"]
    return [(method.upper(), path) for path, ops in paths.items() if path.startswith(prefix)
            for method in ops if method in {"get", "post", "put", "patch", "delete"}]


PUBLIC_AUTH = {"/api/v1/gov/auth/login", "/api/v1/citizen/auth/otp/request", "/api/v1/citizen/auth/otp/verify"}


def _fill(path: str, ref: str) -> str:
    return (path.replace("{ref}", ref).replace("{report_id}", str(uuid.uuid4()))
            .replace("{notification_id}", "1"))


def test_every_gov_admin_and_citizen_route_requires_login(client):
    ref = make_ticket(client, seed=3500)
    checked = 0
    for prefix in ("/api/v1/gov", "/api/v1/admin", "/api/v1/citizen"):
        for method, path in _routes(prefix):
            if path in PUBLIC_AUTH:
                continue
            r = client.request(method, _fill(path, ref))
            assert r.status_code == 401, f"{method} {path} answered {r.status_code} without login"
            checked += 1
    assert checked >= 30  # sanity: the enumeration really found the routes


def test_citizen_tokens_cannot_use_gov_or_admin_routes(client):
    citizen = login(client, phone(3600))
    checked = 0
    for prefix in ("/api/v1/gov", "/api/v1/admin"):
        for method, path in _routes(prefix):
            if path in PUBLIC_AUTH:
                continue
            assert client.request(method, _fill(path, "RW-X"), headers=citizen).status_code == 401, path
            checked += 1
    assert checked >= 20  # 23 gov + admin routes today


def test_no_get_endpoint_leaks_identity(client):
    """Call EVERY GET route of the gov, public and admin APIs with real data present and
    scan the raw responses for reporter ids, phone digits and identity field names."""
    ref = make_ticket(client, reporters=3, seed=3700)
    client.post(f"/api/v1/citizen/tickets/{ref}/seen", headers=login(client, phone(3701)),
                json={"lat": WARD1[0], "lon": WARD1[1], "gps_accuracy_m": 10})
    with core_engine().connect() as c:
        reporter_ids = c.execute(text("SELECT reporter_id FROM reporters")).scalars().all()
    assert len(reporter_ids) == 4

    tokens = {"/api/v1/gov": gov_login(client, "kmc"), "/api/v1/admin": gov_login(client, "platform"),
              "/api/v1/public": {}}
    forbidden_keys = {"reporter_id", "phone", "phone_encrypted", "identity_hash", "identity_id",
                      "photo_original_key", "attestation_token", "ip_hash"}
    scanned = 0
    for prefix, headers in tokens.items():
        for method, path in _routes(prefix):
            if method != "GET":
                continue
            r = client.get(_fill(path, ref), headers=headers)
            assert r.status_code == 200, f"GET {path}: {r.status_code} {r.text[:200]}"
            assert not REPORTER_ID_RE.search(r.text), path
            assert not any(rid in r.text for rid in reporter_ids), path
            assert "98300" not in r.text, path
            if r.headers["content-type"].startswith("application/json"):
                assert not (set(re.findall(r'"([a-z_]+)":', r.text)) & forbidden_keys), path
            scanned += 1
    assert scanned >= 20


# --- Concurrency: simultaneous reports of one pothole make ONE ticket ----------------------------------


def test_concurrent_reports_of_the_same_spot_make_one_ticket(clean_db):
    reporters = []
    with core_session() as db:
        for _ in range(8):
            rid = new_reporter_id()
            db.add(Reporter(reporter_id=rid))
            reporters.append(rid)
        db.commit()
    report_ids = []
    with core_session() as db:
        for i, rid in enumerate(reporters):
            report_ids.append(create_report(db, NewReport(
                reporter_id=rid, category_code="pothole", lat=WARD1[0] + i * 0.00002, lon=WARD1[1],
                gps_accuracy_m=5.0, captured_at=datetime.now(UTC) - timedelta(minutes=1),
                capture_source="in_app_camera", attestation_token=None, description=None,
                photo=road_photo(38000 + i), photo_content_type="image/jpeg")).id)

    barrier = threading.Barrier(len(report_ids))
    errors = []

    def work(report_id):
        try:
            barrier.wait()
            process_report(report_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(r,)) for r in report_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with core_session() as db:
        tickets = list(db.scalars(select(Ticket)))
    assert len(tickets) == 1 and tickets[0].unique_reporters == 8
