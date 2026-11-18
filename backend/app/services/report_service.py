"""Report storage, retrieval and portal-push tracking (FR-016/017/019).

Validation happens before any filesystem write: the sample must exist and have
a passing QC result, the content type must be allowlisted, and the payload must
fit the configured cap. Accepted files are stored under ``REPORTS_ROOT`` with
their SHA-256, and a queued push plus its worker job are created atomically
with the metadata row.
"""

import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import Settings, get_settings
from app.services.sample_service import get_sample

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class ReportQcRequired(Exception):
    """The sample has no passing QC result."""


class ReportTypeRejected(Exception):
    """Content type is outside the allowlist."""


class ReportTooLarge(Exception):
    """Payload exceeds the configured cap."""


class ReportEmpty(Exception):
    """Payload is empty."""


class ReportNotFound(Exception):
    """No report with that id is visible to the caller."""


class ReportFileMissing(Exception):
    """The metadata row exists but the file is gone or outside the root."""


class PushNotFound(Exception):
    """No portal push with that id."""


class PushNotRetryable(Exception):
    """The push is already delivered or has exhausted its attempts."""


_REPORT_SELECT = """
    SELECT r.id, r.sample_id, r.path, r.content_type, r.size_bytes, r.sha256,
           r.uploaded_by, r.uploaded_at,
           p.id AS push_id, p.status AS push_status
    FROM reports r
    JOIN portal_pushes p ON p.report_id = r.id
"""

_PUSH_SELECT = """
    SELECT id, report_id, status, attempts, last_error, next_attempt_at, delivered_at
    FROM portal_pushes
"""


def _safe_component(value: str, fallback: str) -> str:
    cleaned = _SAFE_NAME.sub("_", Path(value).name).strip("._-")
    return cleaned[:120] or fallback


def _settings(settings: Settings | None) -> Settings:
    return settings or get_settings()


def upload_report(
    conn: Connection,
    sample_id: uuid.UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    actor_id: uuid.UUID,
    settings: Settings | None = None,
) -> dict:
    settings = _settings(settings)
    sample = get_sample(conn, sample_id)

    passed = conn.execute(
        text(
            "SELECT 1 FROM qc_results "
            "WHERE sample_id = :sample_id AND kind = 'qc' AND passed LIMIT 1"
        ),
        {"sample_id": sample_id},
    ).scalar()
    if not passed:
        raise ReportQcRequired("Quality control must be passed before report upload")

    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type not in settings.report_allowed_types:
        raise ReportTypeRejected(media_type or "unknown")
    if not data:
        raise ReportEmpty("Report file is empty")
    if len(data) > settings.REPORT_MAX_BYTES:
        raise ReportTooLarge(str(settings.REPORT_MAX_BYTES))

    root = Path(settings.REPORTS_ROOT)
    case_dir = root / _safe_component(sample["case_id"], "case")
    stored_name = f"{uuid.uuid4().hex}-{_safe_component(filename, 'report.pdf')}"
    destination = case_dir / stored_name
    case_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256(data).hexdigest()
    handle, temp_name = tempfile.mkstemp(dir=case_dir, prefix=".upload-")
    try:
        with os.fdopen(handle, "wb") as temp_file:
            temp_file.write(data)
        os.replace(temp_name, destination)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise

    report_id = conn.execute(
        text(
            "INSERT INTO reports "
            "(sample_id, path, content_type, size_bytes, sha256, uploaded_by) "
            "VALUES (:sample_id, :path, :content_type, :size_bytes, :sha256, :uploaded_by) "
            "RETURNING id"
        ),
        {
            "sample_id": sample_id,
            "path": str(destination),
            "content_type": media_type,
            "size_bytes": len(data),
            "sha256": digest,
            "uploaded_by": actor_id,
        },
    ).scalar_one()

    push_id, push_status = conn.execute(
        text(
            "INSERT INTO portal_pushes (report_id, status) "
            "VALUES (:report_id, 'queued') RETURNING id, status"
        ),
        {"report_id": report_id},
    ).one()

    conn.execute(
        text("INSERT INTO jobs (kind, payload) VALUES ('portal_push', CAST(:payload AS jsonb))"),
        {"payload": json.dumps({"push_id": str(push_id), "report_id": str(report_id)})},
    )

    row = (
        conn.execute(text(f"{_REPORT_SELECT} WHERE r.id = :report_id"), {"report_id": report_id})
        .mappings()
        .one()
    )
    return dict(row)


def get_report(conn: Connection, report_id: uuid.UUID) -> dict:
    row = (
        conn.execute(text(f"{_REPORT_SELECT} WHERE r.id = :report_id"), {"report_id": report_id})
        .mappings()
        .first()
    )
    if row is None:
        raise ReportNotFound(str(report_id))
    return dict(row)


def report_file_path(
    conn: Connection, report_id: uuid.UUID, settings: Settings | None = None
) -> Path:
    report = get_report(conn, report_id)
    root = Path(_settings(settings).REPORTS_ROOT).resolve()
    path = Path(report["path"]).resolve()
    if root != path and root not in path.parents:
        raise ReportFileMissing(report["path"])
    if not path.is_file():
        raise ReportFileMissing(report["path"])
    return path


def get_push(conn: Connection, push_id: uuid.UUID) -> dict:
    row = (
        conn.execute(text(f"{_PUSH_SELECT} WHERE id = :push_id"), {"push_id": push_id})
        .mappings()
        .first()
    )
    if row is None:
        raise PushNotFound(str(push_id))
    return dict(row)


def retry_push(conn: Connection, push_id: uuid.UUID, settings: Settings | None = None) -> dict:
    settings = _settings(settings)
    push = get_push(conn, push_id)
    if push["delivered_at"] is not None or push["status"] == "success":
        raise PushNotRetryable("Push has already been delivered")
    if push["attempts"] >= settings.PORTAL_MAX_ATTEMPTS:
        raise PushNotRetryable("Push has exhausted its retry attempts")

    conn.execute(
        text(
            "UPDATE portal_pushes SET status = 'queued', next_attempt_at = now(), "
            "last_error = NULL WHERE id = :push_id"
        ),
        {"push_id": push_id},
    )
    conn.execute(
        text("INSERT INTO jobs (kind, payload) VALUES ('portal_push', CAST(:payload AS jsonb))"),
        {"payload": json.dumps({"push_id": str(push_id), "report_id": str(push["report_id"])})},
    )
    return get_push(conn, push_id)
