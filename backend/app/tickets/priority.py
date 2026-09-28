"""Ticket priority: priority = f(severity, unique_reporters, road_class, age).

A plain additive score so officials can read it:
* severity 1–5            → 10 points each (dominant factor)
* independent reporters   → 8 × log2(1 + n): the 2nd reporter matters more than the 20th
* road class              → busier roads first (national/state highways over lanes)
* age                     → +0.5 per day open, capped at 30 days, so old tickets rise
"""

import math

ROAD_CLASS_WEIGHT = {
    "motorway": 10,
    "trunk": 10,
    "primary": 7,
    "secondary": 5,
    "tertiary": 3,
}
DEFAULT_ROAD_WEIGHT = 2


def compute_priority(
    severity: int, unique_reporters: int, road_class: str | None, age_days: float = 0.0
) -> float:
    score = (
        severity * 10
        + 8 * math.log2(1 + max(0, unique_reporters))
        + ROAD_CLASS_WEIGHT.get(road_class or "", DEFAULT_ROAD_WEIGHT)
        + min(max(0.0, age_days), 30) * 0.5
    )
    return round(score, 2)
