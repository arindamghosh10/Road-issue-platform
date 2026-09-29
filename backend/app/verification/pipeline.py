"""Combine the individual checks into one verdict.

verdict = rejected if any check hard-fails, otherwise
          verified if the weighted average score ≥ VERIFICATION_THRESHOLD (default 0.6).

Weights reflect how much each signal says about "is this a real, current problem at this
spot": the vision model counts most, but can never pass a report on its own.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import get_settings
from app.verification import checks
from app.verification.checks import AttestationVerifier, CheckResult, ReportContext

WEIGHTS = {
    "capture_integrity": 0.25,
    "location": 0.25,
    "vision": 0.4,
    "duplicate_image": 0.1,
}


@dataclass
class Verdict:
    verified: bool
    score: float
    reason: str
    results: list[CheckResult]
    code: str = "verified"  # translatable id of `reason` (see CheckResult.code)
    params: dict = field(default_factory=dict)

    def details(self) -> dict:
        out = {"score": self.score, "checks": [r.as_dict() for r in self.results]}
        if not self.verified:
            out["rejection"] = {"code": self.code, "params": self.params}
        return out


def run_pipeline(ctx: ReportContext, db: Session, attestation: AttestationVerifier) -> Verdict:
    results = [
        checks.capture_integrity(ctx, attestation),
        checks.location(ctx, db),
        checks.vision(ctx),
        checks.duplicate_image(ctx, db),
    ]
    score = round(sum(WEIGHTS[r.name] * r.score for r in results) / sum(WEIGHTS.values()), 3)

    hard = next((r for r in results if r.hard_fail), None)
    if hard:
        return Verdict(False, score, hard.reason, results, hard.code, hard.params)
    threshold = get_settings().verification_threshold
    if score < threshold:
        weakest = min(results, key=lambda r: r.score)
        return Verdict(False, score, f"Could not verify this report ({weakest.reason})", results,
                       "low_score", {"weakest": weakest.code, **weakest.params})
    return Verdict(True, score, "Verified.", results)
