"""Official accounts managed by admins: forced password change, session sign-out.

Revision ID: 0007_core
Revises: 0006_core
Create Date: 2026-10-12
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_core"
down_revision = "0006_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("officials", sa.Column("must_change_password", sa.Boolean(),
                                         server_default=sa.text("false"), nullable=False))
    op.add_column("officials", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("officials", "token_version")
    op.drop_column("officials", "must_change_password")
