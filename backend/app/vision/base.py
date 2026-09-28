"""The `VisionVerifier` interface: "does this photo show the damage the citizen claims?"

A vision model here is a multimodal AI model: you send it an image plus a text prompt,
and it answers in text. We ask it to answer in a fixed JSON shape so the result can be
scored by ordinary code. The model is only one signal among several (see
app/verification); it never decides alone, because models can be wrong or fooled.

Implementations:
* StubVisionVerifier   — offline, deterministic, no key. Default for dev and tests.
* GeminiVisionVerifier — Google Gemini API free tier. Only ever receives SANITIZED
                         images (EXIF stripped, faces/plates blurred).
"""

from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass
class VisionResult:
    provider: str
    is_road_infrastructure: bool  # road / bridge / flyover / footpath visible at all?
    matches_category: bool  # does it show the claimed kind of damage?
    detected_category: str | None
    severity: int  # 1 (minor) … 5 (dangerous / critical)
    confidence: float  # 0..1, the model's own confidence
    reason: str
    error: str | None = None  # set when the model could not be reached / parsed

    def as_dict(self) -> dict:
        return asdict(self)


class VisionVerifier(Protocol):
    name: str

    def assess_damage(
        self, image_jpeg: bytes, claimed_category: str, description: str | None
    ) -> VisionResult: ...
