"""Citizen API: phone OTP sign-in, submitting reports, tracking one's own reports.

These endpoints know the caller's opaque reporter_id (from the token) but never any
identity details — those stay in the vault.
"""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_reporter_id
from app.db import get_core_db
from app.identity.service import AuthError, request_otp, verify_otp
from app.models.core import Category, Report, Ticket
from app.reports.service import NewReport, ReportError, create_report, enqueue_processing
from app.security.tokens import issue_citizen_token

router = APIRouter(prefix="/api/v1/citizen", tags=["citizen"])

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


class OtpRequest(BaseModel):
    phone: str = Field(examples=["9876543210"])


class OtpRequested(BaseModel):
    challenge_id: uuid.UUID
    message: str = "Code sent."


class OtpVerify(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(min_length=4, max_length=8)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CheckOut(BaseModel):
    name: str
    passed: bool
    reason: str


class MyReport(BaseModel):
    id: uuid.UUID
    status: str
    category: str
    submitted_on: date
    rejection_reason: str | None
    ticket_ref: str | None
    checks: list[CheckOut]


@router.post("/auth/otp/request", response_model=OtpRequested)
def otp_request(body: OtpRequest) -> OtpRequested:
    try:
        return OtpRequested(challenge_id=request_otp(body.phone))
    except AuthError as exc:
        raise HTTPException(exc.status_code, exc.message) from None


@router.post("/auth/otp/verify", response_model=TokenOut)
def otp_verify(body: OtpVerify) -> TokenOut:
    try:
        reporter_id = verify_otp(body.challenge_id, body.code)
    except AuthError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    return TokenOut(access_token=issue_citizen_token(reporter_id))


def _to_my_report(report: Report, category_code: str, ticket_ref: str | None) -> MyReport:
    checks = (report.verification_details or {}).get("checks", [])
    return MyReport(
        id=report.id,
        status=report.status,
        category=category_code,
        submitted_on=report.received_at.date(),
        rejection_reason=report.rejection_reason,
        ticket_ref=ticket_ref,
        checks=[CheckOut(name=c["name"], passed=not c["hard_fail"] and c["score"] >= 0.5,
                         reason=c["reason"]) for c in checks],
    )


@router.post("/reports", response_model=MyReport, status_code=status.HTTP_202_ACCEPTED)
def submit_report(
    photo: UploadFile = File(...),
    category: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    gps_accuracy_m: float | None = Form(None),
    captured_at: datetime = Form(...),
    capture_source: str = Form(..., description='Must be "in_app_camera"; gallery uploads are refused.'),
    attestation_token: str | None = Form(None),
    description: str | None = Form(None, max_length=1000),
    reporter_id: str = Depends(current_reporter_id),
    db: Session = Depends(get_core_db),
) -> MyReport:
    """Submit a photo report. Verification runs in the background; poll GET /reports/{id}."""
    if capture_source != "in_app_camera":
        raise HTTPException(422, "Only photos taken with the in-app camera are accepted.")
    if (photo.content_type or "") not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(415, "Photo must be JPEG, PNG, WebP or HEIC.")
    if captured_at.tzinfo is None:
        raise HTTPException(422, "captured_at must include a timezone (ISO 8601).")
    try:
        report = create_report(db, NewReport(
            reporter_id=reporter_id, category_code=category, lat=lat, lon=lon,
            gps_accuracy_m=gps_accuracy_m, captured_at=captured_at,
            capture_source=capture_source, attestation_token=attestation_token,
            description=description, photo=photo.file.read(),
            photo_content_type=photo.content_type or "application/octet-stream",
        ))
    except ReportError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    enqueue_processing(report.id)
    return get_my_report(report.id, reporter_id, db)


@router.get("/reports", response_model=list[MyReport])
def list_my_reports(
    reporter_id: str = Depends(current_reporter_id), db: Session = Depends(get_core_db)
) -> list[MyReport]:
    rows = db.execute(
        select(Report, Category.code, Ticket.public_ref)
        .join(Category, Category.id == Report.category_id)
        .outerjoin(Ticket, Ticket.id == Report.ticket_id)
        .where(Report.reporter_id == reporter_id)
        .order_by(Report.received_at.desc())
        .limit(200)
    ).all()
    return [_to_my_report(r, code, ref) for r, code, ref in rows]


@router.get("/reports/{report_id}", response_model=MyReport)
def get_my_report(
    report_id: uuid.UUID,
    reporter_id: str = Depends(current_reporter_id),
    db: Session = Depends(get_core_db),
) -> MyReport:
    db.expire_all()  # the worker may have updated the row since this session loaded it
    row = db.execute(
        select(Report, Category.code, Ticket.public_ref)
        .join(Category, Category.id == Report.category_id)
        .outerjoin(Ticket, Ticket.id == Report.ticket_id)
        .where(Report.id == report_id, Report.reporter_id == reporter_id)
    ).first()
    if row is None:
        raise HTTPException(404, "Report not found.")
    return _to_my_report(*row)
