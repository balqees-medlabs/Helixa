"""US2 tests: the seeded 8-stage workflow and default turnaround calendar.

Covers FR-005, FR-006, FR-008: exactly 8 ordered stages with unique positions
1..8 and the default SLA split summing to the 18-day internal target; one
default ``working_calendar`` row with ``weekend_days = {5}`` (Friday) and no
holidays seeded.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.usefixtures("database_url")

EXPECTED_SLA = {
    "received": 1,
    "consent_documentation": 2,
    "molecular_processing": 4,
    "data_generation": 4,
    "trf_preparation": 2,
    "trf_confirmation": 1,
    "data_conversion_qc": 2,
    "report_upload_archive": 2,
}


@pytest.fixture
def system_user_id(admin_conn) -> uuid.UUID:
    return admin_conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()


def test_exactly_eight_ordered_stages_with_default_slas(admin_conn) -> None:
    rows = admin_conn.execute(
        text(
            "SELECT s.position, s.slug, s.name, sl.sla_days "
            "FROM stages s JOIN stage_sla sl ON sl.stage_id = s.id "
            "ORDER BY s.position"
        )
    ).fetchall()

    assert len(rows) == 8
    assert [row.position for row in rows] == list(range(1, 9))
    assert [row.slug for row in rows] == list(EXPECTED_SLA)
    # FR-006: defaults sum to the 18-day internal target.
    assert {row.slug: row.sla_days for row in rows} == EXPECTED_SLA
    assert sum(row.sla_days for row in rows) == 18
    # Every stage keeps its human-readable label.
    assert all(row.name for row in rows)


def test_stage_position_is_unique(admin_conn, set_context, system_user_id) -> None:
    seeded = admin_conn.execute(text("SELECT count(*) FROM stages")).scalar_one()
    assert seeded == 8  # guard: the probe must fail on the constraint, not a missing table

    set_context(admin_conn, system_user_id, ["admin"])
    with pytest.raises(DBAPIError):
        admin_conn.execute(
            text("INSERT INTO stages (position, slug, name) VALUES (:pos, :slug, :name)"),
            {"pos": 1, "slug": f"probe_{uuid.uuid4()}", "name": "probe"},
        )


def test_one_default_working_calendar_with_friday_weekend(admin_conn) -> None:
    calendars = admin_conn.execute(text("SELECT weekend_days FROM working_calendar")).fetchall()

    assert len(calendars) == 1
    assert list(calendars[0].weekend_days) == [5]  # Friday per the Medlabs work week

    holidays = admin_conn.execute(text("SELECT count(*) FROM holidays")).scalar_one()
    assert holidays == 0  # seeded empty; administrators add entries later
