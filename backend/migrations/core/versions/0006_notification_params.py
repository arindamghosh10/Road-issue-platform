"""Translatable notifications: values for the app's own (Hindi/Bengali/English) text.

Revision ID: 0006_core
Revises: 0005_core
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_core"
down_revision = "0005_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column(
        "params", postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"), nullable=False,
    ))


def downgrade() -> None:
    op.drop_column("notifications", "params")
