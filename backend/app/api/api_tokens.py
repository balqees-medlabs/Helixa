"""Machine-token admin endpoints (contracts/reporter-auth.md; D-01).

Admin-only mint/list/revoke of ``pipeline-reporter`` API tokens. The raw token
is returned once at mint (``POST``); only its argon2 hash is stored
(``api_tokens.token_hash``, mirroring the password rule — Article III.4).
Revocation (``DELETE``) sets ``revoked_at`` — immediate auth failure (FR-024).
"""

import secrets
import uuid
from typing import Annotated

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, get_tx, require_roles
from app.schemas.pipeline import ApiTokenCreate, ApiTokenMintedOut, ApiTokenOut

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])

Admin = Annotated[AuthContext, Depends(require_roles("admin"))]
Conn = Annotated[Connection, Depends(get_tx)]

_hasher = PasswordHasher()
_TOKEN_SQL_COLUMNS = "id, name, user_id, created_by, created_at, revoked_at"


def _service_user_id(conn: Connection) -> uuid.UUID:
    row = conn.execute(
        text(
            "SELECT u.id FROM users u "
            "JOIN user_roles ur ON ur.user_id = u.id "
            "JOIN roles r ON r.id = ur.role_id "
            "WHERE r.slug = 'pipeline-reporter' LIMIT 1"
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="pipeline-reporter service user not found")
    return row


@router.get("", response_model=list[ApiTokenOut])
def list_api_tokens(_user: Admin, conn: Conn) -> list[ApiTokenOut]:
    rows = (
        conn.execute(text(f"SELECT {_TOKEN_SQL_COLUMNS} FROM api_tokens ORDER BY created_at"))
        .mappings()
        .all()
    )
    return [ApiTokenOut(**row) for row in rows]


@router.post("", response_model=ApiTokenMintedOut, status_code=201)
def mint_api_token(body: ApiTokenCreate, _user: Admin, conn: Conn) -> ApiTokenMintedOut:
    user_id = _service_user_id(conn)
    raw_token = secrets.token_urlsafe(32)
    row = (
        conn.execute(
            text(
                "INSERT INTO api_tokens (name, user_id, token_hash, created_by) "
                "VALUES (:name, :user_id, :token_hash, :created_by) "
                f"RETURNING {_TOKEN_SQL_COLUMNS}"
            ),
            {
                "name": body.name,
                "user_id": str(user_id),
                "token_hash": _hasher.hash(raw_token),
                "created_by": str(_user.user_id),
            },
        )
        .mappings()
        .one()
    )
    return ApiTokenMintedOut(**row, token=raw_token)


@router.delete("/{token_id}", response_model=ApiTokenOut)
def revoke_api_token(token_id: uuid.UUID, _user: Admin, conn: Conn) -> ApiTokenOut:
    row = (
        conn.execute(
            text(
                f"UPDATE api_tokens SET revoked_at = now() WHERE id = :id "
                f"RETURNING {_TOKEN_SQL_COLUMNS}"
            ),
            {"id": str(token_id)},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="API token not found")
    return ApiTokenOut(**row)
