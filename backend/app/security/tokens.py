"""Signed login tokens (JWT, HS256).

A citizen token carries only the opaque reporter_id — never a phone number or any other
identity field — so even a leaked token reveals nothing about who the person is.
"""

import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def issue_citizen_token(reporter_id: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    claims = {
        "jti": secrets.token_hex(8),  # unique per token; lets us revoke single tokens later
        "sub": reporter_id,
        "role": "citizen",
        "iat": now,
        "exp": now + timedelta(hours=s.citizen_token_ttl_hours),
    }
    return jwt.encode(claims, s.effective_jwt_secret, algorithm=ALGORITHM)


def issue_official_token(official_id: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    claims = {
        "jti": secrets.token_hex(8),
        "sub": official_id,
        "role": "official",
        "iat": now,
        "exp": now + timedelta(hours=s.official_token_ttl_hours),
    }
    return jwt.encode(claims, s.effective_jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError if the token is forged, malformed or expired."""
    return jwt.decode(token, get_settings().effective_jwt_secret, algorithms=[ALGORITHM])
