"""Admin API for onboarding: officials, deadlines, areas, organisations (tenants).

Two kinds of administrator:

* platform admin (the RoadWatch operator) — everything: create organisations, import
  ward/municipality boundaries, manage any official, moderation and audit (admin.py);
* government admin (role gov_admin) — their own organisation only: add and manage
  officials inside it, and set its deadlines. Anything outside it reads as "not found".

New accounts get a temporary password, shown once to the admin who created it; the
official must choose their own before doing anything else. Every change is written to
the audit log. Nothing here touches citizens or the identity vault.
"""

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, aliased

from app import audit
from app.api.deps import current_official
from app.db import get_core_db
from app.models.core import (
    Authority,
    AuthorityType,
    Category,
    Jurisdiction,
    JurisdictionLevel,
    Official,
    OfficialRole,
    SlaRule,
    Tenant,
)
from app.security.passwords import hash_password
from app.security.ratelimit import client_ip, enforce

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

MAX_IMPORT_MB = 25
MAX_DEADLINE_HOURS = 24 * 365


# --- Who is asking, and what they may touch -------------------------------------------


@dataclass
class AdminScope:
    official: Official
    tenant: Tenant | None  # None: platform admin, everything is in scope

    @property
    def platform(self) -> bool:
        return self.tenant is None


def current_admin(request: Request, official: Official = Depends(current_official),
                  db: Session = Depends(get_core_db)) -> AdminScope:
    if official.role == OfficialRole.PLATFORM_ADMIN.value:
        scope = AdminScope(official, None)
    elif official.role == OfficialRole.GOV_ADMIN.value:
        tenant = db.get(Tenant, official.tenant_id) if official.tenant_id else None
        if tenant is None:
            raise HTTPException(403, "This administrator account isn't linked to an organisation.")
        scope = AdminScope(official, tenant)
    else:
        raise HTTPException(403, "Administrators only.")
    if request.method != "GET":
        enforce("admin_write_hour", str(official.id), actor_type="official", actor_id=str(official.id),
                ip=client_ip(request))
    return scope


def _platform_only(scope: AdminScope) -> None:
    if not scope.platform:
        raise HTTPException(403, "Only the platform administrator can do this.")


def _node(db: Session, scope: AdminScope, node_id: int) -> Jurisdiction:
    """An area the admin may use; outside their organisation it doesn't exist for them."""
    node = db.get(Jurisdiction, node_id)
    if node is None or (not scope.platform and scope.tenant.root_node_id not in node.path):
        raise HTTPException(404, "Area not found.")
    return node


def _tenant(db: Session, scope: AdminScope, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None or (not scope.platform and tenant.id != scope.tenant.id):
        raise HTTPException(404, "Organisation not found.")
    return tenant


def _official(db: Session, scope: AdminScope, official_id: uuid.UUID) -> Official:
    o = db.get(Official, official_id)
    if o is None or (not scope.platform and o.tenant_id != scope.tenant.id):
        raise HTTPException(404, "Official not found.")
    return o


def _authority(db: Session, scope: AdminScope, authority_id: int) -> Authority:
    a = db.get(Authority, authority_id)
    if a is None:
        raise HTTPException(404, "Road authority not found.")
    if not scope.platform:
        node = db.get(Jurisdiction, a.jurisdiction_id) if a.jurisdiction_id else None
        if node is None or scope.tenant.root_node_id not in node.path:
            raise HTTPException(404, "Road authority not found.")
    return a


def _audit(scope: AdminScope, request: Request, action: str, target: str, **details) -> None:
    audit.record(action, actor_type="official", actor_id=str(scope.official.id), target=target[:128],
                 ip=client_ip(request), details=details)


def _temporary_password() -> str:
    return secrets.token_urlsafe(12)  # 16 characters, ~96 bits


# --- Organisations (tenants) ----------------------------------------------------------


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    root_node_id: int
    root_node: str
    root_level: str
    officials: int


class TenantIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    root_node_id: int


def _tenant_rows(db: Session, where) -> list[TenantOut]:
    counts = (select(Official.tenant_id, func.count().label("n")).group_by(Official.tenant_id).subquery())
    rows = db.execute(
        select(Tenant, Jurisdiction.name, Jurisdiction.level, func.coalesce(counts.c.n, 0))
        .join(Jurisdiction, Jurisdiction.id == Tenant.root_node_id)
        .outerjoin(counts, counts.c.tenant_id == Tenant.id)
        .where(where).order_by(Tenant.name)
    ).all()
    return [TenantOut(id=t.id, name=t.name, root_node_id=t.root_node_id, root_node=name, root_level=level,
                      officials=n) for t, name, level, n in rows]


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(scope: AdminScope = Depends(current_admin), db: Session = Depends(get_core_db)):
    return _tenant_rows(db, Tenant.id.is_not(None) if scope.platform else Tenant.id == scope.tenant.id)


@router.post("/tenants", response_model=TenantOut, status_code=201)
def create_tenant(body: TenantIn, request: Request, scope: AdminScope = Depends(current_admin),
                  db: Session = Depends(get_core_db)):
    """A government client (e.g. a municipal corporation) that sees everything under one area."""
    _platform_only(scope)
    node = _node(db, scope, body.root_node_id)
    if db.scalar(select(Tenant.id).where(Tenant.root_node_id == node.id)):
        raise HTTPException(409, "An organisation already covers exactly this area.")
    tenant = Tenant(name=body.name.strip(), root_node_id=node.id, config={})
    db.add(tenant)
    db.commit()
    _audit(scope, request, "tenant_created", f"tenant:{tenant.id}", name=tenant.name, area=node.name)
    return _tenant_rows(db, Tenant.id == tenant.id)[0]


# --- Deadlines (SLA hours per category and severity) -------------------------------------


class DeadlineRow(BaseModel):
    category: str
    name: str
    severity: int
    default_hours: int
    hours: int | None  # this organisation's override; None = the default applies


class DeadlineChange(BaseModel):
    category: str
    severity: int = Field(ge=1, le=5)
    hours: int | None = Field(None, ge=1, le=MAX_DEADLINE_HOURS)  # None: back to the default


class DeadlinesIn(BaseModel):
    changes: list[DeadlineChange] = Field(max_length=200)


def _deadline_rows(db: Session, tenant: Tenant) -> list[DeadlineRow]:
    overrides = {(c, s): h for c, s, h in db.execute(
        select(SlaRule.category_id, SlaRule.severity, SlaRule.hours).where(SlaRule.tenant_id == tenant.id))}
    rows = []
    for cat in db.scalars(select(Category).order_by(Category.id)):
        for sev in range(1, 6):
            rows.append(DeadlineRow(category=cat.code, name=cat.name, severity=sev,
                                    default_hours=int(cat.default_sla_hours[str(sev)]),
                                    hours=overrides.get((cat.id, sev))))
    return rows


@router.get("/tenants/{tenant_id}/deadlines", response_model=list[DeadlineRow])
def get_deadlines(tenant_id: uuid.UUID, scope: AdminScope = Depends(current_admin),
                  db: Session = Depends(get_core_db)):
    return _deadline_rows(db, _tenant(db, scope, tenant_id))


@router.put("/tenants/{tenant_id}/deadlines", response_model=list[DeadlineRow])
def set_deadlines(tenant_id: uuid.UUID, body: DeadlinesIn, request: Request,
                  scope: AdminScope = Depends(current_admin), db: Session = Depends(get_core_db)):
    """Change how long tickets may stay unresolved before they escalate. Applies to new
    tickets and to each ticket's next deadline (e.g. after an escalation)."""
    tenant = _tenant(db, scope, tenant_id)
    categories = {c.code: c for c in db.scalars(select(Category))}
    latest = {(ch.category, ch.severity): ch for ch in body.changes}  # last change per cell wins
    for ch in latest.values():
        cat = categories.get(ch.category)
        if cat is None:
            raise HTTPException(422, f"Unknown category: {ch.category}")
        rule = db.get(SlaRule, (tenant.id, cat.id, ch.severity))
        if ch.hours is None:
            if rule is not None:
                db.delete(rule)
        elif rule is None:
            db.add(SlaRule(tenant_id=tenant.id, category_id=cat.id, severity=ch.severity, hours=ch.hours))
        else:
            rule.hours = ch.hours
    db.commit()
    _audit(scope, request, "deadlines_changed", f"tenant:{tenant.id}",
           changes=[c.model_dump() for c in body.changes][:50])
    return _deadline_rows(db, tenant)


# --- Areas (jurisdictions) ----------------------------------------------------------


class AreaOut(BaseModel):
    id: int
    name: str
    level: str
    lgd_code: str
    parent_id: int | None
    is_sample: bool
    has_boundary: bool
    children: int
    tenant: str | None  # organisation rooted exactly here, if any


@router.get("/areas", response_model=list[AreaOut])
def list_areas(parent_id: int | None = None, scope: AdminScope = Depends(current_admin),
               db: Session = Depends(get_core_db)):
    """Browse the area tree one level at a time. Without parent_id: the top level the
    admin can see (every state for the platform, the organisation's own area otherwise)."""
    child = aliased(Jurisdiction)
    query = (
        select(Jurisdiction, (Jurisdiction.geom.is_not(None)).label("has_geom"),
               select(func.count()).where(child.parent_id == Jurisdiction.id).scalar_subquery(),
               Tenant.name)
        .outerjoin(Tenant, Tenant.root_node_id == Jurisdiction.id)
        .order_by(Jurisdiction.name)
    )
    if parent_id is not None:
        query = query.where(Jurisdiction.parent_id == _node(db, scope, parent_id).id)
    elif scope.platform:
        query = query.where(Jurisdiction.parent_id.is_(None))
    else:
        query = query.where(Jurisdiction.id == scope.tenant.root_node_id)
    return [AreaOut(id=j.id, name=j.name, level=j.level, lgd_code=j.lgd_code, parent_id=j.parent_id,
                    is_sample=j.is_sample, has_boundary=bool(has_geom), children=n, tenant=tenant)
            for j, has_geom, n, tenant in db.execute(query)]


class ImportOut(BaseModel):
    created: int
    updated: int
    areas: list[dict]


LEVELS = {lv.value for lv in JurisdictionLevel}


def _check_coords(coords) -> bool:
    """Every position is [lon, lat] in degrees (catches files in a projected CRS)."""
    if coords and isinstance(coords[0], (int, float)):
        return len(coords) >= 2 and -180 <= coords[0] <= 180 and -90 <= coords[1] <= 90
    return all(_check_coords(c) for c in coords)


@router.post("/areas/import", response_model=ImportOut)
async def import_areas(request: Request, file: UploadFile = File(...),
                       scope: AdminScope = Depends(current_admin), db: Session = Depends(get_core_db)):
    """Add or update areas (state, district, municipality, ward…) from a GeoJSON file.

    Each feature: a Polygon/MultiPolygon in WGS84 (longitude, latitude) with properties
    `name`, `lgd_code` (official LGD code, unique), `level`, and `parent_lgd_code` (an
    existing area or one earlier in the same file; omit only for a state). Existing
    areas (same lgd_code) get the new name and boundary. Nothing is saved unless every
    feature is valid. Reports are placed using the new boundaries from then on;
    existing tickets keep their area.
    """
    _platform_only(scope)
    raw = await file.read(MAX_IMPORT_MB * 1024 * 1024 + 1)
    if len(raw) > MAX_IMPORT_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {MAX_IMPORT_MB} MB.")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, "Not a valid GeoJSON file.") from None
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list) or not features:
        raise HTTPException(422, "Expected a GeoJSON FeatureCollection with at least one feature.")

    errors: list[str] = []
    specs: list[dict] = []
    seen: set[str] = set()
    for i, f in enumerate(features, start=1):
        props = (f or {}).get("properties") or {}
        geom = (f or {}).get("geometry") or {}
        name, code = str(props.get("name") or "").strip(), str(props.get("lgd_code") or "").strip()
        level, parent = str(props.get("level") or "").strip(), str(props.get("parent_lgd_code") or "").strip()
        where = f"Feature {i}" + (f" ({code})" if code else "")
        if not name or len(name) > 200:
            errors.append(f"{where}: 'name' is missing or longer than 200 characters.")
        if not code or len(code) > 32:
            errors.append(f"{where}: 'lgd_code' is missing or longer than 32 characters.")
        elif code in seen:
            errors.append(f"{where}: lgd_code appears twice in the file.")
        seen.add(code)
        if level not in LEVELS:
            errors.append(f"{where}: 'level' must be one of {', '.join(sorted(LEVELS))}.")
        if geom.get("type") not in ("Polygon", "MultiPolygon"):
            errors.append(f"{where}: geometry must be a Polygon or MultiPolygon.")
        elif not _check_coords(geom.get("coordinates") or []):
            errors.append(f"{where}: coordinates must be longitude/latitude in degrees (WGS84).")
        specs.append({"name": name, "code": code, "level": level, "parent": parent, "geom": geom})

    existing = {j.lgd_code: j for j in db.scalars(select(Jurisdiction).where(
        Jurisdiction.lgd_code.in_([s["code"] for s in specs] + [s["parent"] for s in specs if s["parent"]])))}
    in_file = {s["code"] for s in specs}
    for s in specs:
        if not s["parent"] and s["level"] != JurisdictionLevel.STATE.value:
            errors.append(f"{s['code']}: only a state may have no parent_lgd_code.")
        if s["parent"] and s["parent"] not in existing and s["parent"] not in in_file:
            errors.append(f"{s['code']}: parent '{s['parent']}' is neither an existing area nor in this file.")
        old = existing.get(s["code"])
        if old is not None and s["parent"]:
            old_parent = db.get(Jurisdiction, old.parent_id) if old.parent_id else None
            if (old_parent.lgd_code if old_parent else "") != s["parent"]:
                errors.append(f"{s['code']}: moving an existing area to a different parent isn't supported.")
    if errors:
        raise HTTPException(422, {"message": "Nothing was imported. Fix these and upload again.",
                                  "errors": errors[:100]})

    # Parents before children: repeatedly take the specs whose parent is already known.
    pending, done, created, updated, out = list(specs), dict(existing), 0, 0, []
    while pending:
        ready = [s for s in pending if not s["parent"] or s["parent"] in done]
        if not ready:
            raise HTTPException(422, {"message": "Nothing was imported.", "errors": ["The parent links form a loop."]})
        for s in ready:
            pending.remove(s)
            node = existing.get(s["code"])
            parent = done.get(s["parent"]) if s["parent"] else None
            if node is None:
                node = Jurisdiction(lgd_code=s["code"], name=s["name"], level=s["level"],
                                    parent_id=parent.id if parent else None, is_sample=False)
                db.add(node)
                db.flush()
                node.path = [*(parent.path if parent else []), node.id]
                created += 1
            else:
                node.name, node.level, node.is_sample = s["name"], s["level"], False
                updated += 1
            db.flush()
            db.execute(text(
                "UPDATE jurisdictions SET geom = ST_Multi(ST_CollectionExtract("
                "ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:g), 4326)), 3)) WHERE id = :id"
            ), {"g": json.dumps(s["geom"]), "id": node.id})
            done[s["code"]] = node
            out.append({"id": node.id, "lgd_code": node.lgd_code, "name": node.name, "level": node.level})
    db.commit()
    _audit(scope, request, "areas_imported", file.filename or "geojson", created=created, updated=updated)
    return ImportOut(created=created, updated=updated, areas=out)


# --- Road authorities ---------------------------------------------------------------


class AuthorityOut(BaseModel):
    id: int
    name: str
    type: str
    jurisdiction_id: int | None
    area: str | None


class AuthorityIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    type: AuthorityType
    jurisdiction_id: int


@router.get("/authorities", response_model=list[AuthorityOut])
def list_authorities(scope: AdminScope = Depends(current_admin), db: Session = Depends(get_core_db)):
    query = (select(Authority, Jurisdiction.name, Jurisdiction.path)
             .outerjoin(Jurisdiction, Jurisdiction.id == Authority.jurisdiction_id).order_by(Authority.name))
    rows = db.execute(query).all()
    return [AuthorityOut(id=a.id, name=a.name, type=a.type, jurisdiction_id=a.jurisdiction_id, area=area)
            for a, area, path in rows
            if scope.platform or (path is not None and scope.tenant.root_node_id in path)]


@router.post("/authorities", response_model=AuthorityOut, status_code=201)
def create_authority(body: AuthorityIn, request: Request, scope: AdminScope = Depends(current_admin),
                     db: Session = Depends(get_core_db)):
    """A road-owning body (municipal roads department, State PWD, NHAI regional office…)."""
    _platform_only(scope)
    node = _node(db, scope, body.jurisdiction_id)
    a = Authority(name=body.name.strip(), type=body.type.value, jurisdiction_id=node.id)
    db.add(a)
    db.commit()
    _audit(scope, request, "authority_created", f"authority:{a.id}", name=a.name, type=a.type)
    return AuthorityOut(id=a.id, name=a.name, type=a.type, jurisdiction_id=node.id, area=node.name)


# --- Officials ----------------------------------------------------------------------


class OfficialRow(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    tenant_id: uuid.UUID | None
    tenant: str | None
    node_id: int | None
    node: str | None
    node_level: str | None
    authority_id: int | None
    authority: str | None
    is_active: bool
    totp_enabled: bool
    must_change_password: bool
    created_on: date


class OfficialIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str = Field(max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: OfficialRole = OfficialRole.OFFICIAL
    tenant_id: uuid.UUID | None = None
    node_id: int | None = None
    authority_id: int | None = None


class OfficialPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    role: OfficialRole | None = None
    node_id: int | None = None
    authority_id: int | None = None
    clear_node: bool = False
    clear_authority: bool = False
    is_active: bool | None = None


class CreatedOfficial(BaseModel):
    official: OfficialRow
    temporary_password: str  # shown once; the official must change it at first sign-in


class PasswordReset(BaseModel):
    temporary_password: str


def _official_rows(db: Session, where) -> list[OfficialRow]:
    rows = db.execute(
        select(Official, Tenant.name, Jurisdiction.name, Jurisdiction.level, Authority.name)
        .outerjoin(Tenant, Tenant.id == Official.tenant_id)
        .outerjoin(Jurisdiction, Jurisdiction.id == Official.node_id)
        .outerjoin(Authority, Authority.id == Official.authority_id)
        .where(where).order_by(Official.is_active.desc(), Official.name)
    ).all()
    return [OfficialRow(
        id=o.id, name=o.name, email=o.email, role=o.role, tenant_id=o.tenant_id, tenant=tenant,
        node_id=o.node_id, node=node, node_level=level, authority_id=o.authority_id, authority=auth,
        is_active=o.is_active, totp_enabled=o.totp_enabled, must_change_password=o.must_change_password,
        created_on=o.created_at.date(),
    ) for o, tenant, node, level, auth in rows]


def _check_placement(db: Session, scope: AdminScope, role: OfficialRole, tenant: Tenant | None,
                     node_id: int | None, authority_id: int | None) -> None:
    """Where an official sits decides which tickets they see; reject combinations that
    would give them nothing, or something outside their organisation."""
    if role == OfficialRole.PLATFORM_ADMIN:
        _platform_only(scope)
        if tenant or node_id or authority_id:
            raise HTTPException(422, "A platform administrator isn't part of an organisation or area.")
        return
    if tenant is None:
        raise HTTPException(422, "Choose the organisation this official belongs to.")
    if node_id is not None:
        node = _node(db, scope, node_id)
        if tenant.root_node_id not in node.path:
            raise HTTPException(422, "The area must be inside the organisation's area.")
    if authority_id is not None:
        _authority(db, scope, authority_id)
    if role == OfficialRole.OFFICIAL and node_id is None and authority_id is None:
        raise HTTPException(422, "Choose the area (or road authority) this official works for.")


@router.get("/officials", response_model=list[OfficialRow])
def list_officials(tenant_id: uuid.UUID | None = None, scope: AdminScope = Depends(current_admin),
                   db: Session = Depends(get_core_db)):
    if not scope.platform:
        return _official_rows(db, Official.tenant_id == scope.tenant.id)
    if tenant_id is not None:
        return _official_rows(db, Official.tenant_id == _tenant(db, scope, tenant_id).id)
    return _official_rows(db, Official.id.is_not(None))


@router.post("/officials", response_model=CreatedOfficial, status_code=201)
def create_official(body: OfficialIn, request: Request, scope: AdminScope = Depends(current_admin),
                    db: Session = Depends(get_core_db)):
    email = body.email.strip().lower()
    if db.scalar(select(Official.id).where(Official.email == email)):
        raise HTTPException(409, "An account with this email already exists.")
    tenant = scope.tenant if not scope.platform else (
        _tenant(db, scope, body.tenant_id) if body.tenant_id else None)
    _check_placement(db, scope, body.role, tenant, body.node_id, body.authority_id)
    password = _temporary_password()
    o = Official(name=body.name.strip(), email=email, role=body.role.value,
                 tenant_id=tenant.id if tenant else None, node_id=body.node_id,
                 authority_id=body.authority_id, password_hash=hash_password(password),
                 must_change_password=True)
    db.add(o)
    db.commit()
    _audit(scope, request, "official_created", f"official:{o.id}", email=email, role=o.role)
    return CreatedOfficial(official=_official_rows(db, Official.id == o.id)[0], temporary_password=password)


@router.patch("/officials/{official_id}", response_model=OfficialRow)
def update_official(official_id: uuid.UUID, body: OfficialPatch, request: Request,
                    scope: AdminScope = Depends(current_admin), db: Session = Depends(get_core_db)):
    o = _official(db, scope, official_id)
    if o.id == scope.official.id and (body.role is not None or body.is_active is False):
        raise HTTPException(422, "You can't change your own role or deactivate yourself.")
    role = body.role or OfficialRole(o.role)
    node_id = None if body.clear_node else (body.node_id if body.node_id is not None else o.node_id)
    authority_id = None if body.clear_authority else (
        body.authority_id if body.authority_id is not None else o.authority_id)
    tenant = db.get(Tenant, o.tenant_id) if o.tenant_id else None
    if o.role == OfficialRole.PLATFORM_ADMIN.value or role == OfficialRole.PLATFORM_ADMIN:
        _platform_only(scope)
    _check_placement(db, scope, role, tenant, node_id, authority_id)
    changes = body.model_dump(exclude_none=True)
    o.role, o.node_id, o.authority_id = role.value, node_id, authority_id
    if body.name:
        o.name = body.name.strip()
    if body.is_active is not None and body.is_active != o.is_active:
        o.is_active = body.is_active
        o.token_version += 1  # deactivating signs them out everywhere
    db.commit()
    _audit(scope, request, "official_updated", f"official:{o.id}", changes=changes)
    return _official_rows(db, Official.id == o.id)[0]


@router.post("/officials/{official_id}/reset-password", response_model=PasswordReset)
def reset_password(official_id: uuid.UUID, request: Request, scope: AdminScope = Depends(current_admin),
                   db: Session = Depends(get_core_db)):
    """New temporary password (shown once); signs the official out everywhere."""
    o = _official(db, scope, official_id)
    if o.id == scope.official.id:
        raise HTTPException(422, "Change your own password from your account page instead.")
    if o.role == OfficialRole.PLATFORM_ADMIN.value:
        _platform_only(scope)
    password = _temporary_password()
    o.password_hash, o.must_change_password = hash_password(password), True
    o.token_version += 1
    db.commit()
    _audit(scope, request, "password_reset", f"official:{o.id}")
    return PasswordReset(temporary_password=password)


@router.post("/officials/{official_id}/reset-2fa", response_model=OfficialRow)
def reset_two_factor(official_id: uuid.UUID, request: Request, scope: AdminScope = Depends(current_admin),
                     db: Session = Depends(get_core_db)):
    """For a lost phone: turns two-factor off so the official can sign in and set it up again."""
    o = _official(db, scope, official_id)
    if o.role == OfficialRole.PLATFORM_ADMIN.value:
        _platform_only(scope)
    o.totp_enabled, o.totp_secret = False, None
    o.token_version += 1
    db.commit()
    _audit(scope, request, "two_factor_reset", f"official:{o.id}")
    return _official_rows(db, Official.id == o.id)[0]
