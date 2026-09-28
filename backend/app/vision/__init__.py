"""Vision model connectors. Pick one with VISION_PROVIDER (see base.py)."""

from functools import lru_cache

from app.config import get_settings
from app.vision.base import VisionResult, VisionVerifier


@lru_cache
def get_vision_verifier() -> VisionVerifier:
    provider = get_settings().vision_provider
    if provider == "stub":
        from app.vision.stub import StubVisionVerifier

        return StubVisionVerifier()
    if provider == "gemini":
        from app.vision.gemini import GeminiVisionVerifier

        return GeminiVisionVerifier()
    raise ValueError(f"unknown VISION_PROVIDER {provider!r}")


__all__ = ["VisionResult", "VisionVerifier", "get_vision_verifier"]
