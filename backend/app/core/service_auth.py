"""Pipeline-reporter machine authentication (D-01; contracts/reporter-auth.md).

Non-human ``pipeline-reporter`` callers present a long-lived bearer token on
the reporting endpoints. Each request is verified by argon2 hash-compare
against non-revoked ``api_tokens`` rows — read through the SECURITY DEFINER
``fn_api_token_lookup`` bootstrap (0002's ``fn_auth_user`` pattern), because
``api_tokens`` is RLS-scoped. The resolved service user + role are set on the
transaction so RLS and the audit trigger attribute posts to the service
identity (FR-024). Missing/invalid/revoked tokens are rejected with 401.
"""

import contextlib
import uuid
from dataclasses import dataclass
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, get_tx
from app.db.session_context import set_session_context

_hasher = PasswordHasher()
# Burn an argon2 verify on the no-match path so timing does not reveal
# whether any token matched (mirrors app.core.security's dummy hash).
_DUMMY_TOKEN_HASH = _hasher.hash("well-known-fake-token-for-timing-hiding")


class ReporterAuthError(Exception):
    """Missing, invalid, or revoked token (the route layer maps this to 401)."""


@dataclass(frozen=True)
class ReporterIdentity:
    user_id: uuid.UUID
    roles: tuple[str, ...]


def verify_reporter_token(conn: Connection, token: str) -> ReporterIdentity:
    """Hash-verify ``token`` against non-revoked ``api_tokens`` and set the
    transaction identity to the owning service user. Raises ReporterAuthError
    on missing/invalid/revoked tokens."""
    rows = (
        conn.execute(text("SELECT token_hash, user_id, role_slugs FROM fn_api_token_lookup()"))
        .mappings()
        .all()
    )
    matched = None
    for row in rows:
        with contextlib.suppress(Argon2Error):
            if _hasher.verify(row["token_hash"], token):
                matched = row
    if matched is None:
        with contextlib.suppress(Argon2Error):
            _hasher.verify(_DUMMY_TOKEN_HASH, token)
        raise ReporterAuthError("Invalid or revoked token")
    roles = tuple(matched["role_slugs"])
    set_session_context(conn, matched["user_id"], roles)
    return ReporterIdentity(user_id=matched["user_id"], roles=roles)


Conn = Annotated[Connection, Depends(get_tx)]


async def current_reporter(request: Request, conn: Conn) -> AuthContext:
    """FastAPI dependency: authenticate the bearer token and set the
    service identity on the transaction. 401 on missing/invalid/revoked."""
    header = request.headers.get("authorization") or ""
    scheme, _, raw_token = header.partition(" ")
    if scheme.lower() != "bearer" or not raw_token.strip():
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token")
    try:
        identity = verify_reporter_token(conn, raw_token.strip())
    except ReporterAuthError:
        raise HTTPException(status_code=401, detail="Invalid or revoked token") from None
    return AuthContext(
        user_id=identity.user_id,
        email=None,
        roles=identity.roles,
        display_name="pipeline-reporter",
    )
