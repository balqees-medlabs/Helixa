"""Sequencing run intake + run-sample linkage (FR-001/002/003, FR-006; D4).

Records ``sequencing_runs`` (all intake attributes) and bridges each produced
sample to the already-registered workflow ``samples`` row (FR-002, D4): run
intake never creates a workflow Sample and refuses with a clear reason when no
registered Sample matches (422). Duplicate ``ngs_sample_id`` intake is a 409
(FR-004). Target defaults: 30× clinical (G) / 15× lifestyle (R) (FR-003).
Every write is attributed via the transaction-scoped acting identity.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

DEFAULT_TARGET_BY_TYPE = {"G": 30, "R": 15}

_RUN_SELECT = """
SELECT id, run_folder, instrument, project, run_side, run_date, storage_location,
       readiness, cycle_r1, cycle_r2, cycle_i1, cycle_i2, created_by, created_at
FROM sequencing_runs
"""


class RunExists(Exception):
    """A run with the same folder is already recorded."""


class RunNotFound(Exception):
    """No run with that id."""


class SampleLinkRefused(Exception):
    """The requested linked Sample is not a registered workflow Sample (FR-002)."""


class SampleDuplicateNgsId(Exception):
    """A run sample with the same ngs_sample_id already exists (FR-004)."""


def _apply_target_default(sample_type: str, coverage_target_x: int | None) -> int:
    if coverage_target_x is not None:
        return coverage_target_x
    return DEFAULT_TARGET_BY_TYPE[sample_type]


def create_run(
    conn: Connection,
    *,
    run_folder: str,
    instrument: str,
    created_by: uuid.UUID,
    project: str | None = None,
    run_side: str | None = None,
    run_date: str | None = None,
    storage_location: str | None = None,
    cycle_r1: int | None = None,
    cycle_r2: int | None = None,
    cycle_i1: int | None = None,
    cycle_i2: int | None = None,
) -> dict:
    try:
        run_id = conn.execute(
            text(
                "INSERT INTO sequencing_runs (run_folder, instrument, project, run_side, "
                "run_date, storage_location, cycle_r1, cycle_r2, cycle_i1, cycle_i2, created_by) "
                "VALUES (:run_folder, :instrument, :project, :run_side, CAST(:run_date AS date), "
                ":storage_location, :cycle_r1, :cycle_r2, :cycle_i1, :cycle_i2, :created_by) "
                "RETURNING id"
            ),
            {
                "run_folder": run_folder,
                "instrument": instrument,
                "project": project,
                "run_side": run_side,
                "run_date": run_date,
                "storage_location": storage_location,
                "cycle_r1": cycle_r1,
                "cycle_r2": cycle_r2,
                "cycle_i1": cycle_i1,
                "cycle_i2": cycle_i2,
                "created_by": str(created_by),
            },
        ).scalar_one()
    except IntegrityError as exc:
        raise RunExists(run_folder) from exc
    return get_run(conn, run_id)


def get_run(conn: Connection, run_id: uuid.UUID) -> dict:
    row = (
        conn.execute(text(f"{_RUN_SELECT} WHERE id = :run_id"), {"run_id": str(run_id)})
        .mappings()
        .first()
    )
    if row is None:
        raise RunNotFound(str(run_id))
    return dict(row)


def list_runs(conn: Connection, limit: int = 200, offset: int = 0) -> list[dict]:
    rows = (
        conn.execute(
            text(f"{_RUN_SELECT} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
            {"limit": limit, "offset": offset},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def record_sample(
    conn: Connection,
    *,
    run_id: uuid.UUID,
    sample_id: uuid.UUID,
    ngs_sample_id: str,
    sample_type: str,
    coverage_target_x: int | None,
    created_by: uuid.UUID,
    vendor_id: uuid.UUID | None = None,
) -> dict:
    # Link-to-existing enforcement (FR-002/D4): the workflow Sample must be
    # registered; run intake never creates one. The run itself must exist.
    get_run(conn, run_id)
    linked = conn.execute(
        text("SELECT 1 FROM samples WHERE id = :sample_id"), {"sample_id": str(sample_id)}
    ).scalar()
    if linked is None:
        raise SampleLinkRefused(
            f"Sample {sample_id} is not a registered workflow Sample; register the sample first."
        )
    if (
        conn.execute(
            text("SELECT 1 FROM pipeline_samples WHERE ngs_sample_id = :ngs LIMIT 1"),
            {"ngs": ngs_sample_id},
        ).scalar()
        is not None
    ):
        raise SampleDuplicateNgsId(ngs_sample_id)
    target_x = _apply_target_default(sample_type, coverage_target_x)
    try:
        pipeline_sample_id = conn.execute(
            text(
                "INSERT INTO pipeline_samples (sample_id, ngs_sample_id, sample_type, "
                "coverage_target_x, vendor_id, created_by) "
                "VALUES (:sample_id, :ngs, :type, :target_x, :vendor_id, :created_by) "
                "RETURNING id"
            ),
            {
                "sample_id": str(sample_id),
                "ngs": ngs_sample_id,
                "type": sample_type,
                "target_x": target_x,
                "vendor_id": str(vendor_id) if vendor_id else None,
                "created_by": str(created_by),
            },
        ).scalar_one()
    except IntegrityError as exc:
        raise SampleDuplicateNgsId(ngs_sample_id) from exc
    return get_pipeline_sample(conn, pipeline_sample_id)


def get_pipeline_sample(conn: Connection, pipeline_sample_id: uuid.UUID) -> dict:
    row = (
        conn.execute(
            text(
                "SELECT id, sample_id, ngs_sample_id, sample_type, coverage_target_x, vendor_id, "
                "pipeline_state, created_by, created_at FROM pipeline_samples WHERE id = :id"
            ),
            {"id": str(pipeline_sample_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise SampleLinkRefused(str(pipeline_sample_id))
    return dict(row)


def export_runs_csv(conn: Connection, limit: int = 500, offset: int = 0) -> list[dict]:
    """CSV row data for GET /runs/export (FR-006): the run/sample list."""
    return list_runs(conn, limit=limit, offset=offset)
