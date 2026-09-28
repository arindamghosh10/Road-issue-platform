"""Offline stand-in for a vision model. No network, no key, deterministic.

It cannot really see damage, so it returns a neutral "plausible" answer with a typical
severity per category and a middling confidence (0.5). One real check: a nearly uniform
image (lens covered, blank frame) is reported as not showing any road.
"""

from io import BytesIO

import numpy as np
from PIL import Image

from app.vision.base import VisionResult

TYPICAL_SEVERITY = {
    "road_cave_in": 5,
    "bridge_crack": 4,
    "bridge_leak": 3,
    "pothole": 3,
    "waterlogging": 3,
    "broken_railing": 3,
    "broken_divider": 2,
    "missing_signage": 2,
    "other": 2,
}


class StubVisionVerifier:
    name = "stub"

    def assess_damage(
        self, image_jpeg: bytes, claimed_category: str, description: str | None
    ) -> VisionResult:
        gray = np.asarray(Image.open(BytesIO(image_jpeg)).convert("L"), dtype=np.float32)
        if gray.std() < 5:
            return VisionResult(
                provider=self.name,
                is_road_infrastructure=False,
                matches_category=False,
                detected_category=None,
                severity=1,
                confidence=0.9,
                reason="Image is almost uniform (blank or covered lens).",
            )
        return VisionResult(
            provider=self.name,
            is_road_infrastructure=True,
            matches_category=True,
            detected_category=claimed_category,
            severity=TYPICAL_SEVERITY.get(claimed_category, 2),
            confidence=0.5,
            reason="Stub verifier: no model was called; set VISION_PROVIDER=gemini for real checks.",
        )
