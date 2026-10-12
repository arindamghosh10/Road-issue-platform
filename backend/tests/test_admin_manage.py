"""Admin onboarding: officials with temporary passwords, organisation scoping, deadlines,
area imports. Platform admin = everything; government admin = their own organisation."""

import io
import json
import uuid


import pytest
from sqlalchemy import select, text

from app.db import core_engine, core_session
from app.models.core import Category, Jurisdiction, Ticket
from app.tickets.clustering import sla_hours
from tests.test_phase1_flow import login, phone, submit
from tests.test_phase2_gov import gov_login

pytestmark = pytest.mark.db


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def sign_in(client, email: str, password: str):
    return client.post("/api/v1/gov/auth/login", json={"email": email, "password": password})


def node_id(code: str) -> int:
    with core_engine().connect() as c:
        return c.execute(text("SELECT id FROM jurisdictions WHERE lgd_code = :c"), {"c": code}).scalar_one()


def wb_tenant(client, headers) -> str:
    return client.get("/api/v1/admin/tenants", headers=headers).json()[0]["id"]


def unique_email(tag: str) -> str:
    return f"{tag}.{uuid.uuid4().hex[:8]}@test.roadwatch.in"


# A square (lon/lat degrees) well outside the sample West Bengal area, so imported test
# areas never change where the other tests' reports land.
def square(lon: float, lat: float, size: float) -> dict:
    return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + size, lat], [lon + size, lat + size],
                                                [lon, lat + size], [lon, lat]]]}


def geojson(*features) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": props, "geometry": geom} for props, geom in features]}).encode()


def upload(client, headers, body: bytes):
    return client.post("/api/v1/admin/areas/import", headers=headers,
                       files={"file": ("areas.geojson", io.BytesIO(body), "application/geo+json")})


# --- Accounts --------------------------------------------------------------------------


def test_new_official_must_set_own_password_before_anything_else(client):
    admin = gov_login(client, "admin")
    email = unique_email("ward.officer")
    r = client.post("/api/v1/admin/officials", headers=admin, json={
        "name": "New Ward Officer", "email": email, "role": "official",
        "node_id": node_id("SAMPLE-KMC-W001")})
    assert r.status_code == 201, r.text
    temp = r.json()["temporary_password"]
    assert len(temp) >= 12 and r.json()["official"]["must_change_password"] is True
    assert r.json()["official"]["tenant"] == "West Bengal Demo Tenant (sample)"  # their admin's organisation

    token = sign_in(client, email, temp).json()["access_token"]
    me = client.get("/api/v1/gov/me", headers=bearer(token))
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    blocked = client.get("/api/v1/gov/tickets", headers=bearer(token))
    assert blocked.status_code == 403 and blocked.json()["detail"] == "Password change required."

    weak = client.post("/api/v1/gov/auth/password", headers=bearer(token),
                       json={"current_password": temp, "new_password": "short"})
    assert weak.status_code == 422
    r = client.post("/api/v1/gov/auth/password", headers=bearer(token),
                    json={"current_password": temp, "new_password": "a-long-new-password"})
    assert r.status_code == 200
    fresh = r.json()["access_token"]
    assert client.get("/api/v1/gov/tickets", headers=bearer(fresh)).status_code == 200
    assert client.get("/api/v1/gov/me", headers=bearer(token)).status_code == 401  # old session ended
    assert sign_in(client, email, temp).status_code == 401
    assert sign_in(client, email, "a-long-new-password").status_code == 200


def test_reset_password_and_deactivate_sign_the_official_out(client):
    admin = gov_login(client, "admin")
    email = unique_email("engineer")
    created = client.post("/api/v1/admin/officials", headers=admin, json={
        "name": "Engineer", "email": email, "node_id": node_id("SAMPLE-ULB-KMC")}).json()
    oid, temp = created["official"]["id"], created["temporary_password"]
    token = sign_in(client, email, temp).json()["access_token"]
    token = client.post("/api/v1/gov/auth/password", headers=bearer(token),
                        json={"current_password": temp, "new_password": "engineer-password-1"}).json()["access_token"]

    reset = client.post(f"/api/v1/admin/officials/{oid}/reset-password", headers=admin)
    assert reset.status_code == 200
    assert client.get("/api/v1/gov/me", headers=bearer(token)).status_code == 401
    assert sign_in(client, email, "engineer-password-1").status_code == 401
    token = sign_in(client, email, reset.json()["temporary_password"]).json()["access_token"]

    off = client.patch(f"/api/v1/admin/officials/{oid}", headers=admin, json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert client.get("/api/v1/gov/me", headers=bearer(token)).status_code == 401
    assert sign_in(client, email, reset.json()["temporary_password"]).status_code == 401

    with core_engine().connect() as c:
        actions = c.execute(text("SELECT action FROM audit_log WHERE target = :t ORDER BY id"),
                            {"t": f"official:{oid}"}).scalars().all()
    assert actions == ["official_created", "password_reset", "official_updated"]


def test_only_admins_and_each_admin_only_their_own_organisation(client):
    officer = gov_login(client, "kmc")
    assert client.get("/api/v1/admin/officials", headers=officer).status_code == 403
    citizen = login(client, phone(7801))
    assert client.get("/api/v1/admin/officials", headers=citizen).status_code == 401

    platform = gov_login(client, "platform")
    # A second organisation, rooted at Howrah, with its own admin.
    other = client.post("/api/v1/admin/tenants", headers=platform,
                        json={"name": f"Howrah Test {uuid.uuid4().hex[:4]}", "root_node_id": node_id("SAMPLE-ULB-HMC")})
    assert other.status_code == 201, other.text
    other_admin = client.post("/api/v1/admin/officials", headers=platform, json={
        "name": "Howrah Admin", "email": unique_email("hmc.admin"), "role": "gov_admin",
        "tenant_id": other.json()["id"], "node_id": node_id("SAMPLE-ULB-HMC")}).json()["official"]

    wb_admin = gov_login(client, "admin")
    emails = {o["email"] for o in client.get("/api/v1/admin/officials", headers=wb_admin).json()}
    assert "kmc@demo.roadwatch.in" in emails and other_admin["email"] not in emails
    assert client.post(f"/api/v1/admin/officials/{other_admin['id']}/reset-password",
                       headers=wb_admin).status_code == 404
    assert client.get(f"/api/v1/admin/tenants/{other.json()['id']}/deadlines", headers=wb_admin).status_code == 404
    # Government admins can't create platform admins, organisations or areas.
    r = client.post("/api/v1/admin/officials", headers=wb_admin, json={
        "name": "Sneaky", "email": unique_email("sneaky"), "role": "platform_admin"})
    assert r.status_code == 403
    assert client.post("/api/v1/admin/tenants", headers=wb_admin,
                       json={"name": "Ward Two Org", "root_node_id": node_id("SAMPLE-KMC-W002")}).status_code == 403
    assert upload(client, wb_admin, geojson()).status_code == 403
    # …nor reach the platform's moderation tools.
    assert client.get("/api/v1/admin/reports", headers=wb_admin).status_code == 403


def test_official_placement_rules(client):
    admin = gov_login(client, "admin")
    base = {"name": "Someone", "role": "official"}
    no_area = client.post("/api/v1/admin/officials", headers=admin, json={**base, "email": unique_email("a")})
    assert no_area.status_code == 422  # would see no tickets at all
    dup = client.post("/api/v1/admin/officials", headers=admin,
                      json={**base, "email": "kmc@demo.roadwatch.in", "node_id": node_id("SAMPLE-ULB-KMC")})
    assert dup.status_code == 409
    me = client.get("/api/v1/gov/me", headers=admin).json()
    assert client.patch(f"/api/v1/admin/officials/{me['id']}", headers=admin,
                        json={"is_active": False}).status_code == 422  # no locking yourself out


def test_deadline_override_applies_to_new_tickets(client):
    admin = gov_login(client, "admin")
    tenant = wb_tenant(client, admin)
    rows = client.get(f"/api/v1/admin/tenants/{tenant}/deadlines", headers=admin).json()
    assert len(rows) == 9 * 5  # every category × severity 1–5
    r = client.put(f"/api/v1/admin/tenants/{tenant}/deadlines", headers=admin,
                   json={"changes": [{"category": "pothole", "severity": 3, "hours": 7}]})
    assert r.status_code == 200
    cell = next(x for x in r.json() if x["category"] == "pothole" and x["severity"] == 3)
    assert cell["hours"] == 7
    with core_session() as db:
        pothole = db.scalar(select(Category).where(Category.code == "pothole"))
        path = db.scalar(select(Jurisdiction.path).where(Jurisdiction.lgd_code == "SAMPLE-KMC-W001"))
        assert sla_hours(db, path, pothole, 3) == 7
    # Back to the default.
    client.put(f"/api/v1/admin/tenants/{tenant}/deadlines", headers=admin,
               json={"changes": [{"category": "pothole", "severity": 3, "hours": None}]})
    with core_session() as db:
        assert sla_hours(db, path, pothole, 3) == int(pothole.default_sla_hours["3"])
    bad = client.put(f"/api/v1/admin/tenants/{tenant}/deadlines", headers=admin,
                     json={"changes": [{"category": "pothole", "severity": 3, "hours": 0}]})
    assert bad.status_code == 422


# --- Areas --------------------------------------------------------------------------


def test_area_import_creates_a_working_municipality(client):
    platform = gov_login(client, "platform")
    tag = uuid.uuid4().hex[:6].upper()
    lon, lat = 84.0, 20.0  # outside the sample West Bengal box
    body = geojson(
        ({"name": "Test State", "lgd_code": f"T-ST-{tag}", "level": "state"}, square(lon, lat, 1.0)),
        ({"name": "Test Ward 1", "lgd_code": f"T-W1-{tag}", "level": "ward",
          "parent_lgd_code": f"T-ULB-{tag}"}, square(lon + 0.1, lat + 0.1, 0.05)),  # child before parent is fine
        ({"name": "Test District", "lgd_code": f"T-DT-{tag}", "level": "district",
          "parent_lgd_code": f"T-ST-{tag}"}, square(lon, lat, 0.5)),
        ({"name": "Test Municipality", "lgd_code": f"T-ULB-{tag}", "level": "municipality",
          "parent_lgd_code": f"T-DT-{tag}"}, square(lon + 0.05, lat + 0.05, 0.2)),
    )
    r = upload(client, platform, body)
    assert r.status_code == 200, r.text
    assert (r.json()["created"], r.json()["updated"]) == (4, 0)

    with core_engine().connect() as c:
        ward = c.execute(text("SELECT id, path, is_sample, geom IS NOT NULL FROM jurisdictions WHERE lgd_code = :c"),
                         {"c": f"T-W1-{tag}"}).one()
    assert len(ward.path) == 4 and ward.path[-1] == ward.id and ward.is_sample is False and ward[3]

    # A citizen report there lands in the new ward.
    headers = login(client, phone(7802))
    ref = submit(client, headers, lat=lat + 0.12, lon=lon + 0.12, seed=78020).json()["ticket_ref"]
    with core_session() as db:
        assert db.scalar(select(Ticket.jurisdiction_path).where(Ticket.public_ref == ref))[-1] == ward.id

    # Re-uploading updates instead of duplicating; browsing shows the tree.
    again = upload(client, platform, body)
    assert (again.json()["created"], again.json()["updated"]) == (0, 4)
    roots = client.get("/api/v1/admin/areas", headers=platform).json()
    state = next(a for a in roots if a["lgd_code"] == f"T-ST-{tag}")
    assert state["children"] == 1 and state["has_boundary"]


def test_area_import_is_all_or_nothing(client):
    platform = gov_login(client, "platform")
    tag = uuid.uuid4().hex[:6].upper()
    body = geojson(
        ({"name": "Good", "lgd_code": f"G-{tag}", "level": "state"}, square(70.0, 15.0, 0.5)),
        ({"name": "Bad level", "lgd_code": f"B1-{tag}", "level": "village", "parent_lgd_code": f"G-{tag}"},
         square(70.1, 15.1, 0.1)),
        ({"name": "Projected", "lgd_code": f"B2-{tag}", "level": "district", "parent_lgd_code": f"G-{tag}"},
         square(500000.0, 2200000.0, 1000.0)),
        ({"name": "Orphan", "lgd_code": f"B3-{tag}", "level": "ward", "parent_lgd_code": "NOPE"},
         square(70.2, 15.2, 0.1)),
    )
    r = upload(client, platform, body)
    assert r.status_code == 422
    errors = " ".join(r.json()["detail"]["errors"])
    assert "level" in errors and "longitude/latitude" in errors and "NOPE" in errors
    with core_engine().connect() as c:
        assert c.execute(text("SELECT count(*) FROM jurisdictions WHERE lgd_code = :c"), {"c": f"G-{tag}"}).scalar() == 0
    assert upload(client, platform, b"not json").status_code == 422


def test_gov_admin_sees_only_their_area_tree(client):
    admin = gov_login(client, "admin")
    top = client.get("/api/v1/admin/areas", headers=admin).json()
    assert [a["lgd_code"] for a in top] == ["SAMPLE-ST-WB"]
    assert top[0]["tenant"] == "West Bengal Demo Tenant (sample)"
    platform = gov_login(client, "platform")
    tag = uuid.uuid4().hex[:6].upper()
    upload(client, platform, geojson(({"name": "Elsewhere", "lgd_code": f"E-{tag}", "level": "state"},
                                      square(75.0, 12.0, 0.5))))
    elsewhere = node_id(f"E-{tag}")
    assert client.get(f"/api/v1/admin/areas?parent_id={elsewhere}", headers=admin).status_code == 404
    r = client.post("/api/v1/admin/officials", headers=admin, json={
        "name": "Out of area", "email": unique_email("out"), "node_id": elsewhere})
    assert r.status_code == 404

