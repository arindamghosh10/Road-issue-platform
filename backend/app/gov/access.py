"""Who may see and act on which ticket.

Rule (brief §3): an official attached to node N sees every ticket whose
jurisdiction_path contains N — i.e. N and everything below it. So a ward officer sees
their ward, a municipal engineer sees all wards of the municipality, a state officer
sees the whole state, and an officer of a sibling ward sees nothing of this ward.

Road-authority officials (e.g. NHAI regional office) additionally see every ticket on a
road their authority owns, wherever it is inside their tenant.

Everything is also fenced to the official's tenant: a tenant only ever sees tickets
under its own root node. Platform admins see everything.

The rule is expressed as a SQL condition so filtering happens in the database (with the
GIN index on jurisdiction_path), never by loading tickets and filtering in Python.
"""

from sqlalchemy import ColumnElement, false, or_, select, true
from sqlalchemy.orm import Session

from app.models.core import Official, OfficialRole, Tenant, Ticket


def ticket_scope(db: Session, official: Official) -> ColumnElement[bool]:
    """SQL condition: tickets this official may see."""
    if official.role == OfficialRole.PLATFORM_ADMIN.value:
        return true()
    reach = []
    if official.node_id is not None:
        reach.append(Ticket.jurisdiction_path.any(official.node_id))
    if official.authority_id is not None:
        reach.append(Ticket.authority_id == official.authority_id)
    if not reach:
        return false()
    condition = or_(*reach)
    if official.tenant_id is not None:
        root = db.scalar(select(Tenant.root_node_id).where(Tenant.id == official.tenant_id))
        condition = condition & Ticket.jurisdiction_path.any(root)
    return condition


def can_access(db: Session, official: Official, ticket: Ticket) -> bool:
    return bool(db.scalar(
        select(Ticket.id).where(Ticket.id == ticket.id, ticket_scope(db, official))
    ))


def get_scoped_ticket(db: Session, official: Official, ref: str) -> Ticket | None:
    """The ticket if it exists AND is in scope. Out-of-scope tickets look like 404s, so
    officials cannot even confirm that a ticket outside their area exists."""
    return db.scalar(select(Ticket).where(Ticket.public_ref == ref, ticket_scope(db, official)))
