"""Performance: SLA-breach flag on tickets, geography index for distance checks.

Revision ID: 0005_core
Revises: 0004_core
Create Date: 2026-09-29

Found by the load test (docs/load-test.md):
* dashboards looked up each ticket's event history to see if it ever missed a deadline;
  a flag set at breach time turns that into a column read;
* distance checks in metres (clustering, nearby, fix-proof distance) cast location to
  geography, which the existing geometry index can't serve.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_core"
down_revision = "0004_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("sla_breached", sa.Boolean(), server_default=sa.text("false"),
                                       nullable=False))
    op.execute("""
        UPDATE tickets t SET sla_breached = true
        WHERE EXISTS (SELECT 1 FROM ticket_events e
                      WHERE e.ticket_id = t.id AND e.type = 'escalated'
                        AND e.payload->>'reason' LIKE 'SLA breached%')
    """)
    op.execute("CREATE INDEX ix_tickets_location_geog ON tickets USING gist ((location::geography))")


def downgrade() -> None:
    op.drop_index("ix_tickets_location_geog", table_name="tickets")
    op.drop_column("tickets", "sla_breached")
