"""Rate limiting: slow down brute-force and spam without blocking normal use.

A fixed-window counter per (rule, key): e.g. "at most 8 official logins per email per
15 minutes". Counters live in Redis (shared by every API process) and expire on their
own. Keys are keyed hashes — Redis never holds raw IPs, emails or phone numbers.

Limits are deliberately generous for real people and tight for scripts. When one is hit
the API answers 429 with a Retry-After header, and the hit is written to the audit log.

Backends: "redis" (default), "memory" (tests, single process), "off".
"""

import threading
import time
from dataclasses import dataclass
from functools import lru_cache

from fastapi import HTTPException, Request

from app.config import get_settings
from app.security.vault_crypto import keyed_hash


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window_s: int


# Central list so the limits are easy to review and tune.
RULES = {
    "otp_request_ip": Rule("otp_request_ip", 20, 3600),         # codes requested per IP per hour
    "otp_verify_ip": Rule("otp_verify_ip", 30, 600),            # code guesses per IP per 10 min
    "gov_login_ip": Rule("gov_login_ip", 30, 900),              # official logins per IP per 15 min
    "gov_login_email": Rule("gov_login_email", 8, 900),         # per account per 15 min
    "report_hour": Rule("report_hour", 10, 3600),               # reports per citizen per hour
    "report_day": Rule("report_day", 30, 86400),                # reports per citizen per day
    "sighting_hour": Rule("sighting_hour", 30, 3600),           # "I see this too" per citizen per hour
    "confirm_hour": Rule("confirm_hour", 30, 3600),             # fix answers per citizen per hour
    "push_token_hour": Rule("push_token_hour", 20, 3600),       # device (un)registrations per citizen
    "gov_export_hour": Rule("gov_export_hour", 20, 3600),       # CSV exports per official per hour
    "gov_fix_proof_hour": Rule("gov_fix_proof_hour", 60, 3600), # repair photos per official per hour
}


class RateLimited(Exception):
    def __init__(self, rule: Rule, retry_after: int) -> None:
        super().__init__(rule.name)
        self.rule = rule
        self.retry_after = retry_after


class _MemoryCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[int, float]] = {}

    def hit(self, key: str, window_s: int) -> tuple[int, int]:
        now = time.time()
        with self._lock:
            count, expires = self._counts.get(key, (0, now + window_s))
            if now >= expires:
                count, expires = 0, now + window_s
            count += 1
            self._counts[key] = (count, expires)
            return count, max(1, int(expires - now))

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


class _RedisCounter:
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)

    def hit(self, key: str, window_s: int) -> tuple[int, int]:
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_s, nx=True)  # set the window only on the first hit
        pipe.ttl(key)
        count, _, ttl = pipe.execute()
        return int(count), max(1, int(ttl))


@lru_cache
def _counter():
    s = get_settings()
    if s.rate_limit_backend == "memory":
        return _MemoryCounter()
    if s.rate_limit_backend == "redis":
        return _RedisCounter(s.redis_url)
    return None


def check(rule_name: str, key: str) -> None:
    """Count one attempt; raise RateLimited when over the limit. Fails OPEN if Redis is
    unreachable: an outage of the limiter must not take the whole service down."""
    counter = _counter()
    if counter is None:
        return
    rule = RULES[rule_name]
    bucket = f"rl:{rule.name}:{keyed_hash(key, 'ratelimit')[:32]}"
    try:
        count, ttl = counter.hit(bucket, rule.window_s)
    except Exception:  # noqa: BLE001 — see docstring
        return
    if count > rule.limit:
        raise RateLimited(rule, ttl)


def client_ip(request: Request) -> str:
    """The caller's IP. Behind a reverse proxy set TRUST_PROXY=true so the first
    X-Forwarded-For entry is used; otherwise that header is ignored (it's spoofable)."""
    if get_settings().trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(rule_name: str, key: str, *, actor_type: str = "anonymous", actor_id: str | None = None,
            ip: str | None = None) -> None:
    """check() + audit + HTTP 429. Use from API handlers."""
    try:
        check(rule_name, key)
    except RateLimited as exc:
        from app.audit import record

        record("rate_limited", actor_type=actor_type, actor_id=actor_id, ip=ip, success=False,
               details={"rule": exc.rule.name, "limit": exc.rule.limit, "window_s": exc.rule.window_s})
        raise HTTPException(
            429, "Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
