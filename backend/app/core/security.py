"""Password hashing, JWT access tokens, opaque refresh tokens, cookie helpers.

Constitution III.1: the backend issues and validates tokens; they are never
exposed to frontend JS — both live in HttpOnly cookies. The refresh token is
stored only as a SHA-256 hash (research D1).
"""

import contextlib
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from fastapi import Response

from app.core.config import get_settings

ACCESS_COOKIE = "access"
REFRESH_COOKIE = "refresh"

_hasher = PasswordHasher()  # argon2id with library defaults

# Precomputed hash of a random value. Verifying against it burns roughly one
# argon2 verification so the "unknown account" path takes similar time to the
# "wrong password" path (mitigates user enumeration by response timing).
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def dummy_verify(password: str) -> None:
    """Spend ~one argon2 verify and discard the result; call on the no-such-user
    path so login timing does not reveal whether an email exists."""
    with contextlib.suppress(Argon2Error):
        _hasher.verify(_DUMMY_HASH, password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-time-ish verify; any failure (bad hash, mismatch) → False."""
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except Argon2Error:
        return False


def encode_access_token(user_id: uuid.UUID) -> str:
    """HS256 JWT carrying ``sub`` + ``exp`` only (T017)."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(minutes=settings.ACCESS_TTL_MIN),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str | None) -> uuid.UUID | None:
    """Return the user id for a valid, unexpired token; None otherwise."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_settings().JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


def new_refresh_token() -> str:
    """Opaque random token; only its SHA-256 is ever persisted."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    """Access cookie: HttpOnly; Secure; SameSite=Lax (whole site).

    Refresh cookie: HttpOnly; Secure; SameSite=Strict scoped to ``/auth``
    (CSRF defense-in-depth for the rotation endpoint, research D1).
    """
    settings = get_settings()
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.ACCESS_TTL_MIN * 60,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.REFRESH_ABSOLUTE_D * 86400,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/auth",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/auth")
