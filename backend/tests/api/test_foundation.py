"""Phase 2 checkpoint validation (T020).

Proves on real Postgres, through the real request path:
- a request without/with an invalid access cookie → 401
- an authenticated request resolves the user, and the per-request transaction
  carries app.user_id / app.role_names exactly as set by ``current_user``
- ``require_roles`` allows the listed roles and admin, denies others (403)
- the Alembic history is linear: single head, 0001 → 0002

The routes live on a throwaway FastAPI app because production routers are
registered in later phases; the dependencies under test are the real ones.
"""

from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, current_user, get_tx, require_roles
from app.core.security import ACCESS_COOKIE

pytestmark = pytest.mark.usefixtures("database_url")

BACKEND_DIR = Path(__file__).resolve().parents[2]

smoke = FastAPI()


@smoke.get("/whoami")
def whoami(
    user: Annotated[AuthContext, Depends(current_user)],
    conn: Annotated[Connection, Depends(get_tx)],
) -> dict:
    # Same transactional connection (FastAPI caches get_tx per request), so
    # this reads the session context current_user set before any handler query.
    row = (
        conn.execute(
            text(
                "SELECT current_setting('app.user_id') AS uid, "
                "current_setting('app.role_names') AS roles"
            )
        )
        .mappings()
        .one()
    )
    return {
        "user_id": str(user.user_id),
        "roles": list(user.roles),
        "set_uid": row["uid"],
        "set_roles": row["roles"],
    }


@smoke.get("/genomics-only")
def genomics_only(
    user: Annotated[AuthContext, Depends(require_roles("genomics"))],
) -> dict:
    return {"ok": True, "roles": list(user.roles)}


def test_request_without_cookie_is_401() -> None:
    with TestClient(smoke) as client:
        assert client.get("/whoami").status_code == 401


def test_request_with_garbage_cookie_is_401() -> None:
    with TestClient(smoke) as client:
        client.cookies.set(ACCESS_COOKIE, "not-a-jwt")
        assert client.get("/whoami").status_code == 401


def _smoke_client(mint_token, factory, *roles: str) -> TestClient:
    client = TestClient(smoke)
    client.cookies.set(ACCESS_COOKIE, mint_token(factory(*roles)))
    return client


def test_authenticated_request_sets_identity(mint_token, _user_factory) -> None:
    client = _smoke_client(mint_token, _user_factory, "genomics")
    response = client.get("/whoami")
    assert response.status_code == 200
    body = response.json()
    assert body["set_uid"] == body["user_id"], "app.user_id must equal the acting user"
    assert body["set_roles"] == "genomics", "app.role_names must carry the user's roles"
    assert body["roles"] == ["genomics"]


def test_role_guard_allows_listed_role(mint_token, _user_factory) -> None:
    client = _smoke_client(mint_token, _user_factory, "genomics")
    response = client.get("/genomics-only")
    assert response.status_code == 200
    assert response.json()["roles"] == ["genomics"]


def test_role_guard_denies_other_roles_with_403(mint_token, _user_factory) -> None:
    client = _smoke_client(mint_token, _user_factory, "molecular")
    assert client.get("/genomics-only").status_code == 403


def test_admin_passes_every_guard(mint_token, _user_factory) -> None:
    client = _smoke_client(mint_token, _user_factory, "admin")
    response = client.get("/genomics-only")
    assert response.status_code == 200
    assert "admin" in response.json()["roles"]


def test_alembic_history_is_linear_single_head() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))
    heads = script.get_heads()
    assert heads == ["0002"], f"expected exactly one head 0002, got {heads}"

    chain = [rev.revision for rev in script.walk_revisions()]
    assert set(chain) == {"0001", "0002"}
