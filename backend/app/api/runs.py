"""Run & sample intake API (contracts/endpoints.md, FR-001..FR-006).

``POST /runs`` + ``POST /runs/{run_id}/samples`` are the molecular/admin
intake path; ``GET /runs`` + ``GET /runs/{run_id}`` are the list/detail views;
``GET /runs/export`` is the CSV export (FR-006). Writes go through
``runs_service`` (link-to-existing, duplicate id, target defaults) and are
audited by the same transaction.
"""

import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, get_tx, require_roles
from app.schemas.pipeline import PipelineSampleCreate, PipelineSampleOut, RunCreate, RunOut
from app.services import runs_service

router = APIRouter(prefix="/runs", tags=["runs"])

# Run intake + list/detail/export are the molecular/admin surface
# (contracts/endpoints.md). Bioinformatics-facing pipeline reads arrive in US3.
MolecularAdmin = Annotated[AuthContext, Depends(require_roles("molecular", "admin"))]
Conn = Annotated[Connection, Depends(get_tx)]

_RUN_OUT_FIELDS = (
    "run_folder",
    "instrument",
    "project",
    "run_side",
    "run_date",
    "storage_location",
    "readiness",
    "cycle_r1",
    "cycle_r2",
    "cycle_i1",
    "cycle_i2",
    "created_by",
    "created_at",
)


def _run_out(run: dict) -> RunOut:
    return RunOut(**{k: run[k] for k in RunOut.model_fields if k in run})


def _sample_out(sample: dict) -> PipelineSampleOut:
    return PipelineSampleOut(**sample)


@router.post("", response_model=RunOut, status_code=201)
def create_run(body: RunCreate, user: MolecularAdmin, conn: Conn) -> RunOut:
    try:
        run = runs_service.create_run(
            conn,
            run_folder=body.run_folder,
            instrument=body.instrument,
            project=body.project,
            run_side=body.run_side,
            run_date=body.run_date.isoformat() if body.run_date else None,
            storage_location=body.storage_location,
            cycle_r1=body.cycle_r1,
            cycle_r2=body.cycle_r2,
            cycle_i1=body.cycle_i1,
            cycle_i2=body.cycle_i2,
            created_by=user.user_id,
        )
    except runs_service.RunExists as exc:
        raise HTTPException(
            status_code=409, detail=f"A run with folder {exc} already exists"
        ) from exc
    return _run_out(run)


@router.get("", response_model=list[RunOut])
def list_runs(_user: MolecularAdmin, conn: Conn) -> list[RunOut]:
    return [_run_out(run) for run in runs_service.list_runs(conn)]


@router.get("/export")
def export_runs(_user: MolecularAdmin, conn: Conn) -> Response:
    """CSV export of the run/sample list (FR-006)."""
    rows = runs_service.export_runs_csv(conn)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_RUN_OUT_FIELDS)
    for row in rows:
        writer.writerow([row.get(col) for col in _RUN_OUT_FIELDS])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ngs-runs.csv"},
    )


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: uuid.UUID, _user: MolecularAdmin, conn: Conn) -> RunOut:
    try:
        return _run_out(runs_service.get_run(conn, run_id))
    except runs_service.RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@router.post("/{run_id}/samples", response_model=PipelineSampleOut, status_code=201)
def record_run_sample(
    run_id: uuid.UUID, body: PipelineSampleCreate, user: MolecularAdmin, conn: Conn
) -> PipelineSampleOut:
    try:
        sample = runs_service.record_sample(
            conn,
            run_id=run_id,
            sample_id=body.sample_id,
            ngs_sample_id=body.ngs_sample_id,
            sample_type=body.sample_type,
            coverage_target_x=body.coverage_target_x,
            created_by=user.user_id,
            vendor_id=body.vendor_id,
        )
    except runs_service.RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except runs_service.SampleLinkRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except runs_service.SampleDuplicateNgsId as exc:
        raise HTTPException(
            status_code=409, detail=f"A sample with ngs id {exc} already exists in this run"
        ) from exc
    return _sample_out(sample)
