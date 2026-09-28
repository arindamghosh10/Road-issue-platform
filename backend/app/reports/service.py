"""Citizen reports: accept an upload, then verify it and attach it to a ticket.

create_report()  — runs inside the upload request. Stores the ORIGINAL photo in the
                   private bucket and a report row with status under_verification.
process_report() — runs in the background worker (or inline when TASKS_EAGER=true).
                   Sanitizes the photo, runs the verification pipeline, and on success
                   publishes the sanitized copy and merges the report into a ticket.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import core_session
from app.imaging.sanitize import InvalidImage, sanitize
from app.models.core import Category, Report, ReportStatus
from app.notifications.service import notify_officials, notify_reporter, officials_for_node
from app.storage import get_store
from app.tickets.clustering import attach_to_ticket
from app.tickets.routing import locate
from app.verification.checks import ReportContext, StubAttestationVerifier
from app.verification.pipeline import run_pipeline
from app.vision import get_vision_verifier

log = logging.getLogger(__name__)


class ReportError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class NewReport:
    reporter_id: str
    category_code: str
    lat: float
    lon: float
    gps_accuracy_m: float | None
    captured_at: datetime
    capture_source: str
    attestation_token: str | None
    description: str | None
    photo: bytes
    photo_content_type: str


def create_report(db: Session, data: NewReport) -> Report:
    s = get_settings()
    category = db.scalar(select(Category).where(Category.code == data.category_code))
    if category is None:
        raise ReportError("Unknown category.", 422)
    if not (-90 <= data.lat <= 90 and -180 <= data.lon <= 180):
        raise ReportError("Invalid coordinates.", 422)
    if len(data.photo) > s.max_upload_mb * 1024 * 1024:
        raise ReportError(f"Photo is larger than {s.max_upload_mb} MB.", 413)
    if not data.photo:
        raise ReportError("Photo is empty.", 422)

    report_id = uuid.uuid4()
    key = f"reports/{report_id}/original"
    get_store().put(s.s3_bucket_original, key, data.photo, data.photo_content_type)

    report = Report(
        id=report_id,
        reporter_id=data.reporter_id,
        category_id=category.id,
        description=(data.description or "").strip()[:1000] or None,
        photo_original_key=key,
        location=from_shape(Point(data.lon, data.lat), srid=4326),
        gps_accuracy_m=data.gps_accuracy_m,
        captured_at=data.captured_at,
        status=ReportStatus.UNDER_VERIFICATION.value,
        # Capture metadata the checks need later; internal only, never shown to gov/public.
        verification_details={
            "capture": {"source": data.capture_source, "attestation_token": data.attestation_token}
        },
    )
    db.add(report)
    db.commit()
    return report


def _reject(report: Report, reason: str, details: dict) -> None:
    report.status = ReportStatus.REJECTED.value
    report.rejection_reason = reason
    report.verification_details = details


def process_report(report_id: uuid.UUID) -> None:
    s = get_settings()
    store = get_store()
    with core_session() as db:
        report = db.get(Report, report_id, with_for_update=True)
        if report is None or report.status != ReportStatus.UNDER_VERIFICATION.value:
            return  # already processed (e.g. a retried task)
        category = db.get(Category, report.category_id)
        capture = (report.verification_details or {}).get("capture", {})
        point = to_shape(report.location)

        try:
            clean = sanitize(store.get(s.s3_bucket_original, report.photo_original_key))
        except InvalidImage as exc:
            _reject(report, "The photo could not be read.", {"error": str(exc)})
            db.commit()
            return
        report.phash = clean.phash

        placement = locate(db, point.x, point.y)
        vision_result = get_vision_verifier().assess_damage(
            clean.jpeg, category.code, report.description  # sanitized image only
        )
        ctx = ReportContext(
            report_id=str(report.id),
            reporter_id=report.reporter_id,
            category_code=category.code,
            lon=point.x,
            lat=point.y,
            gps_accuracy_m=report.gps_accuracy_m,
            captured_at=report.captured_at,
            capture_source=capture.get("source", ""),
            attestation_token=capture.get("attestation_token"),
            phash=clean.phash,
            exif_captured_at=clean.exif_captured_at,
            placement=placement,
            vision=vision_result,
        )
        verdict = run_pipeline(ctx, db, StubAttestationVerifier())
        report.verification_score = verdict.score
        details = verdict.details() | {
            "sanitization": {"faces_blurred": clean.faces_blurred,
                             "plates_blurred": clean.plates_blurred},
        }

        if not verdict.verified:
            _reject(report, verdict.reason, details)
            notify_reporter(db, report.reporter_id, None, "report_rejected",
                            "Your report could not be verified", verdict.reason)
            db.commit()
            log.info("report %s rejected: %s", report.id, verdict.reason)
            return

        public_key = f"reports/{report.id}/public.jpg"
        store.put(s.s3_bucket_public, public_key, clean.jpeg, "image/jpeg")
        report.photo_public_key = public_key
        report.status = ReportStatus.VERIFIED.value
        report.verification_details = details
        severity = vision_result.severity if not vision_result.error else 3
        ticket, created = attach_to_ticket(db, report, category, point.x, point.y, severity, placement)
        notify_reporter(db, report.reporter_id, ticket, "report_verified",
                        f"Report verified: {ticket.public_ref}",
                        f"Your report is part of ticket {ticket.public_ref} "
                        f"({ticket.unique_reporters} verified citizen(s) so far).")
        if created:
            notify_officials(
                db, officials_for_node(db, placement.lowest_node_id, placement.authority_id),
                ticket, "new_ticket", f"New issue: {category.name} ({ticket.public_ref})",
                f"A verified {category.name.lower()} report was filed in your area. "
                f"Deadline: {ticket.sla_due_at:%d %b %Y %H:%M} UTC.",
            )
        db.commit()
        log.info("report %s verified → ticket %s (%s)", report.id, ticket.public_ref,
                 "new" if created else "merged")


def enqueue_processing(report_id: uuid.UUID) -> None:
    if get_settings().tasks_eager:
        process_report(report_id)
        return
    from app.worker import verify_report_task

    verify_report_task.delay(str(report_id))
