"""US4 tests: the schema is reproducible and cleanly rebuildable.

Covers FR-016, SC-005: ``alembic downgrade base`` followed by
``alembic upgrade head`` leaves an identical schema with no errors, and the
full seed is back in place.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.usefixtures("database_url")

BACKEND_DIR = Path(__file__).resolve().parents[2]

COLUMNS_QUERY = text(
    "SELECT table_name, column_name, data_type, is_nullable "
    "FROM information_schema.columns "
    "WHERE table_schema = 'public' "
    "ORDER BY table_name, column_name"
)
TABLES_QUERY = text(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
    "ORDER BY table_name"
)


def _schema_snapshot(conn) -> tuple[list[str], list[tuple]]:
    tables = [row[0] for row in conn.execute(TABLES_QUERY)]
    columns = [tuple(row) for row in conn.execute(COLUMNS_QUERY)]
    return tables, columns


def test_downgrade_base_then_upgrade_head_reproduces_schema(
    admin_url: str, admin_engine: Engine
) -> None:
    with admin_engine.connect() as conn:
        before = _schema_snapshot(conn)

    # The rebuild must run without errors; alembic raises on failure.
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", admin_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    with admin_engine.connect() as conn:
        after = _schema_snapshot(conn)
        assert before == after, "schema changed across a downgrade/upgrade cycle"

        # The seed is fully restored after the rebuild (FR-011).
        assert conn.execute(text("SELECT count(*) FROM roles")).scalar_one() == 6
        assert conn.execute(text("SELECT count(*) FROM stages")).scalar_one() == 8
        assert conn.execute(text("SELECT count(*) FROM vendors")).scalar_one() == 4
        # System actor (0001) + the non-human pipeline-reporter machine identity (0003).
        assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 2
        assert conn.execute(text("SELECT count(*) FROM working_calendar")).scalar_one() == 1
