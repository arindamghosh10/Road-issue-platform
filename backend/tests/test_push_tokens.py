"""Citizen push notifications: device tokens live only in the identity vault (encrypted),
pushes carry no details, and they go out only after the change they announce commits."""

import pytest
from sqlalchemy import text

from app.db import core_engine, core_session, vault_engine
from app.identity.push import BODY, MAX_DEVICES, TITLE, get_push_sender
from app.models.core import Ticket
from app.notifications.service import notify_reporter
from tests.test_phase1_flow import WARD1, login, phone, submit
from tests.test_phase2_gov import gov_login

pytestmark = pytest.mark.db


def token(i: int) -> str:
    return f"ExponentPushToken[device-{i:06d}-abcdefgh]"


def register(client, headers, tok: str, platform: str = "android"):
    return client.put("/api/v1/citizen/push-token", headers=headers,
                      json={"token": tok, "platform": platform})


def sent_tokens() -> list[str]:
    return [m.token for m in get_push_sender().sent]


def my_reporter_id(client, headers) -> str:
    report_id = client.get("/api/v1/citizen/reports", headers=headers).json()[0]["id"]
    with core_engine().connect() as c:
        return c.execute(text("SELECT reporter_id FROM reports WHERE id = :id"), {"id": report_id}).scalar()


def test_token_is_stored_encrypted_in_the_vault_and_nowhere_in_core(client):
    headers = login(client, phone(4000))
    assert register(client, headers, token(1)).status_code == 204
    assert register(client, headers, token(1)).status_code == 204  # re-register: refresh only
    submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=40000)

    with vault_engine().connect() as c:
        rows = c.execute(text("SELECT token_encrypted, token_lookup_hash, platform FROM push_tokens")).all()
    assert len(rows) == 1
    enc, lookup, platform = rows[0]
    assert b"device-000001" not in bytes(enc) and "device" not in lookup and platform == "android"

    # Not a trace in any core table (the database officials' systems read from).
    with core_engine().connect() as c:
        tables = c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars().all()
        for table in tables:
            hits = c.execute(text(f'SELECT count(*) FROM "{table}" t WHERE t::text LIKE :p'),
                             {"p": "%PushToken%"}).scalar()
            assert hits == 0, table


@pytest.mark.parametrize("body", [
    {"token": "not-a-token", "platform": "android"},
    {"token": token(2), "platform": "windows"},
])
def test_bad_tokens_are_refused(client, body):
    headers = login(client, phone(4010))
    assert client.put("/api/v1/citizen/push-token", headers=headers, json=body).status_code == 422


def test_verified_report_pushes_a_generic_message(client):
    headers = login(client, phone(4020))
    register(client, headers, token(20), "ios")
    r = submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=40200)
    ref = r.json()["ticket_ref"]
    assert r.json()["status"] == "verified"

    [message] = get_push_sender().sent
    assert message.token == token(20)
    assert (message.title, message.body) == (TITLE, BODY)
    # Nothing about the report reaches Expo / Google / Apple.
    everything = f"{message.title} {message.body} {message.data}"
    assert ref not in everything and "pothole" not in everything.lower()
    # The details are in the authenticated in-app inbox instead.
    inbox = client.get("/api/v1/citizen/notifications", headers=headers).json()
    assert any(n["ticket_ref"] == ref for n in inbox)


def test_push_waits_for_commit_and_is_dropped_on_rollback(client):
    headers = login(client, phone(4030))
    register(client, headers, token(30))
    submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=40300)
    reporter_id = my_reporter_id(client, headers)
    get_push_sender().sent.clear()

    with core_session() as db:
        notify_reporter(db, reporter_id, None, "test", "Test", "rolled back")
        assert sent_tokens() == []  # nothing before commit
        db.rollback()
    assert sent_tokens() == []

    with core_session() as db:
        ticket = db.query(Ticket).one()
        notify_reporter(db, reporter_id, ticket, "test", "one", "a")
        notify_reporter(db, reporter_id, ticket, "test", "two", "b")
        db.commit()
    assert sent_tokens() == [token(30)]  # one push per commit, not per notification


def test_sign_out_removes_device_and_dead_tokens_are_forgotten(client):
    headers = login(client, phone(4040))
    register(client, headers, token(40))
    register(client, headers, token(41))
    other = login(client, phone(4041))
    # Someone else can't remove my device.
    assert client.post("/api/v1/citizen/push-token/remove", headers=other,
                       json={"token": token(40)}).status_code == 204
    assert client.post("/api/v1/citizen/push-token/remove", headers=headers,
                       json={"token": token(41)}).status_code == 204

    get_push_sender().dead_tokens.add(token(40))  # the app was uninstalled
    submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=40400)
    assert sent_tokens() == [token(40)]
    with vault_engine().connect() as c:
        assert c.execute(text("SELECT count(*) FROM push_tokens")).scalar() == 0


def test_device_moves_to_the_account_that_registered_it_last(client):
    first, second = login(client, phone(4050)), login(client, phone(4051))
    register(client, first, token(50))
    register(client, second, token(50))
    submit(client, first, lat=WARD1[0], lon=WARD1[1], seed=40500)
    assert sent_tokens() == []  # the phone now belongs to the second account


def test_device_limit_keeps_the_most_recent(client):
    headers = login(client, phone(4060))
    for i in range(MAX_DEVICES + 2):
        register(client, headers, token(600 + i))
    submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=40600)
    assert sorted(sent_tokens()) == [token(600 + i) for i in range(2, MAX_DEVICES + 2)]


def test_ban_forgets_devices(client):
    headers = login(client, phone(4070))
    register(client, headers, token(70))
    submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=40700)
    report_id = client.get("/api/v1/citizen/reports", headers=headers).json()[0]["id"]
    r = client.post(f"/api/v1/admin/reports/{report_id}/ban-sender", headers=gov_login(client, "platform"),
                    json={"reason": "Spam reports", "withdraw_reports": False})
    assert r.status_code == 200
    with vault_engine().connect() as c:
        assert c.execute(text("SELECT count(*) FROM push_tokens")).scalar() == 0


def test_push_text_follows_the_app_language(client):
    from app.identity.push import BODIES

    headers = login(client, phone(4080))
    r = client.put("/api/v1/citizen/push-token", headers=headers,
                   json={"token": token(80), "platform": "android", "lang": "bn"})
    assert r.status_code == 204
    ref = submit(client, headers, lat=WARD1[0], lon=WARD1[1], seed=40800).json()["ticket_ref"]
    [message] = get_push_sender().sent
    assert message.body == BODIES["bn"] and ref not in message.body
    bad = client.put("/api/v1/citizen/push-token", headers=headers,
                     json={"token": token(81), "platform": "android", "lang": "fr"})
    assert bad.status_code == 422
