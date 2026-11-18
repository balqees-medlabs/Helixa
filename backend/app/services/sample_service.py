"""Sample registration, lookup and stage history (FR-008, data-model).

Runs on the request transaction under the caller's identity, so RLS scopes the
read and the Spec 1 triggers audit the write. Registration also opens the
stage-1 history event so the duration of the first advance is measurable.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError


class SampleNotFound(Exception):
    """No sample visible under the caller's identity."""


class SampleConflict(Exception):
    """The case id already exists."""


class UnknownVendor(Exception):
    """The supplied vendor id does not exist."""


_SAMPLE_SELECT = """
    SELECT s.id, s.case_id, s.external_ref, s.vendor_id, s.received_at, s.status,
           st.position AS stage_position, st.slug AS stage_slug, st.name AS stage_name
    FROM samples s
    JOIN stages st ON st.id = s.current_stage_id
"""


def _to_sample(row) -> dict:
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "external_ref": row["external_ref"],
        "vendor_id": row["vendor_id"],
        "received_at": row["received_at"],
        "status": row["status"],
        "current_stage": {
            "position": row["stage_position"],
            "slug": row["stage_slug"],
            "name": row["stage_name"],
        },
    }


def get_sample(conn: Connection, sample_id: uuid.UUID) -> dict:
    row = (
        conn.execute(
            text(f"{_SAMPLE_SELECT} WHERE s.id = :sample_id"),
            {"sample_id": sample_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise SampleNotFound(str(sample_id))
    return _to_sample(row)


def list_samples(conn: Connection, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    rows = (
        conn.execute(
            text(f"{_SAMPLE_SELECT} ORDER BY s.received_at DESC, s.id LIMIT :limit OFFSET :offset"),
            {"limit": limit, "offset": offset},
        )
        .mappings()
        .all()
    )
    total = conn.execute(text("SELECT count(*) FROM samples")).scalar_one()
    return [_to_sample(row) for row in rows], total


def register_sample(
    conn: Connection,
    *,
    case_id: str,
    external_ref: str | None,
    vendor_id: uuid.UUID | None,
    actor_id: uuid.UUID,
) -> dict:
    if vendor_id is not None:
        vendor_exists = conn.execute(
            text("SELECT 1 FROM vendors WHERE id = :vendor_id"), {"vendor_id": vendor_id}
        ).scalar()
        if not vendor_exists:
            raise UnknownVendor(str(vendor_id))

    stage = (
        conn.execute(text("SELECT id, position, slug, name FROM stages WHERE position = 1"))
        .mappings()
        .first()
    )
    if stage is None:
        raise RuntimeError("workflow stages are not seeded")

    try:
        sample_id = conn.execute(
            text(
                "INSERT INTO samples (case_id, external_ref, current_stage_id, vendor_id) "
                "VALUES (:case_id, :external_ref, :stage_id, :vendor_id) RETURNING id"
            ),
            {
                "case_id": case_id,
                "external_ref": external_ref,
                "stage_id": stage["id"],
                "vendor_id": vendor_id,
            },
        ).scalar_one()
    except IntegrityError as exc:
        raise SampleConflict(case_id) from exc

    # The received stage is the first history event; duration stays NULL until
    # the next advance (Spec 1 fn_stage_event_duration).
    conn.execute(
        text(
            "INSERT INTO sample_stage_events (sample_id, stage_id, actor_id) "
            "VALUES (:sample_id, :stage_id, :actor_id)"
        ),
        {"sample_id": sample_id, "stage_id": stage["id"], "actor_id": actor_id},
    )

    # Seed the standard required consent checklist so the molecular gate cannot
    # be satisfied without documented consent (local import avoids a cycle).
    from app.services import consent_service

    consent_service.seed_checklist(conn, sample_id)

    return get_sample(conn, sample_id)


def list_events(conn: Connection, sample_id: uuid.UUID) -> list[dict]:
    get_sample(conn, sample_id)  # 404 when hidden/absent
    rows = (
        conn.execute(
            text(
                "SELECT e.id, e.entered_at, e.duration_hours, e.actor_id, e.note, "
                "st.position, st.slug, st.name "
                "FROM sample_stage_events e JOIN stages st ON st.id = e.stage_id "
                "WHERE e.sample_id = :sample_id "
                "ORDER BY e.entered_at, e.id"
            ),
            {"sample_id": sample_id},
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": row["id"],
            "stage": {"position": row["position"], "slug": row["slug"], "name": row["name"]},
            "entered_at": row["entered_at"],
            "duration_hours": (
                float(row["duration_hours"]) if row["duration_hours"] is not None else None
            ),
            "actor_id": row["actor_id"],
            "note": row["note"],
        }
        for row in rows
    ]
