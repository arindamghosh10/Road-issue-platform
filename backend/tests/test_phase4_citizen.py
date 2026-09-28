"""Phase 4 backend support for the citizen app: nearby issues and "I see this too"."""

import pytest

from tests.test_phase1_flow import DEG_PER_M_LAT, REPORTER_ID_RE, WARD1, login, phone
from tests.test_phase2_gov import make_ticket

pytestmark = pytest.mark.db


def seen(client, headers, ref, *, lat=WARD1[0], lon=WARD1[1], accuracy=10.0):
    return client.post(f"/api/v1/citizen/tickets/{ref}/seen", headers=headers,
                       json={"lat": lat, "lon": lon, "gps_accuracy_m": accuracy})


def test_nearby_lists_closest_first_with_my_flags(client):
    near = make_ticket(client, seed=400)  # reporter: phone(900)
    far = make_ticket(client, at=(WARD1[0] + 800 * DEG_PER_M_LAT, WARD1[1]), seed=410)
    reporter = login(client, phone(900))
    r = client.get(f"/api/v1/citizen/tickets/nearby?lat={WARD1[0]}&lon={WARD1[1]}&radius_m=2000",
                   headers=reporter)
    assert r.status_code == 200
    rows = r.json()
    assert [t["ref"] for t in rows] == [near, far]
    assert rows[0]["distance_m"] < rows[1]["distance_m"]
    assert rows[0]["i_reported"] is True and rows[1]["i_reported"] is False
    assert not REPORTER_ID_RE.search(r.text)

    small = client.get(f"/api/v1/citizen/tickets/nearby?lat={WARD1[0]}&lon={WARD1[1]}&radius_m=200",
                       headers=reporter).json()
    assert [t["ref"] for t in small] == [near]


def test_i_see_this_too(client):
    ref = make_ticket(client, seed=420)
    reporter = login(client, phone(920))  # the original reporter
    neighbour = login(client, phone(7001))

    assert seen(client, reporter, ref).status_code == 409  # already reported it
    too_far = seen(client, neighbour, ref, lat=WARD1[0] + 400 * DEG_PER_M_LAT)
    assert too_far.status_code == 422 and "within 150 m" in too_far.json()["detail"]
    assert seen(client, neighbour, ref, accuracy=500).status_code == 422

    before = client.get(f"/api/v1/public/tickets/{ref}").json()
    r = seen(client, neighbour, ref)
    assert r.status_code == 200 and r.json()["also_seen"] == 1
    assert seen(client, neighbour, ref).status_code == 409  # only once

    after = client.get(f"/api/v1/public/tickets/{ref}").json()
    assert after["also_seen"] == 1
    assert after["verified_reporters"] == before["verified_reporters"]  # not a verified report
    nearby = client.get(f"/api/v1/citizen/tickets/nearby?lat={WARD1[0]}&lon={WARD1[1]}",
                        headers=neighbour).json()
    assert nearby[0]["i_saw"] is True


def test_gallery_style_upload_is_refused_by_the_api(client):
    """The app has no gallery picker at all; the API refuses anything not from its camera."""
    from tests.test_phase1_flow import submit

    r = submit(client, login(client, phone(7002)), lat=WARD1[0], lon=WARD1[1], seed=7002,
               source="gallery")
    assert r.status_code == 422
