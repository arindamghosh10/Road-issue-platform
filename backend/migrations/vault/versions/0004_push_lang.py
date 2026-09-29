"""Push tokens remember the app language, so pushes arrive in Hindi, Bengali or English.

Revision ID: 0004_vault
Revises: 0003_vault
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_vault"
down_revision = "0003_vault"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("push_tokens", sa.Column("lang", sa.String(5), server_default="en", nullable=False))


def downgrade() -> None:
    op.drop_column("push_tokens", "lang")
