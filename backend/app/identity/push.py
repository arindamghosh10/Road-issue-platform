"""Push notifications to citizens' phones. Tokens live in the identity vault only.

Privacy rules:

1. **Tokens stay in the vault, encrypted.** A push token is a stable device identifier.
   Stored next to reports it would let anyone with core-DB access say "the phone that
   reported this pothole"; so, like the phone number, it lives only in the vault, keyed
   to the identity, and is read back only here, by the platform, to deliver a push.
2. **Push text is generic.** A push travels Expo → Google (FCM) / Apple (APNs), who see
   the text next to a device they can tie to a Google/Apple account. A ticket number or
   place name in the text would tell them which report this person made. So every push
   says only "you have an update"; the details sit in the in-app inbox, fetched over our
   own authenticated API.
3. **Only after commit, off the request path.** Callers mark reporters as "to notify"
   on their DB session; the push goes out after that transaction commits (never for a
   rolled-back change), from the background worker.
4. **Failures never break the workflow**, and tokens the push service reports as dead
   (app uninstalled) are deleted.
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol

import httpx
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import vault_session
from app.models.vault import IdentityRecord, PushToken, ReporterLink
from app.security import vault_crypto

log = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_-]{10,200}\]$")
PLATFORMS = {"android", "ios"}
MAX_DEVICES = 5  # per person; registering a 6th drops the least recently seen

# The only text that ever leaves for Expo / Google / Apple (rule 2 above), in the
# language the app registered with.
TITLE = "RoadWatch"
BODY = "You have an update on your reports. Open the app to see it."
BODIES = {
    "en": BODY,
    "hi": "आपकी शिकायतों पर नई जानकारी है। देखने के लिए ऐप खोलें।",
    "bn": "আপনার অভিযোগ নিয়ে নতুন খবর আছে। দেখতে অ্যাপ খুলুন।",
}
DATA = {"screen": "inbox"}


class PushError(Exception):
    pass


def _link(vault, reporter_id: str) -> ReporterLink | None:
    return vault.scalar(select(ReporterLink).where(ReporterLink.reporter_id == reporter_id))


def register_token(reporter_id: str, token: str, platform: str, lang: str = "en") -> None:
    """Remember this device for this person. Re-registering the same token only refreshes
    it; a token last used by another account moves to this one (the phone changed hands
    or the user switched accounts)."""
    if not TOKEN_RE.fullmatch(token):
        raise PushError("Not a valid push token.")
    if platform not in PLATFORMS:
        raise PushError("platform must be android or ios.")
    if lang not in BODIES:
        raise PushError("lang must be en, hi or bn.")
    lookup = vault_crypto.keyed_hash(token, "push")
    now = datetime.now(UTC)
    with vault_session() as vault:
        link = _link(vault, reporter_id)
        if link is None:
            raise PushError("Unknown account.")
        row = vault.scalar(select(PushToken).where(PushToken.token_lookup_hash == lookup)
                           .with_for_update())
        if row is None:
            row = PushToken(token_encrypted=vault_crypto.encrypt(token), token_lookup_hash=lookup,
                            identity_id=link.identity_id, platform=platform)
            vault.add(row)
        row.identity_id, row.platform, row.lang, row.last_seen_at = link.identity_id, platform, lang, now
        vault.flush()
        stale = vault.scalars(
            select(PushToken.id).where(PushToken.identity_id == link.identity_id)
            .order_by(PushToken.last_seen_at.desc()).offset(MAX_DEVICES)
        ).all()
        if stale:
            vault.execute(delete(PushToken).where(PushToken.id.in_(stale)))
        vault.commit()


def unregister_token(reporter_id: str, token: str) -> None:
    """Forget this device (sign-out). Only the owner's own token is removed."""
    lookup = vault_crypto.keyed_hash(token, "push")
    with vault_session() as vault:
        link = _link(vault, reporter_id)
        if link is not None:
            vault.execute(delete(PushToken).where(PushToken.token_lookup_hash == lookup,
                                                  PushToken.identity_id == link.identity_id))
            vault.commit()


def forget_all_devices(reporter_id: str) -> None:
    """Drop every device of this person (used when an account is banned)."""
    with vault_session() as vault:
        link = _link(vault, reporter_id)
        if link is not None:
            vault.execute(delete(PushToken).where(PushToken.identity_id == link.identity_id))
            vault.commit()


# --- Sending -------------------------------------------------------------------------------


@dataclass(frozen=True)
class PushMessage:
    token: str
    title: str
    body: str
    data: dict


class PushSender(Protocol):
    def send(self, messages: list[PushMessage]) -> list[str]:
        """Send, and return one outcome per message: "ok", "dead" (token no longer
        valid, forget it) or "error" (try again another time)."""
        ...


class LogPushSender:
    """Records pushes instead of sending them (dev without a phone, and tests)."""

    def __init__(self) -> None:
        self.sent: list[PushMessage] = []
        self.dead_tokens: set[str] = set()  # tests: pretend these apps were uninstalled

    def send(self, messages: list[PushMessage]) -> list[str]:
        self.sent.extend(messages)
        log.info("[PUSH LOG] %d message(s): %s", len(messages), messages[0].body if messages else "")
        return ["dead" if m.token in self.dead_tokens else "ok" for m in messages]


class ExpoPushSender:
    """Expo's push service (free): it forwards to FCM on Android and APNs on iOS."""

    URL = "https://exp.host/--/api/v2/push/send"
    BATCH = 100  # Expo's per-request limit

    def send(self, messages: list[PushMessage]) -> list[str]:
        s = get_settings()
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if s.expo_access_token:
            headers["Authorization"] = f"Bearer {s.expo_access_token}"
        outcomes: list[str] = []
        with httpx.Client(timeout=15) as http:
            for i in range(0, len(messages), self.BATCH):
                batch = messages[i:i + self.BATCH]
                body = [{"to": m.token, "title": m.title, "body": m.body, "data": m.data,
                         "sound": "default", "priority": "default"} for m in batch]
                try:
                    r = http.post(self.URL, json=body, headers=headers)
                    r.raise_for_status()
                    tickets = r.json().get("data", [])
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("push batch failed: %s", type(exc).__name__)
                    outcomes.extend(["error"] * len(batch))
                    continue
                for j in range(len(batch)):
                    t = tickets[j] if j < len(tickets) else {}
                    if t.get("status") == "ok":
                        outcomes.append("ok")
                    elif (t.get("details") or {}).get("error") == "DeviceNotRegistered":
                        outcomes.append("dead")
                    else:
                        outcomes.append("error")
        return outcomes


@lru_cache
def get_push_sender() -> PushSender:
    return ExpoPushSender() if get_settings().push_backend == "expo" else LogPushSender()


def deliver(reporter_ids: list[str]) -> int:
    """Send the generic "you have an update" push to every device of these reporters
    (banned accounts excluded). Returns how many devices were reached."""
    if not reporter_ids:
        return 0
    with vault_session() as vault:
        rows = vault.execute(
            select(PushToken.id, PushToken.token_encrypted, PushToken.lang)
            .join(ReporterLink, ReporterLink.identity_id == PushToken.identity_id)
            .join(IdentityRecord, IdentityRecord.id == PushToken.identity_id)
            .where(ReporterLink.reporter_id.in_(set(reporter_ids)), IdentityRecord.banned.is_(False))
        ).all()
    if not rows:
        return 0
    messages = [PushMessage(vault_crypto.decrypt(enc), TITLE, BODIES.get(lang, BODY), DATA)
                for _, enc, lang in rows]
    outcomes = get_push_sender().send(messages)
    dead = [row.id for row, outcome in zip(rows, outcomes, strict=True) if outcome == "dead"]
    if dead:
        with vault_session() as vault:
            vault.execute(delete(PushToken).where(PushToken.id.in_(dead)))
            vault.commit()
    return outcomes.count("ok")
