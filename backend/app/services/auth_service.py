"""Authentication service: credentials, sessions, refresh rotation (FR-001).

All reads/writes run on the request transaction. The ``fn_auth_*`` bootstrap
functions (migration ``0002``) resolve credentials/roles before an identity
exists; every statement after that runs with the caller's identity set so RLS
and audit attribution apply (research D1/D2).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.security import (
    dummy_verify,
    encode_access_token,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.db.session_context import set_session_context


class AuthError(Exception):
    """Base class for authentication failures."""


class InvalidCredentials(AuthError):
    """Unknown user, wrong password, or inactive account (indistinguishable)."""


class InvalidRefresh(AuthError):
    """Missing, unknown, expired, or idle-timed-out refresh token."""


class RefreshReuse(AuthError):
    """A rotated refresh token was replayed; the family has been revoked."""


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str | None
    display_name: str
    is_active: bool
    roles: tuple[str, ...]


@dataclass(frozen=True)
class Session:
    user: AuthenticatedUser
    access_token: str
    refresh_token: str


def _row_to_user(row) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        is_active=row["is_active"],
        roles=tuple(row["role_slugs"]),
    )


def _lookup_by_id(conn: Connection, user_id: uuid.UUID) -> AuthenticatedUser | None:
    row = (
        conn.execute(
            text(
                "SELECT id, email, is_active, display_name, role_slugs "
                "FROM fn_auth_user(:user_id, NULL)"
            ),
            {"user_id": user_id},
        )
        .mappings()
        .first()
    )
    return _row_to_user(row) if row else None


def _set_identity(conn: Connection, user: AuthenticatedUser) -> None:
    if not user.roles:
        raise InvalidCredentials("account has no roles")
    set_session_context(conn, user.id, user.roles)


def _issue_refresh(
    conn: Connection,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    expires_at: datetime,
) -> str:
    token = new_refresh_token()
    conn.execute(
        text(
            "INSERT INTO refresh_tokens (user_id, token_hash, family_id, expires_at) "
            "VALUES (:user_id, :token_hash, :family_id, :expires_at)"
        ),
        {
            "user_id": user_id,
            "token_hash": hash_refresh_token(token),
            "family_id": family_id,
            "expires_at": expires_at,
        },
    )
    return token


def _refresh_lookup(conn: Connection, token: str):
    return (
        conn.execute(
            text(
                "SELECT user_id, family_id, issued_at, expires_at, revoked_at "
                "FROM fn_auth_refresh_lookup(:token_hash)"
            ),
            {"token_hash": hash_refresh_token(token)},
        )
        .mappings()
        .first()
    )


def _revoke_family(conn: Connection, family_id: uuid.UUID) -> None:
    conn.execute(
        text(
            "UPDATE refresh_tokens SET revoked_at = now() "
            "WHERE family_id = :family_id AND revoked_at IS NULL"
        ),
        {"family_id": family_id},
    )


def login(conn: Connection, email: str, password: str) -> Session:
    """Verify credentials and start a session (access + rotating refresh)."""
    row = (
        conn.execute(
            text(
                "SELECT id, email, is_active, display_name, role_slugs, password_hash "
                "FROM fn_auth_user(NULL, :email)"
            ),
            {"email": email},
        )
        .mappings()
        .first()
    )
    if row is None:
        dummy_verify(password)  # equalize timing with the wrong-password path
        raise InvalidCredentials("invalid credentials")
    if not verify_password(row["password_hash"], password):
        raise InvalidCredentials("invalid credentials")

    user = _row_to_user(row)
    if not user.is_active:
        raise InvalidCredentials("invalid credentials")
    if not user.roles:
        raise InvalidCredentials("account has no roles")

    _set_identity(conn, user)

    # Attributed to the signing-in user: app.user_id is already set.
    conn.execute(text("SELECT fn_auth_touch_login(:user_id)"), {"user_id": user.id})

    settings = get_settings()
    family_id = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_ABSOLUTE_D)
    refresh_token = _issue_refresh(conn, user.id, family_id, expires_at)

    return Session(
        user=user,
        access_token=encode_access_token(user.id),
        refresh_token=refresh_token,
    )


def rotate(conn: Connection, presented: str | None) -> Session:
    """Rotate a valid refresh token; replay of a used token revokes the family."""
    if not presented:
        raise InvalidRefresh("missing refresh token")

    row = _refresh_lookup(conn, presented)
    if row is None:
        raise InvalidRefresh("unknown refresh token")

    user = _lookup_by_id(conn, row["user_id"])
    if user is None or not user.is_active or not user.roles:
        raise InvalidRefresh("unknown refresh token")

    _set_identity(conn, user)

    if row["revoked_at"] is not None:
        # Reuse of an already-rotated/logged-out token: breach response.
        _revoke_family(conn, row["family_id"])
        raise RefreshReuse("refresh token reuse detected")

    now = datetime.now(UTC)
    settings = get_settings()
    if row["expires_at"] <= now:
        raise InvalidRefresh("refresh token expired")
    if now - row["issued_at"] > timedelta(hours=settings.REFRESH_IDLE_H):
        conn.execute(
            text(
                "UPDATE refresh_tokens SET revoked_at = now() "
                "WHERE token_hash = :token_hash AND revoked_at IS NULL"
            ),
            {"token_hash": hash_refresh_token(presented)},
        )
        raise InvalidRefresh("refresh token idle timeout")

    revoked = conn.execute(
        text(
            "UPDATE refresh_tokens SET revoked_at = now() "
            "WHERE token_hash = :token_hash AND revoked_at IS NULL"
        ),
        {"token_hash": hash_refresh_token(presented)},
    )
    if revoked.rowcount == 0:
        # Lost a race with a concurrent rotation: treat as reuse.
        _revoke_family(conn, row["family_id"])
        raise RefreshReuse("refresh token reuse detected")

    # Keep the original absolute deadline (never extend past the family cap).
    refresh_token = _issue_refresh(conn, user.id, row["family_id"], row["expires_at"])

    return Session(
        user=user,
        access_token=encode_access_token(user.id),
        refresh_token=refresh_token,
    )


def logout(conn: Connection, presented: str | None) -> None:
    """Revoke the presented refresh family; always succeeds (204 semantics)."""
    if not presented:
        return
    row = _refresh_lookup(conn, presented)
    if row is None:
        return
    user = _lookup_by_id(conn, row["user_id"])
    if user is None:
        return
    if user.roles:
        _set_identity(conn, user)
    _revoke_family(conn, row["family_id"])
