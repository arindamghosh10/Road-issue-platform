"""Pluggable identity connectors: how OTPs are delivered, and (later) Aadhaar/DigiLocker.

Everything here is a stub so the platform runs offline:
* StubOtpSender logs the code to the server log (phone masked) and remembers the last
  code per phone so automated tests can log in.
* AadhaarProvider is only an interface. Real Aadhaar e-KYC is restricted to
  UIDAI-licensed entities; DigiLocker is the likely route. Whatever plugs in must hand
  back a stable identifier that we HMAC-hash (see vault_crypto.keyed_hash) — the Aadhaar
  number itself must never be stored.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)


class OtpSender(Protocol):
    def send(self, phone_e164: str, code: str) -> None: ...


class StubOtpSender:
    def __init__(self) -> None:
        self.last_code: dict[str, str] = {}

    def send(self, phone_e164: str, code: str) -> None:
        self.last_code[phone_e164] = code
        log.warning("[OTP STUB] code for ******%s is %s", phone_e164[-4:], code)


@lru_cache
def get_otp_sender() -> OtpSender:
    provider = get_settings().otp_provider
    if provider == "stub":
        return StubOtpSender()
    raise ValueError(f"unknown OTP_PROVIDER {provider!r}")


@dataclass
class IdentityAssertion:
    """What an Aadhaar/DigiLocker verification returns to us. `subject` is hashed, never stored."""

    subject: str
    level: int = 2


class AadhaarProvider(Protocol):
    def verify(self, consent_token: str) -> IdentityAssertion: ...
