"""US2 tests: workflow model and sample progression.

Covers FR-003, FR-006, FR-007, FR-009, SC-007: advancing a sample records a
``sample_stage_events`` row with ``duration_hours``; UPDATE and DELETE on
``sample_stage_events`` raise for every role; editing ``stage_sla.sla_days``
never alters past durations; a duplicate ``samples.case_id`` is rejected.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.usefixtures("database_url")

ROLES = ("admin", "genomics", "trf", "molecular", "bioinformatics")


@pytest.fixture
def system_user_id(admin_conn) -> uuid.UUID:
    """The seeded system actor — a valid actor for audit attribution."""
    return admin_conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()


@pytest.fixture
def stage_ids(admin_conn) -> dict[int, uuid.UUID]:
    """The seeded stages, keyed by their fixed position (1..8)."""
    rows = admin_conn.execute(text("SELECT position, id FROM stages")).fetchall()
    return {row.position: row.id for row in rows}


@pytest.fixture
def sample_id(admin_conn, set_context, system_user_id, stage_ids) -> uuid.UUID:
    """A sample registered at stage 1 (received)."""
    set_context(admin_conn, system_user_id, ["admin"])
    return admin_conn.execute(
        text("INSERT INTO samples (case_id, current_stage_id) VALUES (:cid, :sid) RETURNING id"),
        {"cid": f"CASE-{uuid.uuid4()}", "sid": str(stage_ids[1])},
    ).scalar_one()


def test_advancing_a_sample_records_event_with_duration(
    admin_conn, set_context, system_user_id, stage_ids, sample_id: uuid.UUID
) -> None:
    set_context(admin_conn, system_user_id, ["admin"])

    # Enter stage 1: no prior event, so no duration can exist yet.
    admin_conn.execute(
        text(
            "INSERT INTO sample_stage_events (sample_id, stage_id, actor_id, entered_at) "
            "VALUES (:sample_id, :stage_id, :actor_id, :entered_at)"
        ),
        {
            "sample_id": str(sample_id),
            "stage_id": str(stage_ids[1]),
            "actor_id": str(system_user_id),
            "entered_at": datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        },
    )
    # Advance to stage 2 one day and four hours later.
    admin_conn.execute(
        text("UPDATE samples SET current_stage_id = :sid WHERE id = :id"),
        {"sid": str(stage_ids[2]), "id": str(sample_id)},
    )
    admin_conn.execute(
        text(
            "INSERT INTO sample_stage_events (sample_id, stage_id, actor_id, entered_at) "
            "VALUES (:sample_id, :stage_id, :actor_id, :entered_at)"
        ),
        {
            "sample_id": str(sample_id),
            "stage_id": str(stage_ids[2]),
            "actor_id": str(system_user_id),
            "entered_at": datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
        },
    )

    rows = admin_conn.execute(
        text(
            "SELECT stage_id, entered_at, duration_hours FROM sample_stage_events "
            "WHERE sample_id = :sample_id ORDER BY entered_at"
        ),
        {"sample_id": str(sample_id)},
    ).fetchall()

    assert len(rows) == 2
    assert rows[0].stage_id == stage_ids[1]
    assert rows[0].duration_hours is None  # nothing prior to measure from
    assert rows[1].stage_id == stage_ids[2]
    assert rows[1].duration_hours == 28.00  # 28h since the stage-1 event


@pytest.fixture
def event_id(admin_engine: Engine, set_context, system_user_id, stage_ids) -> uuid.UUID:
    """One committed sample + stage event (registered and entered at stage 1)."""
    with admin_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["admin"])
        sample_pk = conn.execute(
            text(
                "INSERT INTO samples (case_id, current_stage_id) VALUES (:cid, :sid) RETURNING id"
            ),
            {"cid": f"CASE-{uuid.uuid4()}", "sid": str(stage_ids[1])},
        ).scalar_one()
        return conn.execute(
            text(
                "INSERT INTO sample_stage_events (sample_id, stage_id, actor_id, entered_at) "
                "VALUES (:sample_id, :stage_id, :actor_id, :entered_at) RETURNING id"
            ),
            {
                "sample_id": str(sample_pk),
                "stage_id": str(stage_ids[1]),
                "actor_id": str(system_user_id),
                "entered_at": datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
            },
        ).scalar_one()


@pytest.mark.parametrize("role", ROLES)
def test_update_on_sample_stage_events_is_rejected(
    admin_engine: Engine,
    set_context,
    system_user_id,
    event_id: uuid.UUID,
    role: str,
) -> None:
    with admin_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, [role])
        with pytest.raises(DBAPIError):
            conn.execute(
                text("UPDATE sample_stage_events SET note = 'tampered' WHERE id = :id"),
                {"id": str(event_id)},
            )

    with admin_engine.connect() as conn, conn.begin():
        intact = conn.execute(
            text("SELECT count(*) FROM sample_stage_events WHERE id = :id AND note IS NULL"),
            {"id": str(event_id)},
        ).scalar_one()
    assert intact == 1


@pytest.mark.parametrize("role", ROLES)
def test_delete_on_sample_stage_events_is_rejected(
    admin_engine: Engine,
    set_context,
    system_user_id,
    event_id: uuid.UUID,
    role: str,
) -> None:
    with admin_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, [role])
        with pytest.raises(DBAPIError):
            conn.execute(
                text("DELETE FROM sample_stage_events WHERE id = :id"), {"id": str(event_id)}
            )

    with admin_engine.connect() as conn, conn.begin():
        surviving = conn.execute(
            text("SELECT count(*) FROM sample_stage_events WHERE id = :id"),
            {"id": str(event_id)},
        ).scalar_one()
    assert surviving == 1


def test_editing_sla_leaves_past_durations_unchanged(
    admin_conn, set_context, system_user_id, stage_ids, sample_id: uuid.UUID
) -> None:
    set_context(admin_conn, system_user_id, ["admin"])

    admin_conn.execute(
        text(
            "INSERT INTO sample_stage_events (sample_id, stage_id, actor_id, entered_at, duration_hours) "
            "VALUES (:sample_id, :stage_id, :actor_id, :entered_at, :duration)"
        ),
        {
            "sample_id": str(sample_id),
            "stage_id": str(stage_ids[1]),
            "actor_id": str(system_user_id),
            "entered_at": datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
            "duration": 12.5,
        },
    )

    # An administrator shortens/extends the SLA after samples have progressed.
    admin_conn.execute(
        text("UPDATE stage_sla SET sla_days = :days WHERE stage_id = :stage_id"),
        {"days": 9, "stage_id": str(stage_ids[1])},
    )

    duration = admin_conn.execute(
        text("SELECT duration_hours FROM sample_stage_events WHERE sample_id = :sample_id"),
        {"sample_id": str(sample_id)},
    ).scalar_one()
    assert duration == 12.5  # FR-006: past durations never change


def test_duplicate_case_id_is_rejected(
    admin_engine: Engine, set_context, system_user_id, stage_ids
) -> None:
    case_id = f"CASE-{uuid.uuid4()}"

    with admin_engine.connect() as conn, conn.begin():
        set_context(conn, system_user_id, ["admin"])
        conn.execute(
            text("INSERT INTO samples (case_id, current_stage_id) VALUES (:cid, :sid)"),
            {"cid": case_id, "sid": str(stage_ids[1])},
        )

    # SC-007: rejected every time, not just on the first attempt.
    for _ in range(3):
        with admin_engine.connect() as conn, conn.begin():
            set_context(conn, system_user_id, ["admin"])
            with pytest.raises(DBAPIError):
                conn.execute(
                    text("INSERT INTO samples (case_id, current_stage_id) VALUES (:cid, :sid)"),
                    {"cid": case_id, "sid": str(stage_ids[2])},
                )

    with admin_engine.connect() as conn, conn.begin():
        count = conn.execute(
            text("SELECT count(*) FROM samples WHERE case_id = :cid"), {"cid": case_id}
        ).scalar_one()
    assert count == 1
