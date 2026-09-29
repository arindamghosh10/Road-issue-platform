"""Static seed data: categories, West Bengal districts, demo officials.

LGD codes: real LGD codes should be imported from https://lgdirectory.gov.in. Until
then every code here is prefixed "SAMPLE-" so it can never be mistaken for real data.
"""

# Default SLA (hours) by severity 1 (minor) … 5 (critical). Tenants can override per
# category/severity in `sla_rules`. cluster_radius_m is larger for bridges because
# reports of one bridge can be tens of metres apart.
CATEGORIES: list[dict] = [
    {"code": "pothole", "name": "Pothole", "radius": 30,
     "sla": {"1": 336, "2": 240, "3": 168, "4": 72, "5": 48}},
    {"code": "bridge_leak", "name": "Bridge leak / seepage", "radius": 150,
     "sla": {"1": 168, "2": 120, "3": 96, "4": 72, "5": 48}},
    {"code": "bridge_crack", "name": "Bridge crack / structural damage", "radius": 150,
     "sla": {"1": 120, "2": 96, "3": 72, "4": 48, "5": 24}},
    {"code": "broken_railing", "name": "Broken railing", "radius": 50,
     "sla": {"1": 240, "2": 168, "3": 120, "4": 72, "5": 48}},
    {"code": "broken_divider", "name": "Broken divider", "radius": 50,
     "sla": {"1": 336, "2": 240, "3": 168, "4": 120, "5": 72}},
    {"code": "missing_signage", "name": "Missing / damaged signage", "radius": 30,
     "sla": {"1": 336, "2": 240, "3": 168, "4": 120, "5": 72}},
    {"code": "waterlogging", "name": "Waterlogging", "radius": 100,
     "sla": {"1": 120, "2": 72, "3": 48, "4": 24, "5": 12}},
    {"code": "road_cave_in", "name": "Road cave-in", "radius": 30,
     "sla": {"1": 72, "2": 48, "3": 24, "4": 12, "5": 6}},
    {"code": "other", "name": "Other", "radius": 30,
     "sla": {"1": 336, "2": 240, "3": 168, "4": 120, "5": 72}},
]

# All 23 West Bengal districts. Only the four around Kolkata get sample polygons.
WEST_BENGAL_DISTRICTS: list[str] = [
    "Alipurduar", "Bankura", "Birbhum", "Cooch Behar", "Dakshin Dinajpur", "Darjeeling",
    "Hooghly", "Howrah", "Jalpaiguri", "Jhargram", "Kalimpong", "Kolkata", "Malda",
    "Murshidabad", "Nadia", "North 24 Parganas", "Paschim Bardhaman", "Paschim Medinipur",
    "Purba Bardhaman", "Purba Medinipur", "Purulia", "South 24 Parganas", "Uttar Dinajpur",
]

DEMO_PASSWORD = "roadwatch-demo"  # dev only; printed by the seed script

# node: lgd_code of the jurisdiction the official is attached to.
# authority: key into the authorities created by the seed (see seed/run.py).
DEMO_OFFICIALS: list[dict] = [
    {"name": "State Roads Officer (demo)", "email": "state@demo.roadwatch.in",
     "role": "official", "node": "SAMPLE-ST-WB"},
    {"name": "Kolkata District Officer (demo)", "email": "district.kolkata@demo.roadwatch.in",
     "role": "official", "node": "SAMPLE-DT-KOLKATA"},
    {"name": "KMC Roads Engineer (demo)", "email": "kmc@demo.roadwatch.in",
     "role": "official", "node": "SAMPLE-ULB-KMC", "authority": "kmc"},
    {"name": "KMC Ward 1 Officer (demo)", "email": "kmc.ward001@demo.roadwatch.in",
     "role": "official", "node": "SAMPLE-KMC-W001"},
    {"name": "KMC Ward 2 Officer (demo)", "email": "kmc.ward002@demo.roadwatch.in",
     "role": "official", "node": "SAMPLE-KMC-W002"},
    {"name": "HMC Roads Engineer (demo)", "email": "hmc@demo.roadwatch.in",
     "role": "official", "node": "SAMPLE-ULB-HMC", "authority": "hmc"},
    {"name": "NHAI RO Kolkata (demo)", "email": "nhai@demo.roadwatch.in",
     "role": "official", "node": "SAMPLE-ST-WB", "authority": "nhai"},
    {"name": "WB PWD Engineer (demo)", "email": "pwd@demo.roadwatch.in",
     "role": "official", "node": "SAMPLE-ST-WB", "authority": "state_pwd"},
    {"name": "Tenant Admin (demo)", "email": "admin@demo.roadwatch.in",
     "role": "gov_admin", "node": "SAMPLE-ST-WB"},
]

# The platform operator (us), not a government user: moderation and audit only.
PLATFORM_ADMIN = {"name": "RoadWatch Platform Admin (demo)", "email": "platform@demo.roadwatch.in",
                  "role": "platform_admin"}
