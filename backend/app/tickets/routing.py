"""Routing: which government bodies are responsible for a point on the map?

Two independent answers, both from PostGIS spatial queries:
1. Jurisdiction path — the smallest boundary polygon containing the point (usually a
   ward) and all its ancestors: ward → municipality → district → state. Officials at any
   of those levels will see the ticket.
2. Road authority — the nearest mapped road segment within a few metres tells us who
   owns the road (NHAI, State PWD, municipal roads dept…). If no road is mapped nearby
   we fall back to the municipal roads authority of the containing municipality.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

AUTHORITY_SNAP_M = 30.0  # a report this close to a road segment belongs to that road


@dataclass
class Placement:
    jurisdiction_path: list[int]  # root (state) … lowest node (ward), inclusive
    lowest_node_id: int
    road_segment_id: int | None = None
    road_distance_m: float | None = None
    road_class: str | None = None
    is_bridge: bool = False
    authority_id: int | None = None
    owner_node_id: int | None = None


def point_sql() -> str:
    return "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)"


def nearest_road(db: Session, lon: float, lat: float, max_m: float) -> dict | None:
    row = db.execute(
        text(f"""
            SELECT rs.id, rs.road_class, rs.is_bridge, rs.authority_id,
                   ST_Distance(rs.geom::geography, {point_sql()}::geography) AS dist_m
            FROM road_segments rs
            WHERE ST_DWithin(rs.geom::geography, {point_sql()}::geography, :max_m)
            ORDER BY dist_m
            LIMIT 1
        """),
        {"lon": lon, "lat": lat, "max_m": max_m},
    ).mappings().first()
    return dict(row) if row else None


def locate(db: Session, lon: float, lat: float) -> Placement | None:
    """None if the point is outside every jurisdiction we have boundaries for."""
    node = db.execute(
        text(f"""
            SELECT id, path FROM jurisdictions
            WHERE geom IS NOT NULL AND ST_Covers(geom, {point_sql()})
            ORDER BY cardinality(path) DESC, id
            LIMIT 1
        """),
        {"lon": lon, "lat": lat},
    ).mappings().first()
    if node is None:
        return None

    placement = Placement(jurisdiction_path=list(node["path"]), lowest_node_id=node["id"])
    road = nearest_road(db, lon, lat, AUTHORITY_SNAP_M)
    if road:
        placement.road_segment_id = road["id"]
        placement.road_distance_m = float(road["dist_m"])
        placement.road_class = road["road_class"]
        placement.is_bridge = road["is_bridge"]
        placement.authority_id = road["authority_id"]
    if placement.authority_id is None:
        placement.authority_id = db.scalar(
            text("""
                SELECT id FROM authorities
                WHERE type = 'municipal' AND jurisdiction_id = ANY(:path)
                ORDER BY id LIMIT 1
            """),
            {"path": placement.jurisdiction_path},
        )

    # Primary owner: the road authority's node if known, else the lowest jurisdiction.
    authority_node = None
    if placement.authority_id is not None:
        authority_node = db.scalar(
            text("SELECT jurisdiction_id FROM authorities WHERE id = :id"),
            {"id": placement.authority_id},
        )
    placement.owner_node_id = authority_node or placement.lowest_node_id
    return placement
