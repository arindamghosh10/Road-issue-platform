"""Device attestation: "was this upload made by our genuine app on a real, unmodified phone?"

Phones can vouch for the app that is running on them:
* Android — Google Play Integrity API (free within its quota)
* iOS     — Apple App Attest
The app asks the phone for a signed token and sends it with the report; the server
verifies the token with Google/Apple. This is what finally closes the "script that
pretends to be the camera app" gap — the API alone can't tell a script from the app.

This module is the HOOK. Plugging in a real provider means:
1. Implement `AttestationVerifier.verify(token)` for Play Integrity / App Attest
   (decode + check package name, certificate digest, device integrity verdict and a
   server-issued nonce bound to the upload).
2. Register it in `get_attestation_verifier()` under a new ATTESTATION_PROVIDER value.
3. Set REQUIRE_ATTESTATION=true once most users run an app version that sends tokens.
Until then the stub answers "not checked", which lowers a report's capture score a
little but does not reject it (see app/verification/checks.py).
"""

from functools import lru_cache
from typing import Protocol

from app.config import get_settings


class AttestationVerifier(Protocol):
    def verify(self, token: str | None) -> bool | None:
        """True = genuine app on a genuine device; False = forged/invalid (reject);
        None = not checked (no provider configured, or no token sent)."""


class StubAttestationVerifier:
    def verify(self, token: str | None) -> bool | None:
        return None


@lru_cache
def get_attestation_verifier() -> AttestationVerifier:
    provider = get_settings().attestation_provider
    if provider == "stub":
        return StubAttestationVerifier()
    raise ValueError(f"unknown ATTESTATION_PROVIDER {provider!r} (see app/security/attestation.py)")
