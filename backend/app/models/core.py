"""Core database models (tickets, reports, jurisdictions, officials).

ANONYMITY RULE: nothing in this module may store personal data. Citizens appear only
as `reporter_id` — a random opaque string (e.g. "R-8f3a…"). The mapping from
reporter_id to a real person lives only in the identity vault (app/models/vault.py),
which is a different database server with its own credentials and encryption key.
`tests/test_anonymity_schema.py` enforces this.

Geometry columns use SRID 4326 (WGS84 lat/lon, what phones report). Distance queries
cast to `geography` so ST_DWithin works in metres.
"""

import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class CoreBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# --- Enumerations (stored as short strings + CHECK constraints) -----------------


class JurisdictionLevel(enum.StrEnum):
    STATE = "state"
    DISTRICT = "district"
    MUNICIPALITY = "municipality"  # urban local body (ULB)
    WARD = "ward"
    BLOCK = "block"  # rural equivalent of municipality
    GRAM_PANCHAYAT = "gram_panchayat"  # rural equivalent of ward


class AuthorityType(enum.StrEnum):
    MUNICIPAL = "municipal"
    STATE_PWD = "state_pwd"
    STATE_HIGHWAYS = "state_highways"
    NHAI = "nhai"
    CANTONMENT = "cantonment"
    OTHER = "other"


class OfficialRole(enum.StrEnum):
    OFFICIAL = "official"
    GOV_ADMIN = "gov_admin"
    PLATFORM_ADMIN = "platform_admin"


class TicketStatus(enum.StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    FIX_SUBMITTED = "fix_submitted"
    RESOLVED = "resolved"
    REOPENED = "reopened"


class ReportStatus(enum.StrEnum):
    UNDER_VERIFICATION = "under_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ActorType(enum.StrEnum):
    CITIZEN = "citizen"  # actor_id is never exposed outside the platform
    OFFICIAL = "official"
    SYSTEM = "system"


class FixResponse(enum.StrEnum):
    YES = "yes"
    NO = "no"
    PARTLY = "partly"


def in_enum(column: str, enum_cls: type[enum.StrEnum]) -> str:
    """SQL for a CHECK constraint restricting `column` to the enum's values."""
    values = ", ".join(f"'{e.value}'" for e in enum_cls)
    return f"{column} IN ({values})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# --- Geography & ownership ------------------------------------------------------


class Jurisdiction(CoreBase):
    """One node of the administrative hierarchy (state → district → municipality → ward).

    `path` is a materialised path: the ids from the root down to this node, inclusive.
    Tickets copy the path of their ward, so "official at node N sees tickets under N"
    becomes the fast, GIN-indexed query `N = ANY(ticket.jurisdiction_path)`.
    """

    __tablename__ = "jurisdictions"
    __table_args__ = (
        CheckConstraint(in_enum("level", JurisdictionLevel), name="level"),
        Index("ix_jurisdictions_geom", "geom", postgresql_using="gist"),
        Index("ix_jurisdictions_path", "path", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lgd_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("jurisdictions.id"), index=True)
    path: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'::integer[]")
    )
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True)
    # True for generated placeholder polygons; the UI must label these as sample data.
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class Authority(CoreBase):
    """A road-owning body (municipal roads dept, State PWD, NHAI regional office…)."""

    __tablename__ = "authorities"
    __table_args__ = (CheckConstraint(in_enum("type", AuthorityType), name="type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # The jurisdiction node whose officials act for this authority.
    jurisdiction_id: Mapped[int | None] = mapped_column(ForeignKey("jurisdictions.id"))


class RoadSegment(CoreBase):
    """A piece of road (from OSM or admin upload) tagged with its owning authority."""

    __tablename__ = "road_segments"
    __table_args__ = (Index("ix_road_segments_geom", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    osm_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str | None] = mapped_column(String(200))
    road_class: Mapped[str] = mapped_column(String(32), nullable=False)  # OSM highway=*
    is_bridge: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    authority_id: Mapped[int | None] = mapped_column(ForeignKey("authorities.id"), index=True)
    geom = mapped_column(Geometry("LINESTRING", srid=4326, spatial_index=False), nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class Category(CoreBase):
    """Issue category, e.g. pothole. SLA defaults are keyed by severity "1".."5"."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    default_sla_hours: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Reports closer than this (metres) with the same category merge into one ticket.
    cluster_radius_m: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")


# --- Tenants & officials --------------------------------------------------------


class Tenant(CoreBase):
    """A government client. Sees only the subtree under `root_node_id`."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    root_node_id: Mapped[int] = mapped_column(ForeignKey("jurisdictions.id"), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class SlaRule(CoreBase):
    """Per-tenant override of how many hours a ticket may stay unresolved."""

    __tablename__ = "sla_rules"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "category_id", "severity"),
        CheckConstraint("severity BETWEEN 1 AND 5", name="severity"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    hours: Mapped[int] = mapped_column(Integer, nullable=False)


class Official(CoreBase):
    """A government user, attached to one jurisdiction node and/or one authority."""

    __tablename__ = "officials"
    __table_args__ = (CheckConstraint(in_enum("role", OfficialRole), name="role"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("jurisdictions.id"), index=True)
    authority_id: Mapped[int | None] = mapped_column(ForeignKey("authorities.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _created_at()


# --- Citizens (opaque), reports and tickets -------------------------------------


class Reporter(CoreBase):
    """A citizen as seen by the core DB: an opaque ID and a trust score. No PII."""

    __tablename__ = "reporters"

    reporter_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    trust_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.5")
    banned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = _created_at()


class Ticket(CoreBase):
    """One real-world issue. Many citizen reports of the same spot merge into one ticket."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(in_enum("status", TicketStatus), name="status"),
        CheckConstraint("severity BETWEEN 1 AND 5", name="severity"),
        Index("ix_tickets_location", "location", postgresql_using="gist"),
        Index("ix_tickets_jurisdiction_path", "jurisdiction_path", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    public_ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    location = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    h3_cell: Mapped[str | None] = mapped_column(String(16), index=True)
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    priority: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=TicketStatus.OPEN.value, index=True
    )
    jurisdiction_path: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'::integer[]")
    )
    authority_id: Mapped[int | None] = mapped_column(ForeignKey("authorities.id"), index=True)
    road_segment_id: Mapped[int | None] = mapped_column(ForeignKey("road_segments.id"))
    owner_node_id: Mapped[int | None] = mapped_column(ForeignKey("jurisdictions.id"), index=True)
    escalation_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unique_reporters: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Report(CoreBase):
    """A single citizen submission (one photo). Never returned by gov/public APIs as-is."""

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(in_enum("status", ReportStatus), name="status"),
        Index("ix_reports_location", "location", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), index=True)
    reporter_id: Mapped[str] = mapped_column(
        ForeignKey("reporters.reporter_id"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    photo_original_key: Mapped[str] = mapped_column(String(300), nullable=False)
    photo_public_key: Mapped[str | None] = mapped_column(String(300))
    phash: Mapped[str | None] = mapped_column(String(32), index=True)  # perceptual hash
    location = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = _created_at()
    verification_score: Mapped[float | None] = mapped_column(Float)
    verification_details: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=ReportStatus.UNDER_VERIFICATION.value
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)


class TicketEvent(CoreBase):
    """Append-only audit trail. Citizen actor ids are never exposed outside the platform."""

    __tablename__ = "ticket_events"
    __table_args__ = (CheckConstraint(in_enum("actor_type", ActorType), name="actor_type"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(48), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created_at()


class FixProof(CoreBase):
    """Photos an official uploads to prove a repair; checked by the vision model."""

    __tablename__ = "fix_proofs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id"), nullable=False, index=True
    )
    official_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("officials.id"), nullable=False)
    photo_keys: Mapped[list[str]] = mapped_column(ARRAY(String(300)), nullable=False)
    location = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vision_result: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _created_at()


class FixConfirmation(CoreBase):
    """A reporter's answer to "Is this fixed?". Gov only ever sees aggregate counts."""

    __tablename__ = "fix_confirmations"
    __table_args__ = (
        PrimaryKeyConstraint("ticket_id", "reporter_id"),
        CheckConstraint(in_enum("response", FixResponse), name="response"),
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    reporter_id: Mapped[str] = mapped_column(
        ForeignKey("reporters.reporter_id"), nullable=False
    )
    response: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = _created_at()
