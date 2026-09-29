"""Citizen sign-in via phone OTP. The ONLY module that reads or writes the identity vault.

Flow:
1. request_otp(phone)   → stores an encrypted phone + hashed code, "sends" the code.
2. verify_otp(id, code) → finds or creates the vault identity, finds or creates its
                          random reporter_id, makes sure the core DB knows that opaque
                          id, and returns it. The caller issues a token for reporter_id.

The core DB learns only the random reporter_id. Nothing flows the other way.
"""

import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import core_session, vault_session
from app.identity.providers import get_otp_sender
from app.models.core import Reporter
from app.models.vault import IdentityRecord, OtpChallenge, ReporterLink
from app.security import vault_crypto


class AuthError(Exception):
    """Login failed. `message` is safe to show to the citizen."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _code_hash(challenge_id: uuid.UUID, code: str) -> str:
    return vault_crypto.keyed_hash(f"{challenge_id}:{code}", "otp")


def request_otp(phone: str) -> uuid.UUID:
    s = get_settings()
    try:
        e164 = vault_crypto.normalize_phone(phone)
    except ValueError as exc:
        raise AuthError("Enter a valid Indian mobile number.") from exc
    lookup = vault_crypto.keyed_hash(e164, "phone")
    now = datetime.now(UTC)

    with vault_session() as vault:
        identity = vault.scalar(select(IdentityRecord).where(IdentityRecord.phone_lookup_hash == lookup))
        if identity and identity.banned:
            raise AuthError("This account is suspended.", 403)
        recent = vault.scalar(
            select(func.count()).select_from(OtpChallenge).where(
                OtpChallenge.phone_lookup_hash == lookup,
                OtpChallenge.created_at > now - timedelta(hours=1),
            )
        )
        if recent >= s.otp_max_requests_per_hour:
            raise AuthError("Too many codes requested. Try again later.", 429)

        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge = OtpChallenge(
            id=uuid.uuid4(),
            phone_lookup_hash=lookup,
            phone_encrypted=vault_crypto.encrypt(e164),
            expires_at=now + timedelta(minutes=s.otp_ttl_minutes),
        )
        challenge.code_hash = _code_hash(challenge.id, code)
        vault.add(challenge)
        vault.commit()

    get_otp_sender().send(e164, code)
    return challenge.id


def verify_otp(challenge_id: uuid.UUID, code: str) -> str:
    """Returns the citizen's opaque reporter_id."""
    s = get_settings()
    now = datetime.now(UTC)
    with vault_session() as vault:
        challenge = vault.get(OtpChallenge, challenge_id, with_for_update=True)
        if (
            challenge is None
            or challenge.consumed_at is not None
            or challenge.expires_at < now
            or challenge.attempts >= s.otp_max_attempts
        ):
            raise AuthError("Code expired. Request a new one.")
        if not hmac.compare_digest(challenge.code_hash, _code_hash(challenge.id, code.strip())):
            challenge.attempts += 1
            vault.commit()
            raise AuthError("Incorrect code.")
        challenge.consumed_at = now

        identity = vault.scalar(
            select(IdentityRecord).where(
                IdentityRecord.phone_lookup_hash == challenge.phone_lookup_hash
            )
        )
        if identity is None:
            identity = IdentityRecord(
                id=uuid.uuid4(),
                phone_encrypted=challenge.phone_encrypted,
                phone_lookup_hash=challenge.phone_lookup_hash,
                verified_level=1,
            )
            vault.add(identity)
            vault.flush()
        if identity.banned:
            vault.commit()
            raise AuthError("This account is suspended.", 403)

        link = vault.get(ReporterLink, identity.id)
        if link is None:
            link = ReporterLink(identity_id=identity.id, reporter_id=vault_crypto.new_reporter_id())
            vault.add(link)
        reporter_id = link.reporter_id
        vault.commit()

    # Register the opaque id in the core DB (no personal data crosses over).
    with core_session() as core:
        core.execute(insert(Reporter).values(reporter_id=reporter_id).on_conflict_do_nothing())
        banned = core.scalar(select(Reporter.banned).where(Reporter.reporter_id == reporter_id))
        core.commit()
    if banned:
        raise AuthError("This account is suspended.", 403)
    return reporter_id


def set_reporter_ban(reporter_id: str, banned: bool) -> bool:
    """Ban (or lift the ban on) the person behind an opaque reporter id.

    The ban is applied in BOTH stores:
    * vault — the identity is marked banned, so the same phone number (and, later, the
      same Aadhaar hash) cannot sign in again or register a fresh account;
    * core  — the reporter id is marked banned, so existing tokens stop working at once.
    Nobody — not the admin who triggers it, not the government — learns who the person
    is. Returns False if the reporter id is unknown.
    """
    now = datetime.now(UTC)
    with vault_session() as vault:
        link = vault.scalar(select(ReporterLink).where(ReporterLink.reporter_id == reporter_id))
        if link is not None:
            identity = vault.get(IdentityRecord, link.identity_id, with_for_update=True)
            identity.banned = banned
            identity.banned_at = now if banned else None
            vault.commit()
    with core_session() as core:
        reporter = core.get(Reporter, reporter_id, with_for_update=True)
        if reporter is None:
            return False
        reporter.banned = banned
        core.commit()
    return True
