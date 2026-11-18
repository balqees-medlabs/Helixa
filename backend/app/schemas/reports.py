"""Report and portal-push response schemas (FR-016/017)."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ReportOut(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    path: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    push_id: uuid.UUID
    push_status: str


class PortalPushOut(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    status: str
    attempts: int
    last_error: str | None
    next_attempt_at: datetime
    delivered_at: datetime | None
