"""US1 tests: the audit trigger records every change in the same transaction.

Covers FR-001, FR-002, FR-004, SC-001 per contracts/audit-contract.md:
exactly one same-transaction ``audit_log`` row per INSERT/UPDATE/DELETE on a
tracked table, ``actor_id = app.user_id``, ``job_id`` when ``app.job_id`` is
set, ``before``/``after`` payloads, and refusal of un-attributed writes.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.usefixtures("database_url")


@pytest.fixture
def system_user_id(admin_conn) -> uuid.UUID:
    """The seeded system actor — a valid user id for audit attribution."""
    return admin_conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()


def test_insert_writes_exactly_one_audit_row(
    admin_conn, set_context, system_user_id: uuid.UUID
) -> None:
    set_context(admin_conn, system_user_id, ["admin"])

    job_pk = admin_conn.execute(
        text("INSERT INTO jobs (kind) VALUES (:kind) RETURNING id"), {"kind": "portal_push"}
    ).scalar_one()

    rows = admin_conn.execute(
        text(
            "SELECT actor_id, job_id, action, entity_table, entity_id, before, after "
            "FROM audit_log WHERE entity_id = :entity_id"
        ),
        {"entity_id": str(job_pk)},
    ).fetchall()

    assert len(rows) == 1
    row = rows[0]
    assert row.actor_id == system_user_id
    assert row.job_id is None
    assert row.action == "INSERT"
    assert row.entity_table == "jobs"
    assert row.entity_id == job_pk
    assert row.before is None
    assert row.after["kind"] == "portal_push"


def test_audit_row_rolls_back_with_the_change(
    admin_engine: Engine, set_context, system_user_id: uuid.UUID
) -> None:
    rolled_back_pk: uuid.UUID
    with admin_engine.connect() as conn:
        conn.begin()  # transaction explicitly rolled back below, never committed
        set_context(conn, system_user_id, ["admin"])
        rolled_back_pk = conn.execute(
            text("INSERT INTO jobs (kind) VALUES (:kind) RETURNING id"),
            {"kind": "portal_push"},
        ).scalar_one()
        conn.rollback()  # the audit row must not survive

    with admin_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["admin"])
        committed_pk = conn.execute(
            text("INSERT INTO jobs (kind) VALUES (:kind) RETURNING id"),
            {"kind": "portal_push"},
        ).scalar_one()
        assert committed_pk != rolled_back_pk
        survivors = conn.execute(
            text("SELECT count(*) FROM audit_log WHERE entity_id = :entity_id"),
            {"entity_id": str(rolled_back_pk)},
        ).scalar_one()
    assert survivors == 0


def test_update_and_delete_write_before_and_after(
    admin_conn, set_context, system_user_id: uuid.UUID
) -> None:
    set_context(admin_conn, system_user_id, ["admin"])
    job_pk = admin_conn.execute(
        text("INSERT INTO jobs (kind) VALUES (:kind) RETURNING id"), {"kind": "portal_push"}
    ).scalar_one()

    admin_conn.execute(
        text("UPDATE jobs SET status = 'running' WHERE id = :id"), {"id": str(job_pk)}
    )
    admin_conn.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": str(job_pk)})

    update_row = admin_conn.execute(
        text(
            "SELECT before, after FROM audit_log WHERE entity_id = :entity_id AND action = 'UPDATE'"
        ),
        {"entity_id": str(job_pk)},
    ).fetchall()
    assert len(update_row) == 1
    assert update_row[0].before["status"] == "queued"
    assert update_row[0].after["status"] == "running"

    delete_row = admin_conn.execute(
        text(
            "SELECT before, after FROM audit_log WHERE entity_id = :entity_id AND action = 'DELETE'"
        ),
        {"entity_id": str(job_pk)},
    ).fetchall()
    assert len(delete_row) == 1
    assert delete_row[0].before["status"] == "running"
    assert delete_row[0].after is None


def test_job_id_is_recorded_from_session_context(
    admin_conn, set_context, system_user_id: uuid.UUID
) -> None:
    set_context(admin_conn, system_user_id, ["admin"])
    # app.job_id must reference a real jobs row (Spec 2 workers create these).
    job_id = admin_conn.execute(
        text("INSERT INTO jobs (kind) VALUES (:kind) RETURNING id"), {"kind": "portal_push"}
    ).scalar_one()

    set_context(admin_conn, system_user_id, ["admin"], job_id=job_id)
    job_pk = admin_conn.execute(
        text("INSERT INTO jobs (kind) VALUES (:kind) RETURNING id"), {"kind": "portal_push"}
    ).scalar_one()

    row = admin_conn.execute(
        text("SELECT actor_id, job_id FROM audit_log WHERE entity_id = :entity_id"),
        {"entity_id": str(job_pk)},
    ).fetchone()
    assert row is not None
    assert row.actor_id == system_user_id
    assert row.job_id == job_id


def test_write_without_user_id_raises(admin_engine: Engine) -> None:
    kind = f"unattributed_{uuid.uuid4()}"
    with pytest.raises(DBAPIError), admin_engine.connect() as conn, conn.begin():
        conn.execute(text("INSERT INTO jobs (kind) VALUES (:kind)"), {"kind": kind})

    # The aborted transaction must have left no job and no audit row behind.
    with admin_engine.connect() as conn, conn.begin():
        orphans = conn.execute(
            text("SELECT count(*) FROM jobs WHERE kind = :kind"), {"kind": kind}
        ).scalar_one()
    assert orphans == 0
