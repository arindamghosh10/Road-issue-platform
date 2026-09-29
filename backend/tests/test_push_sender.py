"""The Expo push sender reads Expo's per-message receipts correctly (no network: a fake
Expo server)."""

import json

import httpx

from app.identity import push
from app.identity.push import ExpoPushSender, PushMessage


def _messages(n: int) -> list[PushMessage]:
    return [PushMessage(f"ExponentPushToken[t{i:012d}]", push.TITLE, push.BODY, push.DATA)
            for i in range(n)]


def _fake_expo(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(push.httpx, "Client",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_receipts_map_to_ok_dead_error(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        assert {m["title"] for m in body} == {push.TITLE}  # only the generic text goes out
        return httpx.Response(200, json={"data": [
            {"status": "ok", "id": "a"},
            {"status": "error", "details": {"error": "DeviceNotRegistered"}},
            {"status": "error", "details": {"error": "MessageRateExceeded"}},
        ]})

    _fake_expo(monkeypatch, handler)
    assert ExpoPushSender().send(_messages(3)) == ["ok", "dead", "error"]
    assert len(seen) == 1


def test_batches_of_100_and_outage_is_an_error_not_a_crash(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(len(json.loads(request.content)))
        if len(calls) == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": [{"status": "ok"}] * calls[-1]})

    _fake_expo(monkeypatch, handler)
    outcomes = ExpoPushSender().send(_messages(150))
    assert calls == [100, 50]
    assert outcomes == ["ok"] * 100 + ["error"] * 50
