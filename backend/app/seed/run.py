"""Seed the core database with SAMPLE pilot data for Kolkata / West Bengal.

Usage (inside the api container, or locally with the DBs running):
    python -m app.seed            # seed if empty
    python -m app.seed --reset    # wipe core tables and re-seed (DEV ONLY)

Creates: the jurisdiction tree (state → districts → municipalities → wards), road
authorities, sample road segments, issue categories, a demo tenant with SLA rules, and
demo officials at every level. Nothing is written to the identity vault: citizens only
enter the vault by signing up through OTP (Phase 1).
"""

import argparse
import sys

from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import core_session
from app.models.core import (
    Authority,
    AuthorityType,
    Category,
    Jurisdiction,
    JurisdictionLevel,
    Official,
    RoadSegment,
    SlaRule,
    Tenant,
)
from app.security.passwords import hash_password
from app.seed import data, sample_geo

CORE_TABLES = (
    "fix_confirmations", "fix_proofs", "ticket_events", "reports", "tickets", "reporters",
    "officials", "sla_rules", "tenants", "categories", "road_segments", "authorities",
    "jurisdictions",
)

DISTRICT_SAMPLE_BBOX = {
    "Kolkata": sample_geo.KOLKATA_DISTRICT_BBOX,
    "Howrah": sample_geo.HOWRAH_DISTRICT_BBOX,
    "North 24 Parganas": sample_geo.NORTH_24_PGS_BBOX,
    "South 24 Parganas": sample_geo.SOUTH_24_PGS_BBOX,
}


def _code(name: str) -> str:
    return name.upper().replace(" ", "-")


def _add_node(
    db: Session,
    *,
    lgd_code: str,
    name: str,
    level: JurisdictionLevel,
    parent: Jurisdiction | None,
    geom: MultiPolygon | None,
) -> Jurisdiction:
    node = Jurisdiction(
        lgd_code=lgd_code,
        name=name,
        level=level.value,
        parent_id=parent.id if parent else None,
        geom=from_shape(geom, srid=4326) if geom is not None else None,
        is_sample=True,
    )
    db.add(node)
    db.flush()  # assigns node.id so we can build the materialised path
    node.path = [*(parent.path if parent else []), node.id]
    return node


def seed_jurisdictions(db: Session) -> dict[str, Jurisdiction]:
    nodes: dict[str, Jurisdiction] = {}
    wb = _add_node(
        db, lgd_code="SAMPLE-ST-WB", name="West Bengal", level=JurisdictionLevel.STATE,
        parent=None, geom=sample_geo.multipolygon(sample_geo.WEST_BENGAL_BBOX),
    )
    nodes[wb.lgd_code] = wb

    for district in data.WEST_BENGAL_DISTRICTS:
        bbox = DISTRICT_SAMPLE_BBOX.get(district)
        node = _add_node(
            db, lgd_code=f"SAMPLE-DT-{_code(district)}", name=district,
            level=JurisdictionLevel.DISTRICT, parent=wb,
            geom=sample_geo.multipolygon(bbox) if bbox else None,
        )
        nodes[node.lgd_code] = node

    kmc = _add_node(
        db, lgd_code="SAMPLE-ULB-KMC", name="Kolkata Municipal Corporation",
        level=JurisdictionLevel.MUNICIPALITY, parent=nodes["SAMPLE-DT-KOLKATA"],
        geom=sample_geo.multipolygon(sample_geo.KMC_BBOX),
    )
    nodes[kmc.lgd_code] = kmc
    for i, cell in enumerate(sample_geo.kmc_ward_polygons(), start=1):
        ward = _add_node(
            db, lgd_code=f"SAMPLE-KMC-W{i:03d}", name=f"KMC Ward {i}",
            level=JurisdictionLevel.WARD, parent=kmc, geom=MultiPolygon([cell]),
        )
        nodes[ward.lgd_code] = ward

    hmc = _add_node(
        db, lgd_code="SAMPLE-ULB-HMC", name="Howrah Municipal Corporation",
        level=JurisdictionLevel.MUNICIPALITY, parent=nodes["SAMPLE-DT-HOWRAH"],
        geom=sample_geo.multipolygon(sample_geo.HMC_BBOX),
    )
    nodes[hmc.lgd_code] = hmc
    for i, cell in enumerate(sample_geo.hmc_ward_polygons(), start=1):
        ward = _add_node(
            db, lgd_code=f"SAMPLE-HMC-W{i:03d}", name=f"HMC Ward {i}",
            level=JurisdictionLevel.WARD, parent=hmc, geom=MultiPolygon([cell]),
        )
        nodes[ward.lgd_code] = ward
    return nodes


def seed_authorities(db: Session, nodes: dict[str, Jurisdiction]) -> dict[str, Authority]:
    specs = {
        "kmc": ("KMC Roads Department (sample)", AuthorityType.MUNICIPAL, "SAMPLE-ULB-KMC"),
        "hmc": ("HMC Roads Department (sample)", AuthorityType.MUNICIPAL, "SAMPLE-ULB-HMC"),
        "state_pwd": ("West Bengal PWD (sample)", AuthorityType.STATE_PWD, "SAMPLE-ST-WB"),
        "nhai": ("NHAI Regional Office Kolkata (sample)", AuthorityType.NHAI, "SAMPLE-ST-WB"),
    }
    authorities = {}
    for key, (name, type_, node_code) in specs.items():
        authority = Authority(name=name, type=type_.value, jurisdiction_id=nodes[node_code].id)
        db.add(authority)
        authorities[key] = authority
    db.flush()
    return authorities


def seed_roads(db: Session, authorities: dict[str, Authority]) -> None:
    for road in sample_geo.SAMPLE_ROADS:
        db.add(
            RoadSegment(
                name=road["name"],
                road_class=road["road_class"],
                is_bridge=road["is_bridge"],
                authority_id=authorities[road["authority"]].id,
                geom=from_shape(sample_geo.road_line(road["coords"]), srid=4326),
                is_sample=True,
            )
        )


def seed_categories(db: Session) -> list[Category]:
    categories = [
        Category(code=c["code"], name=c["name"], default_sla_hours=c["sla"],
                 cluster_radius_m=c["radius"])
        for c in data.CATEGORIES
    ]
    db.add_all(categories)
    db.flush()
    return categories


def seed_tenant(
    db: Session,
    nodes: dict[str, Jurisdiction],
    authorities: dict[str, Authority],
    categories: list[Category],
) -> Tenant:
    tenant = Tenant(
        name="West Bengal Demo Tenant (sample)",
        root_node_id=nodes["SAMPLE-ST-WB"].id,
        config={"close_rule": {"min_confirm_ratio": 0.5, "no_dispute_days": 7},
                "fix_proof_max_distance_m": 50, "sla_warning_ratio": 0.8},
    )
    db.add(tenant)
    db.flush()
    for category in categories:
        for severity, hours in category.default_sla_hours.items():
            db.add(SlaRule(tenant_id=tenant.id, category_id=category.id,
                           severity=int(severity), hours=hours))
    password_hash = hash_password(data.DEMO_PASSWORD)
    for spec in data.DEMO_OFFICIALS:
        authority = authorities.get(spec.get("authority", ""))
        db.add(
            Official(
                tenant_id=tenant.id, name=spec["name"], email=spec["email"],
                password_hash=password_hash, role=spec["role"],
                node_id=nodes[spec["node"]].id,
                authority_id=authority.id if authority else None,
            )
        )
    return tenant


def ensure_platform_admin(db: Session) -> None:
    """Idempotent: also adds the platform admin to databases seeded before Phase 5."""
    spec = data.PLATFORM_ADMIN
    if db.scalar(select(Official.id).where(Official.email == spec["email"])) is None:
        db.add(Official(tenant_id=None, name=spec["name"], email=spec["email"],
                        password_hash=hash_password(data.DEMO_PASSWORD), role=spec["role"]))


def run(reset: bool = False) -> None:
    with core_session() as db:
        if reset:
            if get_settings().app_env == "prod":
                sys.exit("Refusing to --reset in prod.")
            db.execute(text(f"TRUNCATE {', '.join(CORE_TABLES)} RESTART IDENTITY CASCADE"))
        elif db.scalar(select(Jurisdiction.id).limit(1)) is not None:
            ensure_platform_admin(db)
            db.commit()
            print("Core DB already seeded; use --reset to wipe and re-seed.")
            return

        nodes = seed_jurisdictions(db)
        authorities = seed_authorities(db, nodes)
        seed_roads(db, authorities)
        categories = seed_categories(db)
        seed_tenant(db, nodes, authorities, categories)
        ensure_platform_admin(db)
        db.commit()

    print(f"Seeded {len(nodes)} jurisdictions (SAMPLE data), {len(authorities)} authorities, "
          f"{len(sample_geo.SAMPLE_ROADS)} road segments, {len(categories)} categories, "
          f"{len(data.DEMO_OFFICIALS)} demo officials.")
    print(f"Demo official password (dev only): {data.DEMO_PASSWORD}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="wipe core tables first (dev only)")
    run(reset=parser.parse_args().reset)
