"""Turnaround metrics and stage-SLA maintenance (FR-015)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, get_tx, require_roles
from app.schemas.metrics import SlaUpdate, StageSlaOut, TatMetrics
from app.services import sla_service

router = APIRouter(tags=["metrics"])

Admin = Annotated[AuthContext, Depends(require_roles("admin"))]
Conn = Annotated[Connection, Depends(get_tx)]


@router.get("/metrics/tat", response_model=TatMetrics)
def get_tat_metrics(_user: Admin, conn: Conn) -> TatMetrics:
    return TatMetrics(**sla_service.compute_tat_metrics(conn))


@router.patch("/stages/{stage_id}/sla", response_model=StageSlaOut)
def update_stage_sla(stage_id: uuid.UUID, body: SlaUpdate, _user: Admin, conn: Conn) -> StageSlaOut:
    try:
        result = sla_service.update_stage_sla(conn, stage_id, body.sla_days)
    except sla_service.StageNotFound as exc:
        raise HTTPException(status_code=404, detail="Stage not found") from exc
    return StageSlaOut(**result)
