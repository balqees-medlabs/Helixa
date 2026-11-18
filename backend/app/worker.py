"""Portal-push jobs worker (FR-017/018/019, research D6).

The worker leases one ``portal_push`` job at a time with ``SKIP LOCKED``, acts
as the seeded system actor with ``app.job_id`` set (so Spec 1 audits every
change), calls the isolated ``PortalClient``, and records the outcome in its
own transaction. Success sets ``delivered_at`` exactly once and closes the
sample; failure records the error and, while under ``PORTAL_MAX_ATTEMPTS``,
schedules an automatic retry a backoff later (a fresh queued job at
``next_attempt_at``). At the attempt cap the push stays ``failed``.
"""

import json
import logging
import time
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.core import deps
from app.core.config import Settings, get_settings
from app.db.session_context import set_session_context
from app.services.portal_client import PortalClient, PortalReport, build_portal_client

logger = logging.getLogger(__name__)


def _context(conn: Connection, job_id: uuid.UUID | None = None) -> uuid.UUID:
    system_id = conn.execute(text("SELECT fn_system_actor_id()")).scalar_one()
    if system_id is None:
        raise RuntimeError("seed system actor is missing")
    set_session_context(conn, system_id, ("admin",), job_id)
    return system_id


def _lease(conn: Connection) -> dict | None:
    return (
        conn.execute(
            text(
                "WITH candidate AS ("
                "  SELECT id FROM jobs"
                "  WHERE kind = 'portal_push' AND status = 'queued' AND run_after <= now()"
                "  ORDER BY run_after, id"
                "  FOR UPDATE SKIP LOCKED"
                "  LIMIT 1"
                ")"
                "UPDATE jobs j "
                "SET status = 'running', locked_at = now(), attempts = j.attempts + 1, "
                "    updated_at = now() "
                "FROM candidate c WHERE j.id = c.id "
                "RETURNING j.id, j.payload"
            )
        )
        .mappings()
        .first()
    )


def _load_push(conn: Connection, push_id: uuid.UUID) -> dict | None:
    return (
        conn.execute(
            text(
                "SELECT p.id AS push_id, p.status, p.delivered_at, p.attempts, "
                "p.report_id, r.sample_id, r.path, r.content_type, r.size_bytes, "
                "r.sha256, s.case_id, s.status AS sample_status "
                "FROM portal_pushes p "
                "JOIN reports r ON r.id = p.report_id "
                "JOIN samples s ON s.id = r.sample_id "
                "WHERE p.id = :push_id"
            ),
            {"push_id": push_id},
        )
        .mappings()
        .first()
    )


def _finish(
    engine: Engine,
    settings: Settings,
    *,
    job_id: uuid.UUID,
    push_id: uuid.UUID | None,
    report_id: uuid.UUID | None,
    sample_id: uuid.UUID | None,
    success: bool,
    error: str | None,
) -> None:
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            _context(conn, job_id)
            if push_id is not None and success:
                delivered = conn.execute(
                    text(
                        "UPDATE portal_pushes "
                        "SET status = 'success', delivered_at = now(), last_error = NULL, "
                        "    next_attempt_at = now() "
                        "WHERE id = :push_id AND delivered_at IS NULL "
                        "RETURNING id"
                    ),
                    {"push_id": push_id},
                ).scalar()
                if delivered is not None and sample_id is not None:
                    conn.execute(
                        text(
                            "UPDATE samples SET status = 'closed' "
                            "WHERE id = :sample_id AND status = 'active'"
                        ),
                        {"sample_id": sample_id},
                    )
            elif push_id is not None:
                # Record the failure; auto-retry with backoff until the attempt
                # cap. Under the cap the push returns to 'queued' and a new job
                # is scheduled at next_attempt_at; at the cap it stays 'failed'.
                outcome = (
                    conn.execute(
                        text(
                            "UPDATE portal_pushes "
                            "SET attempts = attempts + 1, last_error = :error, "
                            "    next_attempt_at = now() + make_interval(secs => :backoff), "
                            "    status = CASE WHEN attempts + 1 >= :max_attempts "
                            "                  THEN 'failed' ELSE 'queued' END "
                            "WHERE id = :push_id AND delivered_at IS NULL "
                            "RETURNING status, next_attempt_at"
                        ),
                        {
                            "push_id": push_id,
                            "error": error,
                            "backoff": settings.PORTAL_RETRY_BACKOFF_SEC,
                            "max_attempts": settings.PORTAL_MAX_ATTEMPTS,
                        },
                    )
                    .mappings()
                    .first()
                )
                if outcome is not None and outcome["status"] == "queued" and report_id is not None:
                    conn.execute(
                        text(
                            "INSERT INTO jobs (kind, payload, run_after) "
                            "VALUES ('portal_push', CAST(:payload AS jsonb), :run_after)"
                        ),
                        {
                            "payload": json.dumps(
                                {"push_id": str(push_id), "report_id": str(report_id)}
                            ),
                            "run_after": outcome["next_attempt_at"],
                        },
                    )

            conn.execute(
                text(
                    "UPDATE jobs SET status = :status, last_error = :error, "
                    "locked_at = NULL, updated_at = now() WHERE id = :job_id"
                ),
                {
                    "job_id": job_id,
                    "status": "succeeded" if success else "failed",
                    "error": error,
                },
            )
            tx.commit()
        except BaseException:
            tx.rollback()
            raise


def run_once(
    *,
    engine: Engine | None = None,
    portal_client: PortalClient | None = None,
    settings: Settings | None = None,
) -> bool:
    """Process at most one queued portal push; return whether one ran."""
    settings = settings or get_settings()
    engine = engine or deps.get_engine()
    client = portal_client or build_portal_client(settings)

    job_id: uuid.UUID | None = None
    push_id: uuid.UUID | None = None
    push: dict | None = None
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            _context(conn)
            job = _lease(conn)
            if job is None:
                tx.commit()
                return False
            job_id = job["id"]
            payload = job["payload"] or {}
            raw_push_id = payload.get("push_id")
            push_id = uuid.UUID(str(raw_push_id)) if raw_push_id else None
            push = _load_push(conn, push_id) if push_id else None
            tx.commit()
        except BaseException:
            tx.rollback()
            raise

    if job_id is None:
        return False

    if push is None:
        _finish(
            engine,
            settings,
            job_id=job_id,
            push_id=push_id,
            report_id=None,
            sample_id=None,
            success=False,
            error="portal push record not found",
        )
        return True

    if push["delivered_at"] is not None:
        _finish(
            engine,
            settings,
            job_id=job_id,
            push_id=push_id,
            report_id=push["report_id"],
            sample_id=None,
            success=True,
            error=None,
        )
        return True

    report = PortalReport(
        report_id=push["report_id"],
        sample_id=push["sample_id"],
        case_id=push["case_id"],
        path=push["path"],
        content_type=push["content_type"],
        size_bytes=push["size_bytes"],
        sha256=push["sha256"],
    )
    try:
        client.push(report)
        success, error = True, None
    except Exception as exc:  # the portal is external; any failure is recorded
        success, error = False, str(exc) or type(exc).__name__
        logger.warning("portal push %s failed: %s", push_id, error)

    _finish(
        engine,
        settings,
        job_id=job_id,
        push_id=push_id,
        report_id=push["report_id"],
        sample_id=push["sample_id"],
        success=success,
        error=error,
    )
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("portal push worker started")
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("portal push worker iteration failed")
        time.sleep(2)


if __name__ == "__main__":
    main()
