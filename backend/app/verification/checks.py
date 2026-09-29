"""Individual verification checks. Each returns a CheckResult: a score 0..1 plus a reason.

A check can also `hard_fail`: a problem serious enough to reject the report no matter
how good the other checks look (e.g. a gallery upload, a reused photo).

Checks (brief §6):
1. capture_integrity — in-app camera, GPS precise enough, photo fresh, device attestation
2. location          — inside a known jurisdiction, near a mapped road
3. vision            — the model sees road infrastructure with the claimed damage
4. duplicate_image   — perceptual hash not seen on another report
Corroboration (several independent reporters) is applied at ticket level in clustering.
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.security.attestation import AttestationVerifier
from app.tickets.routing import Placement, nearest_road
from app.vision.base import VisionResult

IN_APP_CAMERA = "in_app_camera"


@dataclass
class CheckResult:
    name: str
    score: float
    reason: str  # English, for logs and as a fallback
    hard_fail: bool = False
    details: dict = field(default_factory=dict)
    # Stable id + values the apps translate (e.g. "capture.too_old", {"hours": 24}), so a
    # citizen reads the result in Hindi or Bengali. Keep codes stable: apps key on them.
    code: str = ""
    params: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReportContext:
    """Everything the checks need to know about one submission."""

    report_id: str
    reporter_id: str
    category_code: str
    lon: float
    lat: float
    gps_accuracy_m: float | None
    captured_at: datetime
    capture_source: str
    attestation_token: str | None
    phash: str
    exif_captured_at: datetime | None
    placement: Placement | None
    vision: VisionResult


# --- Checks -----------------------------------------------------------------------------


def capture_integrity(ctx: ReportContext, attestation: AttestationVerifier) -> CheckResult:
    s = get_settings()
    now = datetime.now(UTC)
    name = "capture_integrity"

    if ctx.capture_source != IN_APP_CAMERA:
        return CheckResult(name, 0.0, "Only photos taken with the in-app camera are accepted.", True,
                           code="capture.gallery")
    if ctx.captured_at > now + timedelta(minutes=5):
        return CheckResult(name, 0.0, "Photo time is in the future.", True, code="capture.future_time")
    if now - ctx.captured_at > timedelta(hours=s.max_photo_age_hours):
        return CheckResult(name, 0.0, f"Photo is older than {s.max_photo_age_hours} hours.", True,
                           code="capture.too_old", params={"hours": s.max_photo_age_hours})
    if ctx.gps_accuracy_m is None or ctx.gps_accuracy_m > s.reject_gps_accuracy_m:
        return CheckResult(name, 0.0, "GPS location is too imprecise. Try again outdoors.", True,
                           code="capture.gps_imprecise")

    score, notes, warnings = 1.0, [], []
    if ctx.gps_accuracy_m > s.max_gps_accuracy_m:
        score -= 0.3
        notes.append(f"GPS accuracy {ctx.gps_accuracy_m:.0f} m is weak")
        warnings.append("gps_weak")

    attested = attestation.verify(ctx.attestation_token)
    if attested is False:
        return CheckResult(name, 0.0, "App/device integrity check failed.", True,
                           code="capture.attestation_failed")
    if attested is None:
        if s.require_attestation:
            return CheckResult(name, 0.0, "Device attestation required.", True,
                               code="capture.attestation_required")
        score -= 0.1
        notes.append("device attestation not checked (stub)")
        warnings.append("attestation_unchecked")

    # If the phone embedded its own timestamp, it should agree with the app's.
    if ctx.exif_captured_at is not None:
        # EXIF times have no timezone; phones write local time, so allow ±14 h drift.
        exif_utc = ctx.exif_captured_at.replace(tzinfo=UTC)
        if abs((exif_utc - ctx.captured_at).total_seconds()) > 14 * 3600 + 900:
            score -= 0.3
            notes.append("photo's embedded time disagrees with capture time")
            warnings.append("time_mismatch")

    return CheckResult(name, max(0.0, score), "; ".join(notes) or "Captured in-app, fresh, precise GPS.",
                       details={"gps_accuracy_m": ctx.gps_accuracy_m, "attested": attested},
                       code="capture.warnings" if warnings else "capture.ok",
                       params={"warnings": warnings, "gps_m": round(ctx.gps_accuracy_m)} if warnings else {})


def location(ctx: ReportContext, db: Session) -> CheckResult:
    s = get_settings()
    name = "location"
    if ctx.placement is None:
        return CheckResult(name, 0.0, "Location is outside the areas this service covers.", True,
                           code="location.outside")

    road = nearest_road(db, ctx.lon, ctx.lat, s.road_snap_max_m)
    details = {"lowest_node_id": ctx.placement.lowest_node_id,
               "road_distance_m": round(road["dist_m"], 1) if road else None}
    if road:
        return CheckResult(name, 1.0, "On a mapped road.", details=details, code="location.on_road")
    if s.require_road_snap:
        return CheckResult(name, 0.0, "No road found at this location.", True, details,
                           code="location.no_road")
    return CheckResult(
        name, 0.6, "Inside a covered area, but no mapped road nearby (road data incomplete).",
        details=details, code="location.no_road_data",
    )


def vision(ctx: ReportContext) -> CheckResult:
    name = "vision"
    v = ctx.vision
    details = v.as_dict()
    if v.error:
        return CheckResult(name, 0.5, "Vision model unavailable; judged on other checks.", details=details,
                           code="vision.unavailable")
    if not v.is_road_infrastructure and v.confidence >= 0.6:
        return CheckResult(name, 0.0, "Photo does not appear to show a road or bridge.", True, details,
                           code="vision.not_road")
    if not v.matches_category and v.confidence >= 0.7:
        label = ctx.category_code.replace("_", " ")
        return CheckResult(name, 0.0, f"Photo does not appear to show a {label}.", True, details,
                           code="vision.wrong_category", params={"category": ctx.category_code})
    score = 0.5 + 0.5 * v.confidence if v.matches_category else 0.5 - 0.5 * v.confidence
    # The model's own explanation (v.reason) is English free text; apps show a translated
    # summary by code instead.
    return CheckResult(name, round(score, 3), v.reason, details=details,
                       code="vision.match" if score >= 0.5 else "vision.unsure")


def duplicate_image(ctx: ReportContext, db: Session) -> CheckResult:
    """Perceptual hashes of near-identical photos differ in only a few of their 64 bits.
    Postgres compares them directly: bit_count(a XOR b) = number of differing bits."""
    name = "duplicate_image"
    s = get_settings()
    match = db.execute(
        text("""
            SELECT id, bit_count(('x' || phash)::bit(64) # ('x' || :phash)::bit(64)) AS dist
            FROM reports
            WHERE phash IS NOT NULL AND id <> CAST(:report_id AS uuid)
              AND bit_count(('x' || phash)::bit(64) # ('x' || :phash)::bit(64)) <= :max_dist
            ORDER BY dist
            LIMIT 1
        """),
        {"phash": ctx.phash, "report_id": ctx.report_id, "max_dist": s.duplicate_phash_max_distance},
    ).first()
    if match:
        return CheckResult(name, 0.0, "This photo was already submitted.", True,
                           {"hamming_distance": int(match.dist)}, code="duplicate.seen")
    return CheckResult(name, 1.0, "Photo not seen before.", code="duplicate.new")
