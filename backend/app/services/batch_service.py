"""Batch grouping with per-member isolated advance (FR-012).

Each member's transition runs in its own savepoint so one member failing its
gate, carrying a stale stage, or lacking permission neither aborts nor blocks
the others. The batch operation is not atomic by design: outcomes are reported
per member.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.services import workflow_service
from app.services.sample_service import SampleNotFound, get_sample


class BatchNotFound(Exception):
    """No batch with that id."""


def _member_ids(conn: Connection, batch_id: uuid.UUID) -> list[uuid.UUID]:
    rows = (
        conn.execute(
            text(
                "SELECT sample_id FROM batch_members WHERE batch_id = :batch_id ORDER BY sample_id"
            ),
            {"batch_id": batch_id},
        )
        .scalars()
        .all()
    )
    return list(rows)


def get_batch(conn: Connection, batch_id: uuid.UUID) -> dict:
    row = (
        conn.execute(
            text("SELECT id, name, created_by FROM batches WHERE id = :batch_id"),
            {"batch_id": batch_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise BatchNotFound(str(batch_id))
    batch = dict(row)
    batch["member_ids"] = _member_ids(conn, batch_id)
    return batch


def create_batch(conn: Connection, *, name: str, actor_id: uuid.UUID) -> dict:
    batch_id = conn.execute(
        text("INSERT INTO batches (name, created_by) VALUES (:name, :created_by) RETURNING id"),
        {"name": name, "created_by": actor_id},
    ).scalar_one()
    return get_batch(conn, batch_id)


def add_members(conn: Connection, batch_id: uuid.UUID, sample_ids: list[uuid.UUID]) -> dict:
    get_batch(conn, batch_id)
    for sample_id in sample_ids:
        get_sample(conn, sample_id)
        conn.execute(
            text(
                "INSERT INTO batch_members (batch_id, sample_id) "
                "VALUES (:batch_id, :sample_id) "
                "ON CONFLICT (batch_id, sample_id) DO NOTHING"
            ),
            {"batch_id": batch_id, "sample_id": sample_id},
        )
    return get_batch(conn, batch_id)


def advance_batch(
    conn: Connection,
    batch_id: uuid.UUID,
    *,
    from_stage: int | None,
    to_stage: int | None,
    note: str | None,
    actor_id: uuid.UUID,
    actor_roles: tuple[str, ...],
) -> list[dict]:
    get_batch(conn, batch_id)
    members = _member_ids(conn, batch_id)

    results: list[dict] = []
    for sample_id in members:
        observed = from_stage
        try:
            with conn.begin_nested():
                if observed is None:
                    observed = get_sample(conn, sample_id)["current_stage"]["position"]
                result = workflow_service.advance(
                    conn,
                    sample_id,
                    from_stage=observed,
                    to_stage=to_stage,
                    note=note,
                    actor_id=actor_id,
                    actor_roles=actor_roles,
                )
            results.append(
                {
                    "sample_id": sample_id,
                    "status": "advanced",
                    "detail": None,
                    "from_stage": observed,
                    "to_stage": result.to_stage,
                }
            )
        except workflow_service.StageGateFailed as exc:
            results.append(_failed(sample_id, "gate_failed", str(exc), observed))
        except workflow_service.StageConflict as exc:
            results.append(_failed(sample_id, "conflict", str(exc), observed))
        except workflow_service.StagePermissionDenied as exc:
            results.append(_failed(sample_id, "forbidden", str(exc), observed))
        except SampleNotFound as exc:
            results.append(_failed(sample_id, "not_found", str(exc), observed))
    return results


def _failed(sample_id: uuid.UUID, status: str, detail: str, from_stage: int | None) -> dict:
    return {
        "sample_id": sample_id,
        "status": status,
        "detail": detail,
        "from_stage": from_stage,
        "to_stage": None,
    }
