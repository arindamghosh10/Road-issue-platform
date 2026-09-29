"""Initial identity vault schema.

Revision ID: 0001_vault
Revises:
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_vault"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("phone_lookup_hash", sa.String(64), nullable=False),
        sa.Column("identity_hash", sa.String(64), nullable=True),
        sa.Column("verified_level", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("banned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_identities"),
        sa.UniqueConstraint("phone_lookup_hash", name="uq_identities_phone_lookup_hash"),
        sa.UniqueConstraint("identity_hash", name="uq_identities_identity_hash"),
    )
    op.create_table(
        "reporter_links",
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reporter_id", sa.String(40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("identity_id", name="pk_reporter_links"),
        sa.ForeignKeyConstraint(
            ["identity_id"], ["identities.id"], name="fk_reporter_links_identity_id_identities"
        ),
        sa.UniqueConstraint("reporter_id", name="uq_reporter_links_reporter_id"),
    )


def downgrade() -> None:
    op.drop_table("reporter_links")
    op.drop_table("identities")
