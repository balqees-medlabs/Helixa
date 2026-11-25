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


def test_role_slugs_seeded(admin_conn) -> None:
    # Five human access roles (Article III.2) plus the non-human
    # pipeline-reporter machine role added in 0003 (Article II.4 / D-01).
    rows = admin_conn.execute(text("SELECT slug FROM roles ORDER BY slug")).fetchall()
    assert [row.slug for row in rows] == [
        "admin",
        "bioinformatics",
        "genomics",
        "molecular",
        "pipeline-reporter",
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


def test_exactly_one_system_actor_and_only_the_machine_identity(admin_conn) -> None:
    system = admin_conn.execute(
        text("SELECT is_system, email, is_active FROM users WHERE is_system")
    ).fetchall()
    assert len(system) == 1
    assert system[0].is_system is True
    assert system[0].email is None  # no credentials
    assert system[0].is_active is True

    # The only non-system user seeded is the non-human pipeline-reporter machine
    # identity (0003, D-01): no email/credentials, holds only that role. Still no
    # human admin is seeded here (FR-012).
    non_system = admin_conn.execute(
        text(
            "SELECT u.email, array_agg(r.slug ORDER BY r.slug) AS roles "
            "FROM users u "
            "LEFT JOIN user_roles ur ON ur.user_id = u.id "
            "LEFT JOIN roles r ON r.id = ur.role_id "
            "WHERE NOT u.is_system "
            "GROUP BY u.id, u.email"
        )
    ).fetchall()
    assert len(non_system) == 1
    assert non_system[0].email is None
    assert non_system[0].roles == ["pipeline-reporter"]


def test_one_default_calendar_seeded_empty_of_holidays(admin_conn) -> None:
    calendars = admin_conn.execute(text("SELECT weekend_days FROM working_calendar")).fetchall()
    assert len(calendars) == 1
    assert list(calendars[0].weekend_days) == [5]

    holidays = admin_conn.execute(text("SELECT count(*) FROM holidays")).scalar_one()
    assert holidays == 0
