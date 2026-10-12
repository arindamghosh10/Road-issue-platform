"""Time-based one-time passwords (TOTP) for officials' two-factor login.

The official scans a QR code (an `otpauth://` URI) into any authenticator app (Google
Authenticator, Microsoft Authenticator, Aegis…); the app then shows a new 6-digit code
every 30 seconds, computed from a shared secret and the current time. Free, offline,
no SMS needed.
"""

import pyotp

ISSUER = "RoadWatch"


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def verify(secret: str, code: str | None) -> bool:
    if not code:
        return False
    # valid_window=1 accepts the previous/next 30 s code, to tolerate clock drift.
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
