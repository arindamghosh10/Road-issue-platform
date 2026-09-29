"""Push notification tokens, encrypted, in the vault.

Revision ID: 0003_vault
Revises: 0002_vault
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_vault"
down_revision = "0002_vault"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("token_lookup_hash", sa.String(64), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["identity_id"], ["identities.id"], ondelete="CASCADE",
                                name="fk_push_tokens_identity_id_identities"),
        sa.PrimaryKeyConstraint("id", name="pk_push_tokens"),
        sa.UniqueConstraint("token_lookup_hash", name="uq_push_tokens_token_lookup_hash"),
    )
    op.create_index("ix_push_tokens_identity_id", "push_tokens", ["identity_id"])


def downgrade() -> None:
    op.drop_table("push_tokens")
