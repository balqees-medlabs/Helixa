"""Batch grouping and per-member advance (FR-012)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, current_user, get_tx, require_roles
from app.schemas.batches import (
    BatchAdvanceRequest,
    BatchCreate,
    BatchMembers,
    BatchOut,
    MemberAdvanceResult,
)
from app.services import batch_service
from app.services.sample_service import SampleNotFound

router = APIRouter(prefix="/batches", tags=["batches"])

BatchCreator = Annotated[AuthContext, Depends(require_roles("genomics", "bioinformatics"))]
AnyUser = Annotated[AuthContext, Depends(current_user)]
Conn = Annotated[Connection, Depends(get_tx)]


def _batch_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Batch not found")


@router.post("", response_model=BatchOut, status_code=201)
def create_batch(body: BatchCreate, user: BatchCreator, conn: Conn) -> BatchOut:
    return BatchOut(**batch_service.create_batch(conn, name=body.name, actor_id=user.user_id))


@router.post("/{batch_id}/members", response_model=BatchOut)
def add_members(
    batch_id: uuid.UUID, body: BatchMembers, _user: BatchCreator, conn: Conn
) -> BatchOut:
    try:
        batch = batch_service.add_members(conn, batch_id, body.sample_ids)
    except batch_service.BatchNotFound as exc:
        raise _batch_not_found() from exc
    except SampleNotFound as exc:
        raise HTTPException(status_code=404, detail="Sample not found") from exc
    return BatchOut(**batch)


@router.post("/{batch_id}/advance", response_model=list[MemberAdvanceResult])
def advance_batch(
    batch_id: uuid.UUID, body: BatchAdvanceRequest, user: AnyUser, conn: Conn
) -> list[MemberAdvanceResult]:
    try:
        results = batch_service.advance_batch(
            conn,
            batch_id,
            from_stage=body.from_stage,
            to_stage=body.to_stage,
            note=body.note,
            actor_id=user.user_id,
            actor_roles=user.roles,
        )
    except batch_service.BatchNotFound as exc:
        raise _batch_not_found() from exc
    return [MemberAdvanceResult(**result) for result in results]
