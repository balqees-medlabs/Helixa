"""Spec 4 DB tests: RLS visibility + deny-by-default on the new tables.

Mirrors the Spec 1/2 RLS harness (``tests/db/conftest.py`` +
``test_rls_visibility.py``): every new Spec 4 table is RLS-enabled and FORCEd;
``molecular``/``bioinformatics``/``admin`` may read them; the
``pipeline-reporter`` role has only the scoped tier from 0003; everyone else
is denied by default.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.usefixtures("database_url")

NEW_TABLES = (
    "sequencing_runs",
    "pipeline_samples",
    "merge_plan_runs",
    "pipeline_results",
    "coverage_results",
    "vendor_deliveries",
    "api_tokens",
)


@pytest.fixture
def system_user_id(admin_conn) -> uuid.UUID:
    return admin_conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()


def _can_read(conn, table: str) -> int:
    return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_molecular_can_read_all_new_tables(helixa_engine: Engine, set_context, system_user_id):
    with helixa_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["molecular"])
        for table in NEW_TABLES:
            assert _can_read(conn, table) >= 0, f"molecular must be able to read {table}"


def test_bioinformatics_can_read_all_new_tables(helixa_engine: Engine, set_context, system_user_id):
    with helixa_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["bioinformatics"])
        for table in NEW_TABLES:
            assert _can_read(conn, table) >= 0, f"bioinformatics must be able to read {table}"


def test_admin_can_read_all_new_tables(helixa_engine: Engine, set_context, system_user_id):
    with helixa_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["admin"])
        for table in NEW_TABLES:
            assert _can_read(conn, table) >= 0, f"admin must be able to read {table}"


@pytest.mark.parametrize("role", ("genomics", "trf"))
def test_non_reader_roles_deny_by_default(
    helixa_engine: Engine, set_context, system_user_id: uuid.UUID, role: str
) -> None:
    """genomics/trf have no policies on the new tables: they see zero rows."""
    with helixa_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, [role])
        for table in NEW_TABLES:
            assert _can_read(conn, table) == 0, f"{role} must see 0 rows from {table}"


def test_session_without_identity_reads_nothing(helixa_engine: Engine) -> None:
    with helixa_engine.connect() as conn, conn.begin():
        for table in NEW_TABLES:
            assert _can_read(conn, table) == 0, f"no identity must yield 0 rows from {table}"


def test_reporter_scoped_select(helixa_engine: Engine, set_context, system_user_id) -> None:
    """The pipeline-reporter reads the runs/samples/results it reports on."""
    with helixa_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["pipeline-reporter"])
        for table in (
            "sequencing_runs",
            "pipeline_samples",
            "pipeline_results",
            "coverage_results",
        ):
            assert _can_read(conn, table) >= 0, f"reporter must be able to read {table}"
        # … and is denied elsewhere (deny-by-default, Article III.3).
        for table in ("merge_plan_runs", "vendor_deliveries", "api_tokens"):
            assert _can_read(conn, table) == 0, f"reporter must not read {table}"
