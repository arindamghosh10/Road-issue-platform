"""Identity vault models — the ONLY place a reporter can be linked to a person.

Lives in a separate Postgres server (VAULT_DATABASE_URL) with its own credentials.
Only the citizen auth service may open a vault session. Government tenants never get
access to this database or to the keys in VAULT_ENCRYPTION_KEY / IDENTITY_HASH_PEPPER.

What is stored, and why:
* phone_encrypted     — Fernet-encrypted phone, so we can send OTPs. Unreadable without
                        the platform-held key.
* phone_lookup_hash   — HMAC of the phone, so login can find the row without decrypting
                        every row.
* identity_hash       — HMAC of an Aadhaar/DigiLocker identity once that is plugged in.
                        The Aadhaar number itself is NEVER stored. The hash lets us
                        enforce "one person, one account" and make bans stick.
* reporter_links      — identity ↔ opaque reporter_id used in the core DB.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.core import NAMING_CONVENTION


class VaultBase(DeclarativeBase):
    # Separate MetaData object: vault tables can never be created in the core DB by
    # accident, and core migrations never see them.
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdentityRecord(VaultBase):
    __tablename__ = "identities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    phone_lookup_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    identity_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    # 0 = unverified, 1 = phone OTP verified, 2 = Aadhaar/DigiLocker verified (future)
    verified_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    banned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OtpChallenge(VaultBase):
    """A one-time login code sent to a phone. Only a keyed hash of the code is stored."""

    __tablename__ = "otp_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_lookup_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    phone_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReporterLink(VaultBase):
    __tablename__ = "reporter_links"

    identity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("identities.id"), primary_key=True
    )
    reporter_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
