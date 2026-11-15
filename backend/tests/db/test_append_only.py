"""US1 tests: audit_log is append-only for every role.

Covers FR-003, SC-002 per contracts/audit-contract.md: UPDATE and DELETE on
``audit_log`` raise for every role and leave the row count unchanged.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.usefixtures("database_url")

ROLES = ("admin", "genomics", "trf", "molecular", "bioinformatics")


@pytest.fixture
def system_user_id(admin_conn) -> uuid.UUID:
    """The seeded system actor — a valid user id for audit attribution."""
    return admin_conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()


@pytest.fixture
def audit_row_id(admin_conn) -> uuid.UUID:
    """Any existing audit row (e.g. the audited creation of the system actor)."""
    return admin_conn.execute(text("SELECT id FROM audit_log LIMIT 1")).scalar_one()


@pytest.mark.parametrize("role", ROLES)
def test_update_on_audit_log_is_rejected(
    admin_engine: Engine,
    set_context,
    system_user_id: uuid.UUID,
    audit_row_id: uuid.UUID,
    role: str,
) -> None:
    with admin_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, [role])
        before = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()

        with pytest.raises(DBAPIError):
            conn.execute(
                text("UPDATE audit_log SET entity_table = entity_table WHERE id = :id"),
                {"id": str(audit_row_id)},
            )
        # exception aborts the transaction; nothing was changed

    with admin_engine.connect() as conn, conn.begin():
        after = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()
        intact = conn.execute(
            text("SELECT count(*) FROM audit_log WHERE id = :id"), {"id": str(audit_row_id)}
        ).scalar_one()

    assert after == before
    assert intact == 1


@pytest.mark.parametrize("role", ROLES)
def test_delete_on_audit_log_is_rejected(
    admin_engine: Engine,
    set_context,
    system_user_id: uuid.UUID,
    audit_row_id: uuid.UUID,
    role: str,
) -> None:
    with admin_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, [role])
        before = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()

        with pytest.raises(DBAPIError):
            conn.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": str(audit_row_id)})

    with admin_engine.connect() as conn, conn.begin():
        after = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()

    assert after == before
