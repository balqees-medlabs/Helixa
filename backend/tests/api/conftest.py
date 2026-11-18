"""API test harness (T020).

Reuses the Spec 1 database fixtures (``tests/db/conftest.py``): one disposable
Postgres 16 with the helixa_app role provisioned and migrations applied to
head (``0002`` included). On top of that it provides:

- env bootstrap (JWT secret, test DATABASE_URL) for the FastAPI app
- a ``TestClient`` whose request engine connects as ``helixa_app``
- a user factory (writes via the admin engine, audited as the system actor)
  and fixtures that mint a signed-in client per role (admin, genomics, trf,
  molecular, bioinformatics) by crafting the access-cookie directly — the
  login flow itself is exercised by the Phase 3 auth tests.
"""

import os
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core import deps
from app.core.config import Settings
from app.core.security import ACCESS_COOKIE, encode_access_token
from app.db.session_context import set_session_context
from app.main import app
from tests.db.conftest import TEST_APP_PASSWORD

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-0123456789abcdef0123456789")
# The request engine connects as the harness's helixa_app role (deps.get_engine
# replaces the admin DATABASE_URL credentials with APP_DB_USER/APP_DB_PASSWORD).
os.environ.setdefault("APP_DB_PASSWORD", TEST_APP_PASSWORD)

# Re-export the Spec 1 database fixtures so pytest discovers them for
# tests/api as well (conftest fixtures are directory-scoped). The aliases are
# only consumed via fixture parameters; ruff flags the pattern as F401/F811.
from tests.db.conftest import admin_engine as _db_admin_engine  # noqa: E402,F401
from tests.db.conftest import admin_url as _db_admin_url  # noqa: E402,F401
from tests.db.conftest import database_url as _db_database_url  # noqa: E402,F401

ROLE_SLUGS = ("admin", "genomics", "trf", "molecular", "bioinformatics")


@pytest.fixture(scope="session")
def admin_url(_db_admin_url: str) -> Iterator[str]:  # noqa: F811
    yield _db_admin_url


@pytest.fixture(scope="session")
def database_url(_db_database_url: str) -> Iterator[str]:  # noqa: F811
    yield _db_database_url


@pytest.fixture(scope="session")
def admin_engine(_db_admin_engine: Engine) -> Iterator[Engine]:  # noqa: F811
    yield _db_admin_engine


@pytest.fixture(scope="session")
def client(database_url: str) -> Iterator[TestClient]:
    """TestClient over the real app, pointed at the disposable Postgres."""
    deps.reset_engine()
    with TestClient(app) as test_client:
        yield test_client
    deps.reset_engine()


@pytest.fixture(scope="session")
def _user_factory(admin_engine: Engine) -> Iterator[Callable[..., uuid.UUID]]:
    """Create an active user with the given role slugs; return its id."""

    def _create(*slugs: str, display_name: str | None = None) -> uuid.UUID:
        email = f"{(slugs or ('user',))[0]}-{uuid.uuid4().hex[:12]}@test.local"
        name = display_name or f"Test user {email.split('@')[0]}"
        with admin_engine.connect() as conn, conn.begin():
            sys_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
            set_session_context(conn, sys_id, ("admin",))
            user_id = conn.execute(
                text("INSERT INTO users (email, display_name) VALUES (:email, :name) RETURNING id"),
                {"email": email, "name": name},
            ).scalar_one()
            for slug in slugs:
                conn.execute(
                    text(
                        "INSERT INTO user_roles (user_id, role_id) "
                        "SELECT :user_id, id FROM roles WHERE slug = :slug"
                    ),
                    {"user_id": str(user_id), "slug": slug},
                )
        return user_id

    yield _create


def _signed_client(app_obj, user_id: uuid.UUID) -> TestClient:
    test_client = TestClient(app_obj)
    test_client.cookies.set(ACCESS_COOKIE, encode_access_token(user_id))
    return test_client


@pytest.fixture(scope="session")
def mint_token() -> Callable[[uuid.UUID], str]:
    """Mint a signed access-token string for a user id."""
    return encode_access_token


# The per-role session clients sign in against the real app (which gains its
# routers in Phase 3); Phase 2 checkpoint tests build their own clients against
# the throwaway smoke app using mint_token + _user_factory.


@pytest.fixture(scope="session")
def admin_client(_user_factory) -> Iterator[TestClient]:
    yield _signed_client(app, _user_factory("admin"))


@pytest.fixture(scope="session")
def genomics_client(_user_factory) -> Iterator[TestClient]:
    yield _signed_client(app, _user_factory("genomics"))


@pytest.fixture(scope="session")
def trf_client(_user_factory) -> Iterator[TestClient]:
    yield _signed_client(app, _user_factory("trf"))


@pytest.fixture(scope="session")
def molecular_client(_user_factory) -> Iterator[TestClient]:
    yield _signed_client(app, _user_factory("molecular"))


@pytest.fixture(scope="session")
def bioinformatics_client(_user_factory) -> Iterator[TestClient]:
    yield _signed_client(app, _user_factory("bioinformatics"))


@pytest.fixture(scope="session")
def make_signed_client(_user_factory) -> Callable[..., TestClient]:
    """Mint a signed-in client against the real app, any role combination."""

    def _make(*slugs: str) -> TestClient:
        return _signed_client(app, _user_factory(*slugs))

    return _make


@pytest.fixture(scope="session")
def app_settings(database_url: str) -> Settings:
    """The effective test settings (env DATABASE_URL, test JWT secret)."""
    return Settings()
