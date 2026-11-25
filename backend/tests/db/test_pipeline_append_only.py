"""Spec 4 DB tests: ``pipeline_results`` and ``coverage_results`` are append-only.

Covers Article IV.3: UPDATE and DELETE on both tables raise for every role and
leave the rows intact. Rows are created as ``admin`` (``pipeline_samples``) and
``pipeline-reporter`` (``pipeline_results`` / ``coverage_results`` — the
scoped-insert tier of 0003).
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.usefixtures("database_url")

APPEND_ONLY_TABLES = {"pipeline_results": "status", "coverage_results": "verdict"}
ROLES = ("admin", "genomics", "trf", "molecular", "bioinformatics")


@pytest.fixture
def system_user_id(admin_conn) -> uuid.UUID:
    return admin_conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()


@pytest.fixture
def reporter_user_id(admin_conn) -> uuid.UUID:
    return admin_conn.execute(
        text(
            "SELECT u.id FROM users u "
            "JOIN user_roles ur ON ur.user_id = u.id "
            "JOIN roles r ON r.id = ur.role_id "
            "WHERE r.slug = 'pipeline-reporter' LIMIT 1"
        )
    ).scalar_one()


@pytest.fixture
def pipeline_sample_id(admin_engine, system_user_id, set_context) -> uuid.UUID:
    # Seed on its own committed transaction so the separate reporter connection
    # (append_only_rows) can see the pipeline_sample via its FK. fn_audit()
    # refuses un-attributed writes, so set the acting identity first.
    with admin_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ("admin",))
        sample_id = conn.execute(
            text(
                "INSERT INTO samples (case_id, current_stage_id) "
                "VALUES (:cid, (SELECT id FROM stages WHERE position = 1)) RETURNING id"
            ),
            {"cid": f"CASE-{uuid.uuid4()}"},
        ).scalar_one()
        return conn.execute(
            text(
                "INSERT INTO pipeline_samples (sample_id, ngs_sample_id, sample_type, "
                "coverage_target_x, created_by) VALUES (:s, :ngs, 'G', 30, :uid) RETURNING id"
            ),
            {
                "s": str(sample_id),
                "ngs": f"TEST-{uuid.uuid4().hex[:8]}",
                "uid": str(system_user_id),
            },
        ).scalar_one()


@pytest.fixture
def append_only_rows(helixa_engine, set_context, reporter_user_id, pipeline_sample_id) -> dict:
    """One row per append-only table, inserted as the pipeline-reporter."""
    with helixa_engine.connect() as conn, conn.begin():
        set_context(conn, reporter_user_id, ["pipeline-reporter"])
        pipeline_result_id = conn.execute(
            text(
                "INSERT INTO pipeline_results (pipeline_sample_id, kind, status, reported_by, "
                "idempotency_key) VALUES (:s, 'ingest', 'ok', :uid, :key) RETURNING id"
            ),
            {
                "s": str(pipeline_sample_id),
                "uid": str(reporter_user_id),
                "key": f"ik-{uuid.uuid4().hex}",
            },
        ).scalar_one()
        coverage_result_id = conn.execute(
            text(
                "INSERT INTO coverage_results (pipeline_sample_id, read_pairs, yield_gb, depth_x, "
                "target_x, verdict, reported_by, idempotency_key) "
                "VALUES (:s, 1000, 12.5, 30, 30, 'pass', :uid, :key) RETURNING id"
            ),
            {
                "s": str(pipeline_sample_id),
                "uid": str(reporter_user_id),
                "key": f"ck-{uuid.uuid4().hex}",
            },
        ).scalar_one()
    return {
        "pipeline_results": pipeline_result_id,
        "coverage_results": coverage_result_id,
    }


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_update_on_append_only_tables_is_rejected(
    admin_engine: Engine,
    set_context,
    system_user_id: uuid.UUID,
    append_only_rows: dict,
    table: str,
    role: str,
) -> None:
    row_id = append_only_rows[table]
    with admin_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, [role])
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    f"UPDATE {table} SET {APPEND_ONLY_TABLES[table]} = {APPEND_ONLY_TABLES[table]} WHERE id = :id"
                ),
                {"id": str(row_id)},
            )

    with admin_engine.connect() as conn, conn.begin():
        count = conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE id = :id"), {"id": str(row_id)}
        ).scalar_one()
    assert count == 1


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_delete_on_append_only_tables_is_rejected(
    admin_engine: Engine,
    set_context,
    system_user_id: uuid.UUID,
    append_only_rows: dict,
    table: str,
    role: str,
) -> None:
    row_id = append_only_rows[table]
    with admin_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, [role])
        with pytest.raises(DBAPIError):
            conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": str(row_id)})

    with admin_engine.connect() as conn, conn.begin():
        count = conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE id = :id"), {"id": str(row_id)}
        ).scalar_one()
    assert count == 1
