"""US4 tests: the seed applied with the schema is complete and known-good.

Covers FR-011, FR-012, SC-003: after seeding there are exactly 5 roles, 8
ordered stages with SLAs, the 4 named vendors with their TAT anchors, exactly
one ``system`` actor with no credentials, one default calendar with no
holidays, and **zero** non-system users (no human admin is seeded).
"""

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.usefixtures("database_url")

EXPECTED_VENDORS = {
    "Arcensus": (4, "receipt"),
    "Reviity": (28, "receipt"),
    "Sefdecode": (5, "receipt"),
    "Centogene": (30, "sequencing"),
}


def test_exactly_five_roles_seeded(admin_conn) -> None:
    rows = admin_conn.execute(text("SELECT slug FROM roles ORDER BY slug")).fetchall()
    assert [row.slug for row in rows] == [
        "admin",
        "bioinformatics",
        "genomics",
        "molecular",
        "trf",
    ]


def test_exactly_eight_ordered_stages_with_slas_seeded(admin_conn) -> None:
    rows = admin_conn.execute(
        text(
            "SELECT s.position, sl.sla_days FROM stages s "
            "JOIN stage_sla sl ON sl.stage_id = s.id ORDER BY s.position"
        )
    ).fetchall()
    assert [row.position for row in rows] == list(range(1, 9))
    assert sum(row.sla_days for row in rows) == 18


def test_four_named_vendors_with_tat_anchors_seeded(admin_conn) -> None:
    rows = admin_conn.execute(text("SELECT name, tat_days, tat_anchor FROM vendors")).fetchall()
    assert {row.name: (row.tat_days, row.tat_anchor) for row in rows} == EXPECTED_VENDORS


def test_exactly_one_system_actor_and_zero_human_users(admin_conn) -> None:
    users = admin_conn.execute(text("SELECT is_system, email, is_active FROM users")).fetchall()
    assert len(users) == 1
    assert users[0].is_system is True
    assert users[0].email is None  # no credentials; auth arrives in M2
    assert users[0].is_active is True

    humans = admin_conn.execute(text("SELECT count(*) FROM users WHERE NOT is_system")).scalar_one()
    assert humans == 0  # FR-012: no human admin is seeded here


def test_one_default_calendar_seeded_empty_of_holidays(admin_conn) -> None:
    calendars = admin_conn.execute(text("SELECT weekend_days FROM working_calendar")).fetchall()
    assert len(calendars) == 1
    assert list(calendars[0].weekend_days) == [5]

    holidays = admin_conn.execute(text("SELECT count(*) FROM holidays")).scalar_one()
    assert holidays == 0
