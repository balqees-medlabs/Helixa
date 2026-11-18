"""Turnaround metrics and stage-SLA maintenance (FR-015, SC-005).

Durations are read from the recorded ``sample_stage_events.duration_hours``
(the Spec 1 trigger fills them); the in-progress stage is measured from its
``entered_at``. Targets are the 18-day calendar target and the 45-working-day
baseline from the configured working calendar. Editing a stage SLA changes
future measurement only — recorded durations are never rewritten.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

TARGET_DAYS = 18
BASELINE_WORKING_DAYS = 45
DEFAULT_WEEKEND_DAYS = (5,)  # Friday


class StageNotFound(Exception):
    """No stage with that id."""


def update_stage_sla(conn: Connection, stage_id: uuid.UUID, sla_days: int) -> dict:
    updated = (
        conn.execute(
            text(
                "UPDATE stage_sla SET sla_days = :sla_days, updated_at = now() "
                "WHERE stage_id = :stage_id "
                "RETURNING stage_id, sla_days, updated_at"
            ),
            {"stage_id": stage_id, "sla_days": sla_days},
        )
        .mappings()
        .first()
    )
    if updated is None:
        raise StageNotFound(str(stage_id))

    stage = (
        conn.execute(
            text("SELECT position, slug, name FROM stages WHERE id = :stage_id"),
            {"stage_id": stage_id},
        )
        .mappings()
        .one()
    )
    return {
        "stage_id": updated["stage_id"],
        "position": stage["position"],
        "slug": stage["slug"],
        "name": stage["name"],
        "sla_days": updated["sla_days"],
        "updated_at": updated["updated_at"],
    }


def _working_days_elapsed(
    start: datetime,
    end: datetime,
    weekend_days: set[int],
    holidays: set[date],
) -> int:
    if end <= start:
        return 0
    count = 0
    day = start.date()
    last = end.date()
    while day < last:
        if day.isoweekday() not in weekend_days and day not in holidays:
            count += 1
        day += timedelta(days=1)
    return count


def _durations(events: list[dict], now: datetime) -> list[tuple[dict, float | None]]:
    measured: list[tuple[dict, float | None]] = []
    for index, event in enumerate(events):
        if index + 1 < len(events):
            following = events[index + 1]
            recorded = following["duration_hours"]
            if recorded is None:
                delta = following["entered_at"] - event["entered_at"]
                hours: float | None = delta.total_seconds() / 3600
            else:
                hours = float(recorded)
        else:
            delta = now - event["entered_at"]
            hours = delta.total_seconds() / 3600
        measured.append((event, round(hours, 2)))
    return measured


def compute_tat_metrics(conn: Connection, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)

    calendar = (
        conn.execute(text("SELECT weekend_days FROM working_calendar ORDER BY id LIMIT 1"))
        .scalars()
        .first()
    )
    weekend_days = set(calendar if calendar is not None else DEFAULT_WEEKEND_DAYS)
    holidays = set(conn.execute(text("SELECT day FROM holidays")).scalars().all())

    vendors = [
        dict(row)
        for row in conn.execute(
            text("SELECT id, name, tat_days, tat_anchor FROM vendors ORDER BY name")
        )
        .mappings()
        .all()
    ]
    vendors_by_id = {vendor["id"]: vendor for vendor in vendors}

    events_by_sample: dict[uuid.UUID, list[dict]] = {}
    for row in (
        conn.execute(
            text(
                "SELECT e.sample_id, e.entered_at, e.duration_hours, "
                "st.id AS stage_id, st.position, st.slug, st.name, sla.sla_days "
                "FROM sample_stage_events e "
                "JOIN stages st ON st.id = e.stage_id "
                "LEFT JOIN stage_sla sla ON sla.stage_id = st.id "
                "ORDER BY e.sample_id, e.entered_at, e.id"
            )
        )
        .mappings()
        .all()
    ):
        events_by_sample.setdefault(row["sample_id"], []).append(dict(row))

    sample_rows = (
        conn.execute(
            text(
                "SELECT s.id, s.case_id, s.status, s.received_at, s.vendor_id, "
                "st.id AS stage_id, st.position, st.slug, st.name "
                "FROM samples s JOIN stages st ON st.id = s.current_stage_id "
                "ORDER BY s.received_at, s.id"
            )
        )
        .mappings()
        .all()
    )

    samples: list[dict] = []
    vendor_counts: dict[uuid.UUID, dict] = {
        vendor["id"]: {"assigned": 0, "breached": 0} for vendor in vendors
    }

    for sample in sample_rows:
        events = events_by_sample.get(sample["id"], [])
        stages = []
        for event, hours in _durations(events, now):
            sla_days = event["sla_days"]
            stages.append(
                {
                    "stage_id": event["stage_id"],
                    "position": event["position"],
                    "slug": event["slug"],
                    "name": event["name"],
                    "sla_days": sla_days,
                    "duration_hours": hours,
                    "breached": (
                        hours > sla_days * 24
                        if sla_days is not None and hours is not None
                        else None
                    ),
                }
            )

        elapsed_calendar_days = round((now - sample["received_at"]).total_seconds() / 86400, 2)
        working_days = _working_days_elapsed(sample["received_at"], now, weekend_days, holidays)

        vendor_metric = None
        vendor = vendors_by_id.get(sample["vendor_id"])
        if vendor is not None:
            if vendor["tat_anchor"] == "receipt":
                anchor_at = sample["received_at"]
            else:
                anchor_at = next(
                    (event["entered_at"] for event in events if event["position"] == 4),
                    None,
                )
            elapsed_vendor_days = (
                round((now - anchor_at).total_seconds() / 86400, 2)
                if anchor_at is not None
                else None
            )
            breached = (
                elapsed_vendor_days > vendor["tat_days"]
                if elapsed_vendor_days is not None
                else None
            )
            vendor_metric = {
                "id": vendor["id"],
                "name": vendor["name"],
                "tat_days": vendor["tat_days"],
                "tat_anchor": vendor["tat_anchor"],
                "anchor_at": anchor_at,
                "elapsed_days": elapsed_vendor_days,
                "breached": breached,
            }
            vendor_counts[vendor["id"]]["assigned"] += 1
            if breached:
                vendor_counts[vendor["id"]]["breached"] += 1

        samples.append(
            {
                "sample_id": sample["id"],
                "case_id": sample["case_id"],
                "status": sample["status"],
                "current_stage": {
                    "id": sample["stage_id"],
                    "position": sample["position"],
                    "slug": sample["slug"],
                    "name": sample["name"],
                },
                "received_at": sample["received_at"],
                "elapsed_calendar_days": elapsed_calendar_days,
                "elapsed_working_days": working_days,
                "target_days": TARGET_DAYS,
                "target_breached": elapsed_calendar_days > TARGET_DAYS,
                "baseline_working_days": BASELINE_WORKING_DAYS,
                "baseline_breached": working_days > BASELINE_WORKING_DAYS,
                "stages": stages,
                "vendor": vendor_metric,
            }
        )

    return {
        "generated_at": now,
        "target_days": TARGET_DAYS,
        "baseline_working_days": BASELINE_WORKING_DAYS,
        "samples": samples,
        "vendors": [
            {
                "vendor_id": vendor["id"],
                "name": vendor["name"],
                "tat_days": vendor["tat_days"],
                "tat_anchor": vendor["tat_anchor"],
                "assigned_samples": vendor_counts[vendor["id"]]["assigned"],
                "breached_samples": vendor_counts[vendor["id"]]["breached"],
            }
            for vendor in vendors
        ],
    }
