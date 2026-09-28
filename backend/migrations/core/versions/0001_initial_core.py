"""Initial core schema (PostGIS).

Revision ID: 0001_core
Revises:
Create Date: 2026-09-28

Mirrors app/models/core.py. Spatial columns get explicit GIST indexes; the
materialised-path arrays get GIN indexes for fast "ticket is under node N" queries.
"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None

JURISDICTION_LEVELS = ("state", "district", "municipality", "ward", "block", "gram_panchayat")
AUTHORITY_TYPES = ("municipal", "state_pwd", "state_highways", "nhai", "cantonment", "other")
OFFICIAL_ROLES = ("official", "gov_admin", "platform_admin")
TICKET_STATUSES = ("open", "acknowledged", "in_progress", "fix_submitted", "resolved", "reopened")
REPORT_STATUSES = ("under_verification", "verified", "rejected")
ACTOR_TYPES = ("citizen", "official", "system")
FIX_RESPONSES = ("yes", "no", "partly")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _geom(kind: str) -> Geometry:
    return Geometry(kind, srid=4326, spatial_index=False)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _now() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _jsonb(name: str) -> sa.Column:
    return sa.Column(
        name, postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
    )


def _int_path(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.ARRAY(sa.Integer()),
        server_default=sa.text("'{}'::integer[]"),
        nullable=False,
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "jurisdictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lgd_code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("level", sa.String(32), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        _int_path("path"),
        sa.Column("geom", _geom("MULTIPOLYGON"), nullable=True),
        sa.Column("is_sample", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_jurisdictions"),
        sa.UniqueConstraint("lgd_code", name="uq_jurisdictions_lgd_code"),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["jurisdictions.id"], name="fk_jurisdictions_parent_id_jurisdictions"
        ),
        sa.CheckConstraint(_in("level", JURISDICTION_LEVELS), name="ck_jurisdictions_level"),
    )
    op.create_index("ix_jurisdictions_parent_id", "jurisdictions", ["parent_id"])
    op.create_index("ix_jurisdictions_geom", "jurisdictions", ["geom"], postgresql_using="gist")
    op.create_index("ix_jurisdictions_path", "jurisdictions", ["path"], postgresql_using="gin")

    op.create_table(
        "authorities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("jurisdiction_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_authorities"),
        sa.ForeignKeyConstraint(
            ["jurisdiction_id"],
            ["jurisdictions.id"],
            name="fk_authorities_jurisdiction_id_jurisdictions",
        ),
        sa.CheckConstraint(_in("type", AUTHORITY_TYPES), name="ck_authorities_type"),
    )

    op.create_table(
        "road_segments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("osm_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("road_class", sa.String(32), nullable=False),
        sa.Column("is_bridge", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("authority_id", sa.Integer(), nullable=True),
        sa.Column("geom", _geom("LINESTRING"), nullable=False),
        sa.Column("is_sample", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_road_segments"),
        sa.ForeignKeyConstraint(
            ["authority_id"], ["authorities.id"], name="fk_road_segments_authority_id_authorities"
        ),
    )
    op.create_index("ix_road_segments_authority_id", "road_segments", ["authority_id"])
    op.create_index("ix_road_segments_geom", "road_segments", ["geom"], postgresql_using="gist")

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("default_sla_hours", postgresql.JSONB(), nullable=False),
        sa.Column("cluster_radius_m", sa.Integer(), server_default="30", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.UniqueConstraint("code", name="uq_categories_code"),
    )

    op.create_table(
        "tenants",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("root_node_id", sa.Integer(), nullable=False),
        _jsonb("config"),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
        sa.ForeignKeyConstraint(
            ["root_node_id"], ["jurisdictions.id"], name="fk_tenants_root_node_id_jurisdictions"
        ),
    )

    op.create_table(
        "sla_rules",
        sa.Column("tenant_id", _uuid(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("hours", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "category_id", "severity", name="pk_sla_rules"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_sla_rules_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name="fk_sla_rules_category_id_categories"
        ),
        sa.CheckConstraint("severity BETWEEN 1 AND 5", name="ck_sla_rules_severity"),
    )

    op.create_table(
        "officials",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("tenant_id", _uuid(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("authority_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _now(),
        sa.PrimaryKeyConstraint("id", name="pk_officials"),
        sa.UniqueConstraint("email", name="uq_officials_email"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_officials_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["node_id"], ["jurisdictions.id"], name="fk_officials_node_id_jurisdictions"
        ),
        sa.ForeignKeyConstraint(
            ["authority_id"], ["authorities.id"], name="fk_officials_authority_id_authorities"
        ),
        sa.CheckConstraint(_in("role", OFFICIAL_ROLES), name="ck_officials_role"),
    )
    op.create_index("ix_officials_tenant_id", "officials", ["tenant_id"])
    op.create_index("ix_officials_node_id", "officials", ["node_id"])

    op.create_table(
        "reporters",
        sa.Column("reporter_id", sa.String(40), nullable=False),
        sa.Column("trust_score", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("banned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _now(),
        sa.PrimaryKeyConstraint("reporter_id", name="pk_reporters"),
    )

    op.create_table(
        "tickets",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("public_ref", sa.String(20), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("location", _geom("POINT"), nullable=False),
        sa.Column("h3_cell", sa.String(16), nullable=True),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("priority", sa.Float(), server_default="0", nullable=False),
        sa.Column("status", sa.String(32), server_default="open", nullable=False),
        _int_path("jurisdiction_path"),
        sa.Column("authority_id", sa.Integer(), nullable=True),
        sa.Column("road_segment_id", sa.Integer(), nullable=True),
        sa.Column("owner_node_id", sa.Integer(), nullable=True),
        sa.Column("escalation_level", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("report_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unique_reporters", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        _now(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tickets"),
        sa.UniqueConstraint("public_ref", name="uq_tickets_public_ref"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name="fk_tickets_category_id_categories"
        ),
        sa.ForeignKeyConstraint(
            ["authority_id"], ["authorities.id"], name="fk_tickets_authority_id_authorities"
        ),
        sa.ForeignKeyConstraint(
            ["road_segment_id"],
            ["road_segments.id"],
            name="fk_tickets_road_segment_id_road_segments",
        ),
        sa.ForeignKeyConstraint(
            ["owner_node_id"], ["jurisdictions.id"], name="fk_tickets_owner_node_id_jurisdictions"
        ),
        sa.CheckConstraint(_in("status", TICKET_STATUSES), name="ck_tickets_status"),
        sa.CheckConstraint("severity BETWEEN 1 AND 5", name="ck_tickets_severity"),
    )
    op.create_index("ix_tickets_h3_cell", "tickets", ["h3_cell"])
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_authority_id", "tickets", ["authority_id"])
    op.create_index("ix_tickets_owner_node_id", "tickets", ["owner_node_id"])
    op.create_index("ix_tickets_sla_due_at", "tickets", ["sla_due_at"])
    op.create_index("ix_tickets_location", "tickets", ["location"], postgresql_using="gist")
    op.create_index(
        "ix_tickets_jurisdiction_path", "tickets", ["jurisdiction_path"], postgresql_using="gin"
    )

    op.create_table(
        "reports",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("ticket_id", _uuid(), nullable=True),
        sa.Column("reporter_id", sa.String(40), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("photo_original_key", sa.String(300), nullable=False),
        sa.Column("photo_public_key", sa.String(300), nullable=True),
        sa.Column("phash", sa.String(32), nullable=True),
        sa.Column("location", _geom("POINT"), nullable=False),
        sa.Column("gps_accuracy_m", sa.Float(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("verification_score", sa.Float(), nullable=True),
        _jsonb("verification_details"),
        sa.Column("status", sa.String(32), server_default="under_verification", nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], name="fk_reports_ticket_id_tickets"),
        sa.ForeignKeyConstraint(
            ["reporter_id"], ["reporters.reporter_id"], name="fk_reports_reporter_id_reporters"
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name="fk_reports_category_id_categories"
        ),
        sa.CheckConstraint(_in("status", REPORT_STATUSES), name="ck_reports_status"),
    )
    op.create_index("ix_reports_ticket_id", "reports", ["ticket_id"])
    op.create_index("ix_reports_reporter_id", "reports", ["reporter_id"])
    op.create_index("ix_reports_phash", "reports", ["phash"])
    op.create_index("ix_reports_location", "reports", ["location"], postgresql_using="gist")

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ticket_id", _uuid(), nullable=False),
        sa.Column("type", sa.String(48), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=True),
        _jsonb("payload"),
        _now(),
        sa.PrimaryKeyConstraint("id", name="pk_ticket_events"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name="fk_ticket_events_ticket_id_tickets"
        ),
        sa.CheckConstraint(_in("actor_type", ACTOR_TYPES), name="ck_ticket_events_actor_type"),
    )
    op.create_index("ix_ticket_events_ticket_id", "ticket_events", ["ticket_id"])

    op.create_table(
        "fix_proofs",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("ticket_id", _uuid(), nullable=False),
        sa.Column("official_id", _uuid(), nullable=False),
        sa.Column("photo_keys", postgresql.ARRAY(sa.String(300)), nullable=False),
        sa.Column("location", _geom("POINT"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        _jsonb("vision_result"),
        _now(),
        sa.PrimaryKeyConstraint("id", name="pk_fix_proofs"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], name="fk_fix_proofs_ticket_id_tickets"),
        sa.ForeignKeyConstraint(
            ["official_id"], ["officials.id"], name="fk_fix_proofs_official_id_officials"
        ),
    )
    op.create_index("ix_fix_proofs_ticket_id", "fix_proofs", ["ticket_id"])

    op.create_table(
        "fix_confirmations",
        sa.Column("ticket_id", _uuid(), nullable=False),
        sa.Column("reporter_id", sa.String(40), nullable=False),
        sa.Column("response", sa.String(16), nullable=False),
        _now(),
        sa.PrimaryKeyConstraint("ticket_id", "reporter_id", name="pk_fix_confirmations"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name="fk_fix_confirmations_ticket_id_tickets"
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["reporters.reporter_id"],
            name="fk_fix_confirmations_reporter_id_reporters",
        ),
        sa.CheckConstraint(_in("response", FIX_RESPONSES), name="ck_fix_confirmations_response"),
    )


def downgrade() -> None:
    for table in (
        "fix_confirmations",
        "fix_proofs",
        "ticket_events",
        "reports",
        "tickets",
        "reporters",
        "officials",
        "sla_rules",
        "tenants",
        "categories",
        "road_segments",
        "authorities",
        "jurisdictions",
    ):
        op.drop_table(table)
