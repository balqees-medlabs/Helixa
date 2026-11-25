"""Pipeline result + coverage API (contracts/endpoints.md; FR-012..FR-016).

Machine-authenticated as ``pipeline-reporter`` (service_auth) for the
reporting posts; reads for molecular/bioinformatics/admin via RLS.
Idempotent repeats (same ``idempotency_key``) return the existing record with
200 (D7) and never double-advance the workflow (T024, contracts/stage-driving.md).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, current_user, get_tx
from app.core.service_auth import current_reporter
from app.schemas.pipeline import (
    CoverageCreate,
    CoverageOut,
    PipelineResultCreate,
    PipelineResultOut,
)
from app.services import pipeline_service

router = APIRouter(prefix="/samples", tags=["pipeline"])

Reporter = Annotated[AuthContext, Depends(current_reporter)]
AnyUser = Annotated[AuthContext, Depends(current_user)]
Conn = Annotated[Connection, Depends(get_tx)]


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


@router.post("/{sample_id}/pipeline-results", response_model=PipelineResultOut, status_code=201)
def post_pipeline_result(
    sample_id: uuid.UUID,
    body: PipelineResultCreate,
    user: Reporter,
    conn: Conn,
    response: Response,
) -> PipelineResultOut:
    try:
        if body.kind == "ingest":
            result, created = pipeline_service.record_ingest(
                conn,
                sample_id=sample_id,
                idempotency_key=body.idempotency_key,
                status=body.status,
                detail=body.detail or None,
                reporter_id=user.user_id,
            )
        elif body.kind == "conversion":
            result, created = pipeline_service.record_conversion(
                conn,
                sample_id=sample_id,
                idempotency_key=body.idempotency_key,
                status=body.status,
                read_length=body.read_length,
                q30=body.q30,
                reads_assigned_pct=body.reads_assigned_pct,
                detail=body.detail or None,
                reporter_id=user.user_id,
            )
        else:  # augmentation
            result, created = pipeline_service.record_augmentation(
                conn,
                sample_id=sample_id,
                idempotency_key=body.idempotency_key,
                status=body.status,
                source_run_ids=body.source_run_ids,
                integrity_ok=body.integrity_ok,
                plan_match=body.plan_match,
                detail=body.detail or None,
                reporter_id=user.user_id,
            )
    except pipeline_service.PipelineSampleNotFound as exc:
        raise _not_found(str(exc)) from exc
    if not created:
        response.status_code = 200  # idempotent repeat (D7): no new record, no advance
    return PipelineResultOut(**result)


@router.post("/{sample_id}/coverage", response_model=CoverageOut, status_code=201)
def post_coverage(
    sample_id: uuid.UUID, body: CoverageCreate, user: Reporter, conn: Conn
) -> CoverageOut:
    try:
        result = pipeline_service.record_coverage(
            conn,
            sample_id=sample_id,
            idempotency_key=body.idempotency_key,
            read_pairs=body.read_pairs,
            yield_gb=body.yield_gb,
            depth_x=body.depth_x,
            target_x=body.target_x,
            reporter_id=user.user_id,
        )
    except pipeline_service.PipelineSampleNotFound as exc:
        raise _not_found(str(exc)) from exc
    return CoverageOut(**result)


@router.get("/{sample_id}/coverage", response_model=list[CoverageOut])
def list_coverage(sample_id: uuid.UUID, _user: AnyUser, conn: Conn) -> list[CoverageOut]:
    try:
        rows = pipeline_service.list_coverage(conn, sample_id)
    except pipeline_service.PipelineSampleNotFound as exc:
        raise _not_found(str(exc)) from exc
    return [CoverageOut(**row) for row in rows]


@router.get("/{sample_id}/pipeline-results", response_model=list[PipelineResultOut])
def list_pipeline_results(
    sample_id: uuid.UUID, _user: AnyUser, conn: Conn
) -> list[PipelineResultOut]:
    try:
        rows = pipeline_service.list_results(conn, sample_id)
    except pipeline_service.PipelineSampleNotFound as exc:
        raise _not_found(str(exc)) from exc
    return [PipelineResultOut(**row) for row in rows]
