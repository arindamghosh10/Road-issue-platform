"""Dashboard statistics, shared by the public and government dashboards.

Every function takes a `scope` SQL condition: `true()` for the public dashboard, the
official's access condition (app/gov/access.py) for the government one. So a ward
officer's numbers can only ever count tickets they are allowed to see.

All figures are aggregates over tickets — nothing here can identify a reporter.

Definitions (shown on the dashboards):
* open           — not resolved (includes acknowledged, in progress, fix submitted, reopened)
* avg resolution — mean hours from ticket creation to resolution, resolved tickets only
* SLA compliance — of tickets whose deadline has been "tested" (resolved, or deadline
                   passed), the share that never missed a deadline
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.core import (
    Authority,
    Category,
    Jurisdiction,
    JurisdictionLevel,
    Ticket,
    TicketEvent,
    TicketStatus,
)
from app.tickets.lifecycle import SLA_ACTIVE

RESOLVED = TicketStatus.RESOLVED.value


# --- Filters ------------------------------------------------------------------------------


def filters(
    db: Session,
    scope: ColumnElement[bool],
    jurisdiction_id: int | None = None,
    category: str | None = None,
    days: int | None = None,
) -> ColumnElement[bool]:
    """Combine the access scope with the dashboard's filter row."""
    conditions = [scope]
    if jurisdiction_id is not None:
        conditions.append(Ticket.jurisdiction_path.any(jurisdiction_id))
    if category:
        category_id = db.scalar(select(Category.id).where(Category.code == category))
        if category_id is None:
            raise HTTPException(422, "Unknown category.")
        conditions.append(Ticket.category_id == category_id)
    if days:
        conditions.append(Ticket.created_at >= datetime.now(UTC) - timedelta(days=days))
    return and_(*conditions)


def _breached() -> ColumnElement[bool]:
    """Ticket ever missed a deadline: an SLA escalation was recorded, or it is overdue now."""
    escalated_for_sla = exists().where(
        TicketEvent.ticket_id == Ticket.id,
        TicketEvent.type == "escalated",
        TicketEvent.payload["reason"].astext.like("SLA breached%"),
    )
    overdue_now = and_(Ticket.status.in_(SLA_ACTIVE), Ticket.sla_due_at < func.now())
    return or_(escalated_for_sla, overdue_now)


def _measures(breached: ColumnElement[bool]):
    resolved = Ticket.status == RESOLVED
    tested = or_(resolved, breached)
    hours = func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 3600
    return [
        func.count().label("total"),
        func.count().filter(~resolved).label("open"),
        func.count().filter(resolved).label("resolved"),
        func.count().filter(breached).label("breaches"),
        func.count().filter(tested).label("sla_tested"),
        func.avg(case((resolved, hours))).label("avg_resolution_hours"),
        func.coalesce(func.sum(Ticket.unique_reporters), 0).label("verified_reporters"),
    ]


class Measures(BaseModel):
    total: int
    open: int
    resolved: int
    breaches: int
    resolution_rate: float | None  # resolved / total, 0..1
    avg_resolution_hours: float | None
    sla_compliance: float | None  # 0..1
    verified_reporters: int


def _to_measures(row) -> Measures:
    return Measures(
        total=row.total,
        open=row.open,
        resolved=row.resolved,
        breaches=row.breaches,
        resolution_rate=round(row.resolved / row.total, 4) if row.total else None,
        avg_resolution_hours=round(float(row.avg_resolution_hours), 1)
        if row.avg_resolution_hours is not None else None,
        sla_compliance=round(1 - row.breaches / row.sla_tested, 4) if row.sla_tested else None,
        verified_reporters=int(row.verified_reporters),
    )


# --- Summary ---------------------------------------------------------------------------------


class Summary(Measures):
    by_status: dict[str, int]


def summary(db: Session, where: ColumnElement[bool]) -> Summary:
    row = db.execute(select(*_measures(_breached())).where(where)).one()
    by_status = dict(db.execute(
        select(Ticket.status, func.count()).where(where).group_by(Ticket.status)
    ).all())
    return Summary(**_to_measures(row).model_dump(),
                   by_status={s.value: by_status.get(s.value, 0) for s in TicketStatus})


# --- Leaderboards / drill-down ----------------------------------------------------------------


class AreaRow(Measures):
    id: int
    name: str
    level: str
    has_children: bool


def areas(
    db: Session,
    where: ColumnElement[bool],
    parent_id: int | None = None,
    level: JurisdictionLevel | None = None,
) -> list[AreaRow]:
    """Per-area figures. `parent_id` → the children of that area (drill-down);
    `level` → every area at that level (e.g. all wards); neither → top-level areas."""
    area = aliased(Jurisdiction)
    query = (
        select(area.id, area.name, area.level, *_measures(_breached()))
        .select_from(Ticket)
        .join(area, Ticket.jurisdiction_path.any(area.id))
        .where(where)
        .group_by(area.id, area.name, area.level)
    )
    if parent_id is not None:
        query = query.where(area.parent_id == parent_id)
    elif level is not None:
        query = query.where(area.level == level.value)
    else:
        query = query.where(area.parent_id.is_(None))
    rows = db.execute(query).all()
    ids = [r.id for r in rows]
    parents_with_children = set(db.scalars(
        select(Jurisdiction.parent_id).where(Jurisdiction.parent_id.in_(ids)).distinct()
    )) if ids else set()
    out = [AreaRow(id=r.id, name=r.name, level=r.level, has_children=r.id in parents_with_children,
                   **_to_measures(r).model_dump()) for r in rows]
    return _rank(out)


class AuthorityRow(Measures):
    id: int
    name: str
    type: str


def authorities(db: Session, where: ColumnElement[bool]) -> list[AuthorityRow]:
    rows = db.execute(
        select(Authority.id, Authority.name, Authority.type, *_measures(_breached()))
        .select_from(Ticket)
        .join(Authority, Authority.id == Ticket.authority_id)
        .where(where)
        .group_by(Authority.id, Authority.name, Authority.type)
    ).all()
    return _rank([AuthorityRow(id=r.id, name=r.name, type=r.type, **_to_measures(r).model_dump())
                  for r in rows])


def _rank(rows: list) -> list:
    """Best first: highest resolution rate, then fewest breaches, then most tickets."""
    return sorted(rows, key=lambda r: (-(r.resolution_rate or 0), r.breaches, -r.total, r.name))


# --- Categories & trends -----------------------------------------------------------------------


class CategoryRow(BaseModel):
    code: str
    name: str
    total: int
    open: int
    resolved: int


def categories(db: Session, where: ColumnElement[bool]) -> list[CategoryRow]:
    resolved = Ticket.status == RESOLVED
    rows = db.execute(
        select(Category.code, Category.name, func.count(),
               func.count().filter(~resolved), func.count().filter(resolved))
        .select_from(Ticket).join(Category, Category.id == Ticket.category_id)
        .where(where).group_by(Category.code, Category.name)
        .order_by(func.count().desc())
    ).all()
    return [CategoryRow(code=c, name=n, total=t, open=o, resolved=r) for c, n, t, o, r in rows]


class TrendPoint(BaseModel):
    week: str  # ISO date of the Monday starting the week
    new: int
    resolved: int


def trends(db: Session, where: ColumnElement[bool], weeks: int = 12) -> list[TrendPoint]:
    """New vs resolved tickets per week, oldest first, zero-filled."""
    today = datetime.now(UTC).date()
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(weeks=weeks - 1)
    # Weeks start on Monday, in UTC regardless of the database's timezone setting.
    week_of = lambda col: func.date_trunc("week", func.timezone("UTC", col))
    def per_week(col) -> dict:
        week = week_of(col)
        rows = db.execute(select(week, func.count()).where(where, col >= start).group_by(week))
        return {k.date(): v for k, v in rows.all()}

    new, resolved = per_week(Ticket.created_at), per_week(Ticket.resolved_at)
    points = []
    for i in range(weeks):
        monday = start + timedelta(weeks=i)
        points.append(TrendPoint(week=monday.isoformat(), new=new.get(monday, 0),
                                 resolved=resolved.get(monday, 0)))
    return points


# --- Government-only: backlog ageing ------------------------------------------------------------


class AgeingBucket(BaseModel):
    bucket: str
    count: int


AGE_BUCKETS = [("< 7 days", 0, 7), ("7–30 days", 7, 30), ("30–90 days", 30, 90), ("90+ days", 90, None)]


def ageing(db: Session, where: ColumnElement[bool]) -> list[AgeingBucket]:
    """Open tickets by how long they have been open."""
    age_days = func.extract("epoch", func.now() - Ticket.created_at) / 86400
    columns = []
    for label, low, high in AGE_BUCKETS:
        cond = age_days >= low if high is None else and_(age_days >= low, age_days < high)
        columns.append(func.count().filter(cond).label(label))
    row = db.execute(select(*columns).where(where, Ticket.status != RESOLVED)).one()
    return [AgeingBucket(bucket=label, count=row[i]) for i, (label, _, _) in enumerate(AGE_BUCKETS)]
