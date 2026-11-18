"""Reports and portal-push HTTP shell (reports-portal-contract.md)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.deps import AuthContext, get_tx, require_roles
from app.schemas.reports import PortalPushOut, ReportOut
from app.services import report_service
from app.services.sample_service import SampleNotFound

router = APIRouter(tags=["reports"])

Uploader = Annotated[AuthContext, Depends(require_roles("bioinformatics"))]
Reader = Annotated[AuthContext, Depends(require_roles("admin", "bioinformatics", "genomics"))]
Admin = Annotated[AuthContext, Depends(require_roles("admin"))]
Conn = Annotated[Connection, Depends(get_tx)]


@router.post("/samples/{sample_id}/report", response_model=ReportOut, status_code=201)
def upload_report(
    sample_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    user: Uploader,
    conn: Conn,
) -> ReportOut:
    settings = get_settings()
    data = file.file.read(settings.REPORT_MAX_BYTES + 1)
    try:
        report = report_service.upload_report(
            conn,
            sample_id,
            filename=file.filename or "report.pdf",
            content_type=file.content_type or "",
            data=data,
            actor_id=user.user_id,
            settings=settings,
        )
    except SampleNotFound as exc:
        raise HTTPException(status_code=404, detail="Sample not found") from exc
    except report_service.ReportQcRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except report_service.ReportTypeRejected as exc:
        allowed = ", ".join(sorted(settings.report_allowed_types))
        raise HTTPException(
            status_code=415, detail=f"Unsupported content type {exc}; allowed: {allowed}"
        ) from exc
    except report_service.ReportTooLarge as exc:
        raise HTTPException(status_code=413, detail=f"Report exceeds the {exc}-byte limit") from exc
    except report_service.ReportEmpty as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ReportOut(**report)


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: uuid.UUID, _user: Reader, conn: Conn) -> ReportOut:
    try:
        return ReportOut(**report_service.get_report(conn, report_id))
    except report_service.ReportNotFound as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc


@router.get("/reports/{report_id}/file")
def get_report_file(report_id: uuid.UUID, _user: Reader, conn: Conn) -> FileResponse:
    try:
        path = report_service.report_file_path(conn, report_id)
    except report_service.ReportNotFound as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    except report_service.ReportFileMissing as exc:
        raise HTTPException(status_code=404, detail="Report file not found") from exc
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/portal-pushes/{push_id}", response_model=PortalPushOut)
def get_portal_push(push_id: uuid.UUID, _user: Admin, conn: Conn) -> PortalPushOut:
    try:
        return PortalPushOut(**report_service.get_push(conn, push_id))
    except report_service.PushNotFound as exc:
        raise HTTPException(status_code=404, detail="Portal push not found") from exc


@router.post("/portal-pushes/{push_id}/retry", response_model=PortalPushOut)
def retry_portal_push(push_id: uuid.UUID, _user: Admin, conn: Conn) -> PortalPushOut:
    try:
        push = report_service.retry_push(conn, push_id)
    except report_service.PushNotFound as exc:
        raise HTTPException(status_code=404, detail="Portal push not found") from exc
    except report_service.PushNotRetryable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PortalPushOut(**push)
