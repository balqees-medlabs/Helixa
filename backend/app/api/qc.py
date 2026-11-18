"""QC / data-generation outcome recording (FR-013)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, get_tx, require_roles
from app.schemas.qc import QcCreate, QcOut
from app.services import qc_service
from app.services.sample_service import SampleNotFound

router = APIRouter(prefix="/samples", tags=["qc"])

Bioinformatics = Annotated[AuthContext, Depends(require_roles("bioinformatics"))]
Conn = Annotated[Connection, Depends(get_tx)]


@router.post("/{sample_id}/qc", response_model=QcOut)
def record_qc(sample_id: uuid.UUID, body: QcCreate, user: Bioinformatics, conn: Conn) -> QcOut:
    try:
        result = qc_service.record(
            conn,
            sample_id,
            kind=body.kind,
            passed=body.passed,
            detail=body.detail,
            actor_id=user.user_id,
        )
    except SampleNotFound as exc:
        raise HTTPException(status_code=404, detail="Sample not found") from exc
    return QcOut(**result)
