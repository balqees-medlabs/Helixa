"""Samples & gated workflow HTTP shell (workflow-contract.md)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, current_user, get_tx, require_roles
from app.schemas.base import Page
from app.schemas.samples import (
    AdvanceRequest,
    ConsentOut,
    ConsentRequest,
    SampleCreate,
    SampleEventOut,
    SampleOut,
)
from app.services import consent_service, sample_service, workflow_service

router = APIRouter(prefix="/samples", tags=["samples"])

Genomics = Annotated[AuthContext, Depends(require_roles("genomics"))]
AnyUser = Annotated[AuthContext, Depends(current_user)]
Conn = Annotated[Connection, Depends(get_tx)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Sample not found")


@router.post("", response_model=SampleOut, status_code=201)
def register_sample(body: SampleCreate, user: Genomics, conn: Conn) -> SampleOut:
    try:
        sample = sample_service.register_sample(
            conn,
            case_id=body.case_id,
            external_ref=body.external_ref,
            vendor_id=body.vendor_id,
            actor_id=user.user_id,
        )
    except sample_service.SampleConflict as exc:
        raise HTTPException(
            status_code=409, detail=f"A sample with case id {exc} already exists"
        ) from exc
    except sample_service.UnknownVendor as exc:
        raise HTTPException(status_code=422, detail=f"Unknown vendor: {exc}") from exc
    return SampleOut(**sample)


@router.get("", response_model=Page[SampleOut])
def list_samples(
    _user: AnyUser,
    conn: Conn,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SampleOut]:
    items, total = sample_service.list_samples(conn, limit=limit, offset=offset)
    return Page(items=[SampleOut(**s) for s in items], total=total, limit=limit, offset=offset)


@router.get("/{sample_id}", response_model=SampleOut)
def get_sample(sample_id: uuid.UUID, _user: AnyUser, conn: Conn) -> SampleOut:
    try:
        return SampleOut(**sample_service.get_sample(conn, sample_id))
    except sample_service.SampleNotFound as exc:
        raise _not_found() from exc


@router.get("/{sample_id}/events", response_model=list[SampleEventOut])
def list_events(sample_id: uuid.UUID, _user: AnyUser, conn: Conn) -> list[SampleEventOut]:
    try:
        events = sample_service.list_events(conn, sample_id)
    except sample_service.SampleNotFound as exc:
        raise _not_found() from exc
    return [SampleEventOut(**event) for event in events]


@router.get("/{sample_id}/consent", response_model=ConsentOut)
def get_consent(sample_id: uuid.UUID, _user: AnyUser, conn: Conn) -> ConsentOut:
    try:
        return ConsentOut(**consent_service.get_consent(conn, sample_id))
    except sample_service.SampleNotFound as exc:
        raise _not_found() from exc


@router.post("/{sample_id}/consent", response_model=ConsentOut)
def set_consent(
    sample_id: uuid.UUID,
    body: ConsentRequest,
    user: Genomics,
    conn: Conn,
) -> ConsentOut:
    try:
        consent = consent_service.set_items(
            conn,
            sample_id,
            [item.model_dump() for item in body.items],
            user.user_id,
        )
    except sample_service.SampleNotFound as exc:
        raise _not_found() from exc
    return ConsentOut(**consent)


@router.post("/{sample_id}/advance", response_model=SampleOut)
def advance_sample(
    sample_id: uuid.UUID,
    body: AdvanceRequest,
    user: AnyUser,
    conn: Conn,
) -> SampleOut:
    try:
        result = workflow_service.advance(
            conn,
            sample_id,
            from_stage=body.from_stage,
            to_stage=body.to_stage,
            actor_id=user.user_id,
            actor_roles=user.roles,
            note=body.note,
        )
    except sample_service.SampleNotFound as exc:
        raise _not_found() from exc
    except workflow_service.StagePermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (workflow_service.StageConflict, workflow_service.StageGateFailed) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SampleOut(**result.sample)
