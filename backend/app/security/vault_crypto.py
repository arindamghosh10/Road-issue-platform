"""Crypto helpers for the identity vault.

Two different tools for two different jobs:

* Encryption (Fernet = AES-128-CBC + HMAC-SHA256) for values we must read back later,
  e.g. the phone number to send an OTP to.
* Keyed hashing (HMAC-SHA256 with a secret "pepper") for values we only ever need to
  compare, e.g. "has this phone / Aadhaar already registered or been banned?".

Why HMAC with a pepper rather than a per-row random salt? A per-row salt makes equal
inputs hash differently, so uniqueness and ban checks would be impossible. A secret
pepper keeps hashes comparable while making them useless to anyone without the key
(Indian phone/Aadhaar numbers are guessable, so a plain unkeyed hash could be brute-forced).
Both keys are held by the platform only — see README "Key custody".
"""

import hashlib
import hmac
import re
import secrets

from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().effective_vault_key.encode())


def normalize_phone(phone: str) -> str:
    """Canonical Indian mobile form: +91 followed by 10 digits."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("not a valid Indian mobile number")
    return "+91" + digits


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt(token: bytes) -> str:
    return _fernet().decrypt(token).decode()


def keyed_hash(value: str, purpose: str) -> str:
    """HMAC-SHA256 hex digest. `purpose` (e.g. "phone", "aadhaar") namespaces the hash so
    the same digits used as a phone and as an ID never collide."""
    key = get_settings().effective_pepper.encode()
    return hmac.new(key, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def new_reporter_id() -> str:
    """Random opaque reporter id, e.g. "R-8f3a…". Carries no information about the person."""
    return "R-" + secrets.token_hex(16)
