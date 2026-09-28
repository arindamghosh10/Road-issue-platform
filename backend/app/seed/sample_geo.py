"""Generated SAMPLE geometries for the Kolkata pilot.

These are NOT real boundaries. Real ward/district polygons (e.g. from DataMeet or the
state GIS portal) can be imported later; until then we generate simple rectangles in
roughly the right places so spatial joins, drill-down and access control can be built
and demoed. Every row created from here has `is_sample = true`.

Bounding boxes are (min_lon, min_lat, max_lon, max_lat) in WGS84.
"""

from shapely.geometry import LineString, MultiPolygon, Polygon, box

# Approximate extents around Kolkata (sample only).
KOLKATA_DISTRICT_BBOX = (88.29, 22.45, 88.42, 22.64)
KMC_BBOX = (88.30, 22.46, 88.41, 22.63)
HOWRAH_DISTRICT_BBOX = (88.10, 22.45, 88.28, 22.70)
HMC_BBOX = (88.24, 22.55, 88.28, 22.61)
NORTH_24_PGS_BBOX = (88.30, 22.65, 88.70, 22.95)
SOUTH_24_PGS_BBOX = (88.20, 22.10, 88.70, 22.44)
WEST_BENGAL_BBOX = (85.80, 21.50, 89.90, 27.30)

KMC_WARD_COUNT = 144  # KMC has 144 wards; the sample grid matches that count.


def multipolygon(bbox: tuple[float, float, float, float]) -> MultiPolygon:
    return MultiPolygon([box(*bbox)])


def grid_cells(bbox: tuple[float, float, float, float], rows: int, cols: int) -> list[Polygon]:
    """Split `bbox` into rows×cols rectangles, numbered north-west to south-east."""
    min_lon, min_lat, max_lon, max_lat = bbox
    dlon = (max_lon - min_lon) / cols
    dlat = (max_lat - min_lat) / rows
    cells = []
    for r in range(rows):
        top = max_lat - r * dlat
        for c in range(cols):
            left = min_lon + c * dlon
            cells.append(box(left, top - dlat, left + dlon, top))
    return cells


def kmc_ward_polygons() -> list[Polygon]:
    return grid_cells(KMC_BBOX, rows=12, cols=12)


def hmc_ward_polygons() -> list[Polygon]:
    return grid_cells(HMC_BBOX, rows=2, cols=2)


# Sample road segments: rough straight-line stand-ins for well-known roads, so the
# "which authority owns this road" logic has something to match against.
SAMPLE_ROADS: list[dict] = [
    {
        "name": "NH-12 / Jessore Road (sample segment)",
        "road_class": "trunk",
        "authority": "nhai",
        "is_bridge": False,
        "coords": [(88.395, 22.625), (88.420, 22.660), (88.445, 22.700)],
    },
    {
        "name": "NH-16 / Kona Expressway (sample segment)",
        "road_class": "trunk",
        "authority": "nhai",
        "is_bridge": False,
        "coords": [(88.290, 22.575), (88.250, 22.580), (88.200, 22.590)],
    },
    {
        "name": "Vidyasagar Setu (sample segment)",
        "road_class": "primary",
        "authority": "state_pwd",
        "is_bridge": True,
        "coords": [(88.324, 22.558), (88.312, 22.560), (88.300, 22.562)],
    },
    {
        "name": "EM Bypass (sample segment)",
        "road_class": "primary",
        "authority": "state_pwd",
        "is_bridge": False,
        "coords": [(88.400, 22.480), (88.400, 22.520), (88.405, 22.560), (88.400, 22.590)],
    },
    {
        "name": "AJC Bose Road (sample segment)",
        "road_class": "secondary",
        "authority": "kmc",
        "is_bridge": False,
        "coords": [(88.345, 22.545), (88.355, 22.540), (88.365, 22.537)],
    },
]


def road_line(coords: list[tuple[float, float]]) -> LineString:
    return LineString(coords)
