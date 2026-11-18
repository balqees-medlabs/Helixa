"""Per-request dependencies: transaction, acting identity, RBAC guards.

``get_tx`` opens one transaction per request (research D2); ``current_user``
resolves the authenticated user from the access cookie (``sub`` only — never a
DB lookup under RLS, research D2) and calls Spec 1 ``set_session_context`` with
the user's roles before any handler query; ``require_roles`` enforces RBAC
(``admin`` passes every guard, constitution III.2). Commit on success, rollback
on any exception, so a change and its audit row stay atomic.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Connection, Engine

from app.core.config import get_settings, reset_cached_settings
from app.core.security import ACCESS_COOKIE, decode_access_token
from app.db.session_context import set_session_context

_engine: Engine | None = None


def get_engine() -> Engine:
    """The request-handling engine: connects as the non-superuser helixa_app."""
    global _engine
    if _engine is None:
        settings = get_settings()
        # Force the psycopg (v3) driver so a plain libpq DATABASE_URL works
        # regardless of the SQLAlchemy version's default (2.0 defaults to
        # psycopg2, which is not installed); mirrors alembic/env.py.
        url = make_url(settings.DATABASE_URL).set(
            drivername="postgresql+psycopg",
            username=settings.APP_DB_USER,
            password=settings.APP_DB_PASSWORD,
        )
        _engine = create_engine(url)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (tests point it at the disposable database)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
    reset_cached_settings()


def get_tx() -> Iterator[Connection]:
    """One transaction per request: the session context and all handler
    queries run on this connection; commit on success, rollback on error."""
    with get_engine().connect() as conn:
        tx = conn.begin()
        try:
            yield conn
        except BaseException:
            tx.rollback()
            raise
        tx.commit()


@dataclass(frozen=True)
class AuthContext:
    user_id: uuid.UUID
    roles: tuple[str, ...]
    display_name: str


def current_user(request: Request, conn: Annotated[Connection, Depends(get_tx)]) -> AuthContext:
    """Resolve the acting user from the access cookie and set the identity.

    The lookup goes through the migration-owned fn_auth_user bootstrap (the
    users/user_roles tables are admin-only under RLS); the resolved roles then
    drive set_session_context so all subsequent queries are RLS- and
    audit-attributed correctly.
    """
    user_id = decode_access_token(request.cookies.get(ACCESS_COOKIE))
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    row = (
        conn.execute(
            text(
                "SELECT id, is_active, display_name, role_slugs FROM fn_auth_user(:user_id, NULL)"
            ),
            {"user_id": user_id},
        )
        .mappings()
        .first()
    )

    if row is None or not row["is_active"]:
        raise HTTPException(status_code=401, detail="Not authenticated")

    roles: tuple[str, ...] = tuple(row["role_slugs"])
    set_session_context(conn, row["id"], roles)
    return AuthContext(user_id=row["id"], roles=roles, display_name=row["display_name"])


def require_roles(*slugs: str):
    """Route guard: pass with any of the given roles; ``admin`` passes all.

    Returns 403 (not 401) for an authenticated user lacking the role (SC-002).
    """

    def dependency(user: Annotated[AuthContext, Depends(current_user)]) -> AuthContext:
        if "admin" in user.roles or set(slugs) & set(user.roles):
            return user
        raise HTTPException(status_code=403, detail="Insufficient role")

    return dependency
