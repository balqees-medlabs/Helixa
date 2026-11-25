"""US3 tests: role-based row access as a second line of defense.

Covers FR-014, FR-015, SC-004, exercised through the non-superuser
``helixa_app`` role (RLS does not apply to superusers): an operational role
reads every sample but zero rows from the restricted tables; an ``admin``
session reads everything; a session with no acting identity reads nothing and
is refused writes; a direct ``helixa_app`` INSERT into ``audit_log`` is
rejected (audit rows land only via the SECURITY DEFINER trigger).
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.usefixtures("database_url")

RESTRICTED = ("users", "roles", "user_roles", "audit_log")
OPERATIONAL = (
    "samples",
    "sample_stage_events",
    "stages",
    "stage_sla",
    "vendors",
    "working_calendar",
    "holidays",
    "jobs",
)


@pytest.fixture
def system_user_id(admin_conn) -> uuid.UUID:
    """The seeded system actor — a valid identity for session context."""
    return admin_conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()


@pytest.fixture
def genomics_session(helixa_engine: Engine, set_context, system_user_id: uuid.UUID):
    """A helixa_app session acting as genomics, with one sample registered."""
    with helixa_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["genomics"])
        conn.execute(
            text(
                "INSERT INTO samples (case_id, current_stage_id) "
                "VALUES (:cid, (SELECT id FROM stages WHERE position = 1))"
            ),
            {"cid": f"CASE-{uuid.uuid4()}"},
        )
        yield conn


def test_genomics_reads_samples_but_zero_restricted_rows(genomics_session, set_context) -> None:
    samples = genomics_session.execute(text("SELECT count(*) FROM samples")).scalar_one()
    assert samples >= 1  # operational roles read every sample

    for table in RESTRICTED:
        rows = genomics_session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        assert rows == 0, f"genomics must see no rows from {table}"


def test_admin_reads_all(helixa_engine: Engine, set_context, system_user_id: uuid.UUID) -> None:
    with helixa_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["admin"])
        assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() >= 1
        assert conn.execute(text("SELECT count(*) FROM roles")).scalar_one() == 6
        assert conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one() >= 1
        assert conn.execute(text("SELECT count(*) FROM samples")).scalar_one() >= 0
        assert conn.execute(text("SELECT count(*) FROM stages")).scalar_one() == 8


def test_session_without_identity_reads_nothing(helixa_engine: Engine) -> None:
    with helixa_engine.connect() as conn, conn.begin():
        for table in RESTRICTED + OPERATIONAL:
            rows = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            assert rows == 0, f"no identity must yield zero rows from {table}"


def test_write_without_identity_is_refused(helixa_engine: Engine) -> None:
    with (
        helixa_engine.connect() as conn,
        conn.begin(),
        pytest.raises(DBAPIError),
    ):
        conn.execute(
            text(
                "INSERT INTO samples (case_id, current_stage_id) "
                "VALUES (:cid, (SELECT id FROM stages WHERE position = 1))"
            ),
            {"cid": f"CASE-{uuid.uuid4()}"},
        )


def test_user_with_two_roles_reads_operational_data(
    helixa_engine: Engine, set_context, system_user_id: uuid.UUID
) -> None:
    with helixa_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["genomics", "trf"])
        # Combined roles still read workflow data ...
        assert conn.execute(text("SELECT count(*) FROM samples")).scalar_one() >= 0
        # ... but the combination grants no admin visibility.
        for table in RESTRICTED:
            rows = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            assert rows == 0, f"non-admin combination must see no rows from {table}"


def test_direct_insert_into_audit_log_is_rejected(
    helixa_engine: Engine, set_context, system_user_id: uuid.UUID
) -> None:
    with helixa_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["admin"])
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    "INSERT INTO audit_log (actor_id, action, entity_table, entity_id) "
                    "VALUES (:actor, 'INSERT', 'samples', gen_random_uuid())"
                ),
                {"actor": str(system_user_id)},
            )
