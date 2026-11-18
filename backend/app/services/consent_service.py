"""Per-sample consent/documentation checklist (FR-011).

Completeness of every ``required`` item is the molecular-processing gate. The
standard checklist below is seeded on registration so a sample can never reach
molecular processing with no consent documented (the gate is never vacuously
satisfied). Adjust the list to the lab's consent policy.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.services.sample_service import get_sample

# Required consent/documentation items seeded on sample registration.
REQUIRED_CONSENT_ITEMS: tuple[str, ...] = (
    "signed_consent",  # patient informed-consent form signed
    "id_verified",  # patient identity verified
    "requisition_received",  # test requisition / order form received
)


def seed_checklist(conn: Connection, sample_id: uuid.UUID) -> None:
    """Insert the standard required checklist (incomplete) for a new sample.

    Idempotent: re-seeding leaves existing items untouched. The caller's
    identity must already be set so the audit trigger attributes the inserts.
    """
    for item in REQUIRED_CONSENT_ITEMS:
        conn.execute(
            text(
                "INSERT INTO consent_items (sample_id, item, required, complete) "
                "VALUES (:sample_id, :item, true, false) "
                "ON CONFLICT (sample_id, item) DO NOTHING"
            ),
            {"sample_id": sample_id, "item": item},
        )


def _items(conn: Connection, sample_id: uuid.UUID) -> list[dict]:
    rows = (
        conn.execute(
            text(
                "SELECT item, required, complete, completed_by, completed_at "
                "FROM consent_items WHERE sample_id = :sample_id ORDER BY item"
            ),
            {"sample_id": sample_id},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def required_complete(conn: Connection, sample_id: uuid.UUID) -> bool:
    """True only when at least one required item exists and all are complete.

    The ``required > 0`` guard means a sample with no consent on record never
    passes the molecular gate (defence in depth alongside the seeded checklist).
    """
    row = (
        conn.execute(
            text(
                "SELECT count(*) FILTER (WHERE required) AS required_total, "
                "       count(*) FILTER (WHERE required AND NOT complete) AS incomplete "
                "FROM consent_items WHERE sample_id = :sample_id"
            ),
            {"sample_id": sample_id},
        )
        .mappings()
        .one()
    )
    return row["required_total"] > 0 and row["incomplete"] == 0


def get_consent(conn: Connection, sample_id: uuid.UUID) -> dict:
    get_sample(conn, sample_id)  # 404 when hidden/absent
    return {
        "sample_id": sample_id,
        "items": _items(conn, sample_id),
        "required_complete": required_complete(conn, sample_id),
    }


def set_items(
    conn: Connection,
    sample_id: uuid.UUID,
    items: list[dict],
    actor_id: uuid.UUID,
) -> dict:
    get_sample(conn, sample_id)

    for item in items:
        conn.execute(
            text(
                "INSERT INTO consent_items "
                "(sample_id, item, required, complete, completed_by, completed_at) "
                "VALUES (:sample_id, :item, :required, :complete, :actor_id, "
                "        CASE WHEN :complete THEN now() ELSE NULL END) "
                "ON CONFLICT (sample_id, item) DO UPDATE SET "
                "  required = EXCLUDED.required, "
                "  complete = EXCLUDED.complete, "
                "  completed_by = EXCLUDED.completed_by, "
                "  completed_at = EXCLUDED.completed_at"
            ),
            {
                "sample_id": sample_id,
                "item": item["item"],
                "required": item["required"],
                "complete": item["complete"],
                "actor_id": actor_id if item["complete"] else None,
            },
        )

    return get_consent(conn, sample_id)
