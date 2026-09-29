"""Shared FastAPI dependencies."""

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_core_db
from app.models.core import Official, Reporter
from app.security.tokens import decode_token

bearer = HTTPBearer(auto_error=False)


def current_official(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_core_db),
) -> Official:
    """The logged-in government official."""
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required.")
    if creds is None:
        raise unauthorized
    try:
        claims = decode_token(creds.credentials)
    except jwt.InvalidTokenError:
        raise unauthorized from None
    if claims.get("role") != "official":
        raise unauthorized
    try:
        official = db.get(Official, uuid.UUID(claims["sub"]))
    except ValueError:
        raise unauthorized from None
    if official is None or not official.is_active:
        raise unauthorized
    return official


def current_reporter_id(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_core_db),
) -> str:
    """The logged-in citizen's opaque reporter_id (from their token)."""
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required.")
    if creds is None:
        raise unauthorized
    try:
        claims = decode_token(creds.credentials)
    except jwt.InvalidTokenError:
        raise unauthorized from None
    if claims.get("role") != "citizen":
        raise unauthorized
    banned = db.scalar(select(Reporter.banned).where(Reporter.reporter_id == claims["sub"]))
    if banned is None:
        raise unauthorized
    if banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is suspended.")
    return claims["sub"]
