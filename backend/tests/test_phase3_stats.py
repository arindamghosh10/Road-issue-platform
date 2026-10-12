"""Phase 3: dashboard statistics (public and scoped government)."""

import pytest

from app.tickets.sla import run_sla_sweep
from tests.test_phase1_flow import REPORTER_ID_RE, WARD1, login, phone
from tests.test_phase2_gov import _set, gov_login, make_ticket, reporter_headers, upload_fix

pytestmark = pytest.mark.db

WARD2 = (22.6229, 88.3137)  # centre of sample KMC Ward 2 (next grid cell east)
HMC_WARD = (22.59, 88.25)


@pytest.fixture
def scenario(client):
    """Ward 1: two tickets (one resolved); Ward 2: one ticket; Howrah: one ticket."""
    resolved = make_ticket(client, seed=300)
    assert upload_fix(client, gov_login(client, "kmc.ward001"), resolved).status_code == 200
    citizen = reporter_headers(client, 300, 1)[0]
    r = client.post(f"/api/v1/citizen/tickets/{resolved}/confirm", headers=citizen,
                    json={"response": "yes"})
    assert r.json()["ticket_status"] == "resolved"

    headers = login(client, phone(310))
    from tests.test_phase1_flow import submit

    other = submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=3100,
                   category="waterlogging").json()["ticket_ref"]
    ward2 = make_ticket(client, at=WARD2, seed=320)
    howrah = make_ticket(client, at=HMC_WARD, seed=330)
    return {"resolved": resolved, "other": other, "ward2": ward2, "howrah": howrah}


def get(client, url, headers=None):
    r = client.get(url, headers=headers or {})
    assert r.status_code == 200, (url, r.text)
    return r.json()


def test_public_summary(client, scenario):
    s = get(client, "/api/v1/public/stats/summary")
    assert (s["total"], s["open"], s["resolved"]) == (4, 3, 1)
    assert s["resolution_rate"] == 0.25
    assert s["avg_resolution_hours"] is not None and s["avg_resolution_hours"] >= 0
    assert s["sla_compliance"] == 1.0 and s["breaches"] == 0
    assert s["by_status"]["resolved"] == 1 and s["by_status"]["open"] == 3


def test_drill_down_and_leaderboard(client, scenario):
    top = get(client, "/api/v1/public/stats/areas")
    assert [(a["name"], a["total"]) for a in top] == [("West Bengal", 4)]
    kmc_id = next(a["id"] for a in get(client, "/api/v1/public/stats/areas?level=municipality")
                  if a["name"] == "Kolkata Municipal Corporation")
    wards = get(client, f"/api/v1/public/stats/areas?parent_id={kmc_id}")
    assert [(w["name"], w["total"], w["resolved"]) for w in wards] == [
        ("KMC Ward 1", 2, 1), ("KMC Ward 2", 1, 0)]  # best resolution rate first
    assert wards[0]["has_children"] is False
    munis = get(client, "/api/v1/public/stats/areas?level=municipality")
    assert {m["name"] for m in munis} == {"Kolkata Municipal Corporation", "Howrah Municipal Corporation"}
    auths = get(client, "/api/v1/public/stats/authorities")
    assert {a["name"] for a in auths} >= {"KMC Roads Department (sample)"}


def test_filters_apply(client, scenario):
    assert get(client, "/api/v1/public/stats/summary?category=waterlogging")["total"] == 1
    kmc_id = next(a["id"] for a in get(client, "/api/v1/public/stats/areas?level=municipality")
                  if a["name"].startswith("Kolkata"))
    assert get(client, f"/api/v1/public/stats/summary?jurisdiction_id={kmc_id}")["total"] == 3
    assert get(client, "/api/v1/public/stats/summary?days=30")["total"] == 4
    cats = get(client, "/api/v1/public/stats/categories")
    assert {c["code"]: c["total"] for c in cats} == {"pothole": 3, "waterlogging": 1}


def test_trends_count_this_week(client, scenario):
    points = get(client, "/api/v1/public/stats/trends?weeks=4")
    assert len(points) == 4
    assert points[-1]["new"] == 4 and points[-1]["resolved"] == 1
    assert all(p["new"] == 0 for p in points[:-1])


def test_sla_breach_lowers_compliance(client, scenario):
    _set(scenario["ward2"], "sla_due_at = now() - interval '1 hour'")
    run_sla_sweep()
    s = get(client, "/api/v1/public/stats/summary")
    assert s["breaches"] == 1
    assert s["sla_compliance"] == 0.5  # tested: 1 resolved on time + 1 breached


def test_government_stats_are_scoped(client, scenario):
    ward1 = gov_login(client, "kmc.ward001")
    assert get(client, "/api/v1/gov/stats/summary", ward1)["total"] == 2
    assert get(client, "/api/v1/gov/stats/summary", gov_login(client, "kmc.ward002"))["total"] == 1
    assert get(client, "/api/v1/gov/stats/summary", gov_login(client, "hmc"))["total"] == 1
    assert get(client, "/api/v1/gov/stats/summary", gov_login(client, "state"))["total"] == 4

    kmc = gov_login(client, "kmc")
    me = get(client, "/api/v1/gov/me", kmc)
    wards = get(client, "/api/v1/gov/stats/areas", kmc)  # defaults to own area's children
    assert me["node_id"] and {w["name"] for w in wards} == {"KMC Ward 1", "KMC Ward 2"}
    ageing = get(client, "/api/v1/gov/stats/ageing", kmc)
    assert sum(b["count"] for b in ageing) == 2 and ageing[0]["bucket"] == "< 7 days"
    assert len(get(client, "/api/v1/gov/stats/trends", kmc)) == 12


def test_stats_never_expose_identity(client, scenario):
    urls = ["/api/v1/public/stats/summary", "/api/v1/public/stats/areas?level=ward",
            "/api/v1/public/stats/authorities", "/api/v1/public/stats/categories",
            "/api/v1/public/stats/trends"]
    for url in urls:
        raw = client.get(url).text
        assert not REPORTER_ID_RE.search(raw) and "98300" not in raw, url
