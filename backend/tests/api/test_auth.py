"""US1 auth paths (T021, SC-001).

Covers login success/failure (no user/password distinction), ``/auth/me``,
protected-without-cookie 401, refresh rotation + reuse-revokes-family, logout
then 401, and access-token expiry -> 401. Runs against real Postgres through
the real app; the session cookies are set ``Secure`` so the clients use an
https base URL.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import ACCESS_COOKIE, REFRESH_COOKIE
from app.main import app

pytestmark = pytest.mark.usefixtures("database_url")


def _client() -> TestClient:
    return TestClient(app, base_url="https://testserver")


def _login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_login_sets_cookies_and_me_returns_roles(account_factory) -> None:
    account = account_factory("genomics")
    client = _client()

    response = _login(client, account["email"], account["password"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == account["email"]
    assert body["roles"] == ["genomics"]

    set_cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith(f"{ACCESS_COOKIE}=") and "HttpOnly" in c for c in set_cookies)
    assert any(c.startswith(f"{REFRESH_COOKIE}=") and "HttpOnly" in c for c in set_cookies)
    assert all("Secure" in c for c in set_cookies if c.startswith((ACCESS_COOKIE, REFRESH_COOKIE)))
    assert any("SameSite=strict" in c or "SameSite=Strict" in c for c in set_cookies)

    me = client.get("/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["roles"] == ["genomics"]
    assert me.json()["id"] == str(account["id"])


def test_login_failure_has_no_user_password_distinction(account_factory) -> None:
    account = account_factory("genomics")
    client = _client()

    wrong_password = _login(client, account["email"], "not-the-password")
    unknown_user = _login(client, f"missing-{uuid.uuid4().hex[:8]}@test.local", "whatever")

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert client.cookies.get(ACCESS_COOKIE) is None


def test_protected_route_without_cookie_is_401() -> None:
    client = _client()
    assert client.get("/auth/me").status_code == 401


def test_refresh_rotates_and_reuse_revokes_family(account_factory) -> None:
    account = account_factory("admin")
    client = _client()
    assert _login(client, account["email"], account["password"]).status_code == 200

    first_refresh = client.cookies.get(REFRESH_COOKIE)
    assert first_refresh

    rotated = client.post("/auth/refresh")
    assert rotated.status_code == 200, rotated.text
    second_refresh = client.cookies.get(REFRESH_COOKIE)
    assert second_refresh and second_refresh != first_refresh

    # Replaying the already-rotated token is treated as reuse → the whole
    # family is revoked and the request refused.
    client.cookies.set(REFRESH_COOKIE, first_refresh, path="/auth")
    reuse = client.post("/auth/refresh")
    assert reuse.status_code == 401

    # The current token is now dead too — the family was revoked.
    client.cookies.set(REFRESH_COOKIE, second_refresh, path="/auth")
    assert client.post("/auth/refresh").status_code == 401


def test_refresh_without_cookie_is_401() -> None:
    client = _client()
    assert client.post("/auth/refresh").status_code == 401


def test_logout_clears_session_and_me_is_401(account_factory) -> None:
    account = account_factory("trf")
    client = _client()
    assert _login(client, account["email"], account["password"]).status_code == 200
    assert client.get("/auth/me").status_code == 200

    logout = client.post("/auth/logout")
    assert logout.status_code == 204

    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/refresh").status_code == 401


def test_expired_access_token_is_401(account_factory) -> None:
    account = account_factory("molecular")
    client = _client()
    expired = jwt.encode(
        {
            "sub": str(account["id"]),
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        get_settings().JWT_SECRET,
        algorithm="HS256",
    )

    client.cookies.set(ACCESS_COOKIE, expired)
    assert client.get("/auth/me").status_code == 401
