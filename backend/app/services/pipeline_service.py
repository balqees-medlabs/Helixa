"""Pipeline result recording + stage driving (Article V.3; contracts/stage-driving.md).

Recording is idempotent (FR-016, D7): a repeat with the same ``idempotency_key``
returns the existing row without a second insert. Stage driving follows the
constitution mapping (research D2):

- ``ingest``/``ok`` → Stage 4 (``data_generation``) when the sample is at
  Stage 3; otherwise the result is held as a no-op advance.
- Stage 7 (``data_conversion_qc``) requires a ``conversion``/``ok`` result
  **and** a latest coverage ``pass`` (T024/T025); a BELOW verdict blocks it
  (contracts/stage-driving.md rule 4).

Advances reuse the existing optimistic-concurrency update in
``workflow_service`` — a stale or double report finds ``rowcount = 0`` and
does not double-advance. The automation passes ``actor_roles=("admin",)`` to
the advance because the reporting pipeline drives the stage; the acting
identity is attributed to the service user (Article IV.2).
"""

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.services import workflow_service


class PipelineSampleNotFound(Exception):
    """No pipeline_samples row is linked to the given workflow Sample id."""


class PipelineResultNotFound(Exception):
    """No pipeline result with that id."""


_PIPELINE_SAMPLE_SELECT = (
    "SELECT id, pipeline_state FROM pipeline_samples WHERE sample_id = :sample_id"
)

_CONVERSION_OK = (
    "SELECT 1 FROM pipeline_results "
    "WHERE pipeline_sample_id = :pipeline_sample_id AND kind = 'conversion' "
    "AND status = 'ok' LIMIT 1"
)

_LATEST_COVERAGE_VERDICT = (
    "SELECT verdict FROM coverage_results "
    "WHERE pipeline_sample_id = :pipeline_sample_id "
    "ORDER BY reported_at DESC LIMIT 1"
)


def _pipeline_sample(conn: Connection, sample_id: uuid.UUID) -> dict:
    row = (
        conn.execute(text(_PIPELINE_SAMPLE_SELECT), {"sample_id": str(sample_id)})
        .mappings()
        .first()
    )
    if row is None:
        raise PipelineSampleNotFound(str(sample_id))
    return dict(row)


def get_pipeline_sample(conn: Connection, sample_id: uuid.UUID) -> dict:
    return _pipeline_sample(conn, sample_id)


def get_result(conn: Connection, result_id: uuid.UUID) -> dict:
    row = (
        conn.execute(
            text(
                "SELECT id, pipeline_sample_id, kind, status, read_length, q30, reads_assigned_pct, "
                "source_run_ids, integrity_ok, plan_match, detail, reported_by, reported_at, "
                "idempotency_key FROM pipeline_results WHERE id = :id"
            ),
            {"id": str(result_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise PipelineResultNotFound(str(result_id))
    return dict(row)


def _find_idempotent(conn: Connection, idempotency_key: str) -> tuple[dict, bool] | None:
    row = (
        conn.execute(
            text("SELECT id FROM pipeline_results WHERE idempotency_key = :key"),
            {"key": idempotency_key},
        )
        .scalars()
        .first()
    )
    if row is None:
        return None
    return get_result(conn, row), False


def record_ingest(
    conn: Connection,
    *,
    sample_id: uuid.UUID,
    idempotency_key: str,
    status: str = "ok",
    detail: dict | None = None,
    reporter_id: uuid.UUID,
) -> tuple[dict, bool]:
    """Record an ``ingest`` result and drive Stage 4 (data generation).

    Returns ``(record, created)``; ``created=False`` means the idempotency
    key already had a row (D7) and no advance is re-attempted.
    The advance only fires from Stage 3 (Article V.3); out-of-order/duplicate
    reports are held, not advanced (contracts/stage-driving.md rule 1).
    """
    existing = _find_idempotent(conn, idempotency_key)
    if existing is not None:
        return existing

    pipeline_sample = _pipeline_sample(conn, sample_id)
    result_id = conn.execute(
        text(
            "INSERT INTO pipeline_results (pipeline_sample_id, kind, status, reported_by, "
            "idempotency_key, detail) VALUES (:psid, 'ingest', :status, :reporter, "
            ":key, :detail) RETURNING id"
        ),
        {
            "psid": str(pipeline_sample["id"]),
            "status": status,
            "reporter": str(reporter_id),
            "key": idempotency_key,
            "detail": json.dumps(detail or {}),
        },
    ).scalar_one()

    # Only basecalls-present (ingest/ok) drives Stage 4 — a failed ingest is
    # recorded but never advances (contracts/stage-driving.md).
    if status == "ok":
        _drive_stage_4(conn, sample_id, actor_id=reporter_id)
    return get_result(conn, result_id), True


def record_conversion(
    conn: Connection,
    *,
    sample_id: uuid.UUID,
    idempotency_key: str,
    status: str = "ok",
    read_length: int | None = None,
    q30: float | None = None,
    reads_assigned_pct: float | None = None,
    detail: dict | None = None,
    reporter_id: uuid.UUID,
) -> tuple[dict, bool]:
    """Record a ``conversion`` result (Stage 7 needs conversion **and** pass)."""
    existing = _find_idempotent(conn, idempotency_key)
    if existing is not None:
        return existing

    pipeline_sample = _pipeline_sample(conn, sample_id)
    result_id = conn.execute(
        text(
            "INSERT INTO pipeline_results (pipeline_sample_id, kind, status, read_length, q30, "
            "reads_assigned_pct, reported_by, idempotency_key, detail) "
            "VALUES (:psid, 'conversion', :status, :read_length, :q30, :reads_assigned_pct, "
            ":reporter, :key, :detail) RETURNING id"
        ),
        {
            "psid": str(pipeline_sample["id"]),
            "status": status,
            "read_length": read_length,
            "q30": q30,
            "reads_assigned_pct": reads_assigned_pct,
            "reporter": str(reporter_id),
            "key": idempotency_key,
            "detail": json.dumps(detail or {}),
        },
    ).scalar_one()
    return get_result(conn, result_id), True


def record_augmentation(
    conn: Connection,
    *,
    sample_id: uuid.UUID,
    idempotency_key: str,
    status: str = "ok",
    source_run_ids: list[uuid.UUID] | None = None,
    integrity_ok: bool | None = None,
    plan_match: bool | None = None,
    detail: dict | None = None,
    reporter_id: uuid.UUID,
) -> tuple[dict, bool]:
    """Record an ``augmentation`` result — append-only (T024, T033).

    Merge-plan validation of ``source_run_ids``/``plan_match`` lands with T033
    (Phase 5, US3); the insert itself is always recorded here.
    """
    existing = _find_idempotent(conn, idempotency_key)
    if existing is not None:
        return existing

    pipeline_sample = _pipeline_sample(conn, sample_id)
    result_id = conn.execute(
        text(
            "INSERT INTO pipeline_results (pipeline_sample_id, kind, status, source_run_ids, "
            "integrity_ok, plan_match, reported_by, idempotency_key, detail) "
            "VALUES (:psid, 'augmentation', :status, :source_run_ids, :integrity_ok, :plan_match, "
            ":reporter, :key, :detail) RETURNING id"
        ),
        {
            "psid": str(pipeline_sample["id"]),
            "status": status,
            "source_run_ids": [str(run_id) for run_id in source_run_ids or []],
            "integrity_ok": integrity_ok,
            "plan_match": plan_match,
            "reporter": str(reporter_id),
            "key": idempotency_key,
            "detail": json.dumps(detail or {}),
        },
    ).scalar_one()
    return get_result(conn, result_id), True


def record_coverage(
    conn: Connection,
    *,
    sample_id: uuid.UUID,
    idempotency_key: str,
    read_pairs: int,
    yield_gb: float,
    depth_x: float,
    target_x: int,
    reporter_id: uuid.UUID,
) -> dict:
    """Record a coverage result; ``verdict`` is derived (T025).

    ``pass`` iff ``depth_x >= target_x``. A pass with a prior ``conversion``/ok
    drives Stage 7 (contracts/stage-driving.md rule 3); a below verdict blocks
    it (rule 4).
    """
    existing_id = (
        conn.execute(
            text("SELECT id FROM coverage_results WHERE idempotency_key = :key"),
            {"key": idempotency_key},
        )
        .scalars()
        .first()
    )
    if existing_id is not None:
        # Idempotent repeat (D7/FR-016): return the existing row, no re-insert
        # and no second Stage 7 advance.
        return get_coverage(conn, existing_id)

    pipeline_sample = _pipeline_sample(conn, sample_id)
    verdict = "pass" if depth_x >= target_x else "below"
    result_id = conn.execute(
        text(
            "INSERT INTO coverage_results (pipeline_sample_id, read_pairs, yield_gb, depth_x, "
            "target_x, verdict, reported_by, idempotency_key) "
            "VALUES (:psid, :read_pairs, :yield_gb, :depth_x, :target_x, :verdict, :reporter, "
            ":key) RETURNING id"
        ),
        {
            "psid": str(pipeline_sample["id"]),
            "read_pairs": read_pairs,
            "yield_gb": yield_gb,
            "depth_x": depth_x,
            "target_x": target_x,
            "verdict": verdict,
            "reporter": str(reporter_id),
            "key": idempotency_key,
        },
    ).scalar_one()

    if verdict == "pass":
        _drive_stage_7(conn, sample_id, actor_id=reporter_id)

    return get_coverage(conn, result_id)


def get_coverage(conn: Connection, result_id: uuid.UUID) -> dict:
    row = (
        conn.execute(
            text(
                "SELECT id, pipeline_sample_id, read_pairs, yield_gb, depth_x, target_x, verdict, "
                "reported_by, reported_at, idempotency_key FROM coverage_results WHERE id = :id"
            ),
            {"id": str(result_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise PipelineResultNotFound(str(result_id))
    return dict(row)


def list_coverage(conn: Connection, sample_id: uuid.UUID, limit: int = 100) -> list[dict]:
    """Coverage history, latest first (the latest verdict governs the gate)."""
    pipeline_sample = _pipeline_sample(conn, sample_id)
    rows = (
        conn.execute(
            text(
                "SELECT id, pipeline_sample_id, read_pairs, yield_gb, depth_x, target_x, verdict, "
                "reported_by, reported_at, idempotency_key FROM coverage_results "
                "WHERE pipeline_sample_id = :psid ORDER BY reported_at DESC, id DESC LIMIT :limit"
            ),
            {"psid": str(pipeline_sample["id"]), "limit": limit},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def list_results(conn: Connection, sample_id: uuid.UUID, limit: int = 100) -> list[dict]:
    pipeline_sample = _pipeline_sample(conn, sample_id)
    rows = (
        conn.execute(
            text(
                "SELECT id, pipeline_sample_id, kind, status, read_length, q30, reads_assigned_pct, "
                "source_run_ids, integrity_ok, plan_match, detail, reported_by, reported_at, "
                "idempotency_key FROM pipeline_results "
                "WHERE pipeline_sample_id = :psid ORDER BY reported_at DESC, id DESC LIMIT :limit"
            ),
            {"psid": str(pipeline_sample["id"]), "limit": limit},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def _drive_stage_4(conn: Connection, sample_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
    try:
        workflow_service.advance(
            conn,
            sample_id,
            from_stage=3,
            to_stage=4,
            actor_id=actor_id,
            actor_roles=("admin",),
            note="Basecalls present (ingest/ok) — Stage 4 data generation (Article V.3)",
        )
    except workflow_service.StageConflict:
        # Hold, don't skip: the sample is not at Stage 3 yet (contracts/stage-driving.md).
        return


def _drive_stage_7(conn: Connection, sample_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
    pipeline_sample = _pipeline_sample(conn, sample_id)
    has_conversion = conn.execute(
        text(_CONVERSION_OK), {"pipeline_sample_id": pipeline_sample["id"]}
    ).scalar()
    if not has_conversion:
        return
    latest = (
        conn.execute(text(_LATEST_COVERAGE_VERDICT), {"pipeline_sample_id": pipeline_sample["id"]})
        .mappings()
        .first()
    )
    if latest is None or latest["verdict"] != "pass":
        return
    try:
        workflow_service.advance(
            conn,
            sample_id,
            from_stage=6,
            to_stage=7,
            actor_id=actor_id,
            actor_roles=("admin",),
            note="Conversion ok + coverage pass — Stage 7 data conversion & QC (Article V.3)",
        )
    except workflow_service.StageConflict:
        # Hold until the sample reaches Stage 6 (TRF confirmation); the
        # result is recorded and re-checked on the next report.
        return
