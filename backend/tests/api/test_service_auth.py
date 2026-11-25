"""Spec 4 API tests: pipeline-reporter token auth (T015).

Covers contracts/reporter-auth.md — token auth valid / invalid / revoked /
out-of-scope-403. The admin mint/list/revoke surface is exercised through the
TestClient; authentication is verified against the real ``api_tokens`` rows
(through the migration's SECURITY DEFINER ``fn_api_token_lookup`` bootstrap).
"""

import asyncio
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from starlette.requests import Request

from app.core.deps import AuthContext, require_roles
from app.core.service_auth import ReporterAuthError, current_reporter, verify_reporter_token
from tests.db.conftest import helixa_engine as _db_helixa_engine  # noqa: F401
from tests.db.conftest import set_session_context  # noqa: F401


def _reporter_user_id(admin_engine) -> uuid.UUID:
    with admin_engine.connect() as conn, conn.begin():
        return conn.execute(
            text(
                "SELECT u.id FROM users u "
                "JOIN user_roles ur ON ur.user_id = u.id "
                "JOIN roles r ON r.id = ur.role_id "
                "WHERE r.slug = 'pipeline-reporter' LIMIT 1"
            )
        ).scalar_one()


def _request_with_bearer(token: str | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_mint_returns_token_once(admin_client) -> None:
    resp = admin_client.post("/api-tokens", json={"name": "test-reporter@lab"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token"]
    assert body["name"] == "test-reporter@lab"
    assert body["revoked_at"] is None


def test_list_returns_metadata_only(admin_client) -> None:
    admin_client.post("/api-tokens", json={"name": "meta-test"})
    resp = admin_client.get("/api-tokens")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows
    assert all("token" not in row for row in rows)


def test_revoke_returns_revoked_row(admin_client) -> None:
    mint = admin_client.post("/api-tokens", json={"name": "revoked-row"})
    token_id = uuid.UUID(mint.json()["id"])
    resp = admin_client.delete(f"/api-tokens/{token_id}")
    assert resp.status_code == 200
    assert resp.json()["revoked_at"] is not None


def test_valid_token_authenticates_as_reporter(
    admin_client, helixa_engine, admin_engine
) -> None:
    mint = admin_client.post("/api-tokens", json={"name": "valid-reporter"})
    token = mint.json()["token"]
    service_id = _reporter_user_id(admin_engine)
    with helixa_engine.connect() as conn, conn.begin():
        set_session_context(conn, service_id, ["pipeline-reporter"])
        identity = verify_reporter_token(conn, token)
        assert identity.user_id == service_id
        assert identity.roles == ("pipeline-reporter",)
        # The transaction identity is set so RLS + audit attribute writes.
        acting = conn.execute(
            text("SELECT nullif(current_setting('app.user_id', true), '')")
        ).scalar_one()
        assert acting == str(service_id)


def test_invalid_token_is_rejected(helixa_engine) -> None:
    with helixa_engine.connect() as conn, conn.begin(), pytest.raises(ReporterAuthError):
        verify_reporter_token(conn, "not-a-real-token")


def test_missing_bearer_is_rejected(helixa_engine) -> None:
    with (
        helixa_engine.connect() as conn,
        conn.begin(),
        pytest.raises(HTTPException) as exc_info,
    ):
        asyncio.run(current_reporter(_request_with_bearer(None), conn))
    assert exc_info.value.status_code == 401


def test_revoked_token_is_rejected(admin_client, helixa_engine, admin_engine) -> None:
    mint = admin_client.post("/api-tokens", json={"name": "revoked-reporter"})
    token_id = uuid.UUID(mint.json()["id"])
    assert admin_client.delete(f"/api-tokens/{token_id}").status_code == 200
    with helixa_engine.connect() as conn, conn.begin(), pytest.raises(ReporterAuthError):
        verify_reporter_token(conn, mint.json()["token"])


def test_reporter_token_is_out_of_scope_for_human_routes(admin_engine) -> None:
    service_id = _reporter_user_id(admin_engine)
    ctx = AuthContext(
        user_id=service_id,
        email=None,
        roles=("pipeline-reporter",),
        display_name="pipeline-reporter",
    )
    with pytest.raises(HTTPException) as exc_info:
        require_roles("molecular")(ctx)
    assert exc_info.value.status_code == 403
