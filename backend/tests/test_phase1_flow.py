"""End-to-end Phase 1 tests against real Postgres + PostGIS test databases.

Covers the brief's acceptance criteria that Phase 1 can already meet:
* five reports within 30 m of the same category → one ticket with unique_reporters = 5
* public responses never contain a reporter id or any identity field
* public photos have no EXIF
* gallery uploads are refused
"""

import re
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import text

from app.db import core_engine, vault_engine
from app.identity.providers import get_otp_sender
from tests.images import blank_photo, road_photo

pytestmark = pytest.mark.db

# Centre of sample KMC Ward 1 (the north-west cell of the generated grid).
WARD1 = (22.6229, 88.3046)
# A vertex of the sample NH-12 segment (owned by NHAI).
ON_NH12 = (22.625, 88.395)
DEG_PER_M_LAT = 1 / 111_320

FORBIDDEN_KEYS = {"reporter_id", "phone", "phone_encrypted", "identity_hash", "identity_id",
                  "actor_id", "photo_original_key", "captured_at", "attestation_token"}
REPORTER_ID_RE = re.compile(r"R-[0-9a-f]{32}")


def login(client, phone: str) -> dict:
    r = client.post("/api/v1/citizen/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    challenge_id = r.json()["challenge_id"]
    code = get_otp_sender().last_code["+91" + phone[-10:]]
    r = client.post("/api/v1/citizen/auth/otp/verify",
                    json={"challenge_id": challenge_id, "code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def submit(client, headers, *, lat, lon, seed, category="pothole", photo=None,
           source="in_app_camera", captured_at=None, accuracy=8.0):
    captured_at = captured_at or datetime.now(UTC) - timedelta(minutes=2)
    return client.post(
        "/api/v1/citizen/reports",
        headers=headers,
        files={"photo": ("p.jpg", photo or road_photo(seed), "image/jpeg")},
        data={"category": category, "lat": str(lat), "lon": str(lon),
              "gps_accuracy_m": str(accuracy), "captured_at": captured_at.isoformat(),
              "capture_source": source, "description": "Deep pothole near the bus stop"},
    )


def phone(i: int) -> str:
    return f"98300{i:05d}"


# --- Identity & anonymity --------------------------------------------------------


def test_otp_login_gives_stable_opaque_id_and_vault_holds_no_plaintext(client):
    h1 = login(client, phone(1))
    h2 = login(client, phone(1))
    assert h1 != h2  # new token each time …
    with core_engine().connect() as c:
        reporters = c.execute(text("SELECT reporter_id FROM reporters")).scalars().all()
    assert len(reporters) == 1 and REPORTER_ID_RE.fullmatch(reporters[0])  # … same person

    with vault_engine().connect() as v:
        blob = b"".join(bytes(r[0]) for r in v.execute(text("SELECT phone_encrypted FROM identities")))
        hashes = v.execute(text("SELECT phone_lookup_hash FROM identities")).scalars().all()
    assert b"9830000001" not in blob and "9830000001" not in hashes[0]


def test_wrong_otp_is_refused(client):
    challenge_id = client.post(
        "/api/v1/citizen/auth/otp/request", json={"phone": phone(2)}).json()["challenge_id"]
    real = get_otp_sender().last_code["+91" + phone(2)]
    wrong = f"{(int(real) + 1) % 1_000_000:06d}"
    verify = {"challenge_id": challenge_id, "code": wrong}
    for _ in range(5):
        assert client.post("/api/v1/citizen/auth/otp/verify", json=verify).status_code == 400
    # After 5 wrong attempts even the right code no longer works.
    verify["code"] = real
    r = client.post("/api/v1/citizen/auth/otp/verify", json=verify)
    assert r.status_code == 400 and "expired" in r.json()["detail"]


def test_reports_require_login(client):
    r = submit(client, {}, lat=WARD1[0], lon=WARD1[1], seed=1)
    assert r.status_code == 401


# --- Acceptance: clustering ---------------------------------------------------------


def test_five_reports_within_30m_make_one_ticket_with_five_reporters(client):
    for i in range(5):
        headers = login(client, phone(10 + i))
        lat = WARD1[0] + i * 5 * DEG_PER_M_LAT  # spread over 20 m
        r = submit(client, headers, lat=lat, lon=WARD1[1], seed=100 + i)
        assert r.status_code == 202, r.text
        assert r.json()["status"] == "verified", r.json()

    tickets = client.get("/api/v1/public/tickets").json()
    assert len(tickets) == 1
    t = tickets[0]
    assert t["verified_reporters"] == 5 and t["report_count"] == 5
    assert [a["level"] for a in t["areas"]] == ["state", "district", "municipality", "ward"]
    assert t["areas"][-1]["name"] == "KMC Ward 1"
    assert t["authority"] == "KMC Roads Department (sample)"
    assert len(t["photos"]) == 5


def test_same_reporter_twice_counts_once(client):
    headers = login(client, phone(20))
    for seed in (200, 201):
        assert submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=seed).json()["status"] == "verified"
    t = client.get("/api/v1/public/tickets").json()[0]
    assert t["report_count"] == 2 and t["verified_reporters"] == 1


def test_far_apart_or_different_category_make_separate_tickets(client):
    headers = login(client, phone(30))
    submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=300)
    submit(client, headers, lat=WARD1[0] + 60 * DEG_PER_M_LAT, lon=WARD1[1], seed=301)
    submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=302, category="waterlogging")
    assert len(client.get("/api/v1/public/tickets").json()) == 3


def test_highway_report_routes_to_nhai(client):
    headers = login(client, phone(40))
    r = submit(client, headers, lat=ON_NH12[0], lon=ON_NH12[1], seed=400)
    assert r.json()["status"] == "verified", r.json()
    t = client.get(f"/api/v1/public/tickets/{r.json()['ticket_ref']}").json()
    assert t["authority"] == "NHAI Regional Office Kolkata (sample)"


# --- Rejections ---------------------------------------------------------------------


def test_gallery_upload_refused(client):
    headers = login(client, phone(50))
    r = submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=500, source="gallery")
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("kwargs", "reason_fragment"),
    [
        ({"lat": 28.61, "lon": 77.21}, "outside"),  # New Delhi: no boundaries loaded
        ({"photo": blank_photo()}, "road or bridge"),
        ({"captured_at": datetime.now(UTC) - timedelta(days=3)}, "older than"),
        ({"accuracy": 500.0}, "GPS"),
    ],
)
def test_bad_reports_are_rejected_with_reason(client, kwargs, reason_fragment):
    headers = login(client, phone(60))
    args = {"lat": WARD1[0], "lon": WARD1[1], "seed": 600} | kwargs
    r = submit(client, headers, **args)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "rejected" and reason_fragment in body["rejection_reason"]
    assert body["ticket_ref"] is None
    assert client.get("/api/v1/public/tickets").json() == []


def test_reused_photo_rejected(client):
    photo = road_photo(700)
    a, b = login(client, phone(70)), login(client, phone(71))
    assert submit(client, a, lat=WARD1[0], lon=WARD1[1], seed=0, photo=photo).json()["status"] == "verified"
    r = submit(client, b, lat=WARD1[0], lon=WARD1[1], seed=0, photo=photo).json()
    assert r["status"] == "rejected" and "already submitted" in r["rejection_reason"]


def test_citizens_see_only_their_own_reports(client):
    a, b = login(client, phone(80)), login(client, phone(81))
    report_id = submit(client, a, lat=WARD1[0], lon=WARD1[1], seed=800).json()["id"]
    assert client.get(f"/api/v1/citizen/reports/{report_id}", headers=a).status_code == 200
    assert client.get(f"/api/v1/citizen/reports/{report_id}", headers=b).status_code == 404
    assert len(client.get("/api/v1/citizen/reports", headers=a).json()) == 1
    assert client.get("/api/v1/citizen/reports", headers=b).json() == []


# --- Acceptance: public responses carry no identity; public photos carry no EXIF --------


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k, v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def test_public_endpoints_never_expose_identity(client):
    for i in range(3):
        submit(client, login(client, phone(90 + i)), lat=WARD1[0], lon=WARD1[1], seed=900 + i)
    ref = client.get("/api/v1/public/tickets").json()[0]["ref"]
    with core_engine().connect() as c:
        reporter_ids = c.execute(text("SELECT reporter_id FROM reporters")).scalars().all()
    assert len(reporter_ids) == 3

    for url in ("/api/v1/public/tickets", f"/api/v1/public/tickets/{ref}",
                "/api/v1/public/categories", "/api/v1/public/jurisdictions"):
        resp = client.get(url)
        assert resp.status_code == 200
        raw = resp.text
        assert not REPORTER_ID_RE.search(raw), url
        assert not any(rid in raw for rid in reporter_ids), url
        assert "98300" not in raw, url
        for path, key, _ in _walk(resp.json()):
            assert key not in FORBIDDEN_KEYS, f"{url}: {path}"


def test_public_photos_have_no_exif(client):
    from app.config import get_settings
    from app.storage import get_store

    submit(client, login(client, phone(95)), lat=WARD1[0], lon=WARD1[1], seed=950)
    url = client.get("/api/v1/public/tickets").json()[0]["photos"][0]
    key = url.split(get_settings().s3_public_base_url.rstrip("/") + "/", 1)[1]
    data = get_store().get(get_settings().s3_bucket_public, key)
    assert dict(Image.open(BytesIO(data)).getexif()) == {}
    assert b"TestPhoneCo" not in data and b"SERIAL-123456" not in data
