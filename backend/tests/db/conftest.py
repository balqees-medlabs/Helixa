"""Pytest harness for the database test suite.

Spins up a disposable PostgreSQL 16 (testcontainers; or an externally provisioned
database via TEST_DATABASE_URL), creates the ``helixa_app`` role, applies
``alembic upgrade head``, and provides admin / helixa_app connections plus a
fixture to set the session context.

The ``helixa_app`` role is created BEFORE migrations run, mirroring production
order (infra/bootstrap-app-role.sh then alembic): later migrations GRANT
privileges to the role, so it must already exist at ``upgrade head``.

Note: TEST_DATABASE_URL, if provided, must be a SQLAlchemy URL using the psycopg
driver, e.g. ``postgresql+psycopg://user:pass@host:5432/db``.
"""

import os
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url

from app.db.session_context import set_session_context

BACKEND_DIR = Path(__file__).resolve().parents[2]

TEST_APP_ROLE = "helixa_app"
TEST_APP_PASSWORD = "helixa_app_test"


def _ensure_app_role(admin_url: str) -> None:
    """Create or update the non-superuser helixa_app role before migrations.

    TEST_APP_PASSWORD is a hardcoded test constant, so inlining it in the DDL is
    safe (CREATE/ALTER ROLE cannot take a bound parameter for PASSWORD).
    """
    create_sql = text(
        f"CREATE ROLE {TEST_APP_ROLE} LOGIN PASSWORD '{TEST_APP_PASSWORD}' "
        "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
    )
    alter_sql = text(
        f"ALTER ROLE {TEST_APP_ROLE} LOGIN PASSWORD '{TEST_APP_PASSWORD}' "
        "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
    )
    engine = create_engine(admin_url)
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
                {"role": TEST_APP_ROLE},
            ).scalar()
            conn.execute(alter_sql if exists else create_sql)
            conn.commit()
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def admin_url() -> Iterator[str]:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield url
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16", driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def database_url(admin_url: str) -> Iterator[str]:
    os.environ["DATABASE_URL"] = admin_url
    from alembic import command
    from alembic.config import Config

    # Role must exist before migrations (later migrations GRANT to it).
    _ensure_app_role(admin_url)

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", admin_url)
    command.upgrade(cfg, "head")
    yield admin_url
    command.downgrade(cfg, "base")


@pytest.fixture(scope="session")
def admin_engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def helixa_engine(database_url: str) -> Iterator[Engine]:
    url = make_url(database_url).set(username=TEST_APP_ROLE, password=TEST_APP_PASSWORD)
    engine = create_engine(url.render_as_string(hide_password=False))
    yield engine
    engine.dispose()


@pytest.fixture
def admin_conn(admin_engine: Engine) -> Iterator[Connection]:
    with admin_engine.connect() as conn, conn.begin():
        yield conn


@pytest.fixture
def helixa_conn(helixa_engine: Engine) -> Iterator[Connection]:
    with helixa_engine.connect() as conn, conn.begin():
        yield conn


@pytest.fixture
def set_context():
    """Set the session context (app.user_id / app.role_names / app.job_id) on a connection."""

    def _set(
        conn: Connection,
        user_id: uuid.UUID,
        role_names: Iterable[str],
        job_id: uuid.UUID | None = None,
    ) -> None:
        set_session_context(conn, user_id, role_names, job_id)

    return _set
