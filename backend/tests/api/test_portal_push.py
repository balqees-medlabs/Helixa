"""US4 portal push worker, retry and case close (T044, SC-006/009).

A failed push leaves the case open and is retryable; success records
``delivered_at`` exactly once and closes the sample. Re-running the worker
never sends a delivered push again.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core import deps
from app.core.config import Settings
from app.db.session_context import set_session_context
from app.services.portal_client import MockPortalClient
from app.worker import run_once

pytestmark = pytest.mark.usefixtures("database_url", "reports_root")

PDF = b"%PDF-1.4\n% portal push report\n"


@pytest.fixture(autouse=True)
def _drain_portal_jobs(admin_engine: Engine) -> None:
    """Other tests' uploads also queue pushes; drain them so the worker is deterministic."""
    with admin_engine.connect() as conn, conn.begin():
        system_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
        set_session_context(conn, system_id, ("admin",))
        conn.execute(
            text(
                "UPDATE jobs SET status = 'succeeded', updated_at = now() "
                "WHERE kind = 'portal_push' AND status = 'queued'"
            )
        )


def _upload_report(
    genomics_client: TestClient, bioinformatics_client: TestClient
) -> tuple[str, str, str]:
    sample = genomics_client.post("/samples", json={"case_id": f"PUSH-{uuid.uuid4().hex[:12]}"})
    assert sample.status_code == 201, sample.text
    sample_id = sample.json()["id"]
    assert (
        bioinformatics_client.post(
            f"/samples/{sample_id}/qc", json={"kind": "qc", "passed": True}
        ).status_code
        == 200
    )
    report = bioinformatics_client.post(
        f"/samples/{sample_id}/report",
        files={"file": ("report.pdf", PDF, "application/pdf")},
    )
    assert report.status_code == 201, report.text
    return sample_id, report.json()["id"], report.json()["push_id"]


def _fast_settings() -> Settings:
    """Test settings with zero backoff so auto-retry jobs are leasable at once."""
    return Settings(PORTAL_RETRY_BACKOFF_SEC=0)


def test_failed_push_auto_retries_to_success_and_closes_case_once(
    admin_client: TestClient,
    genomics_client: TestClient,
    bioinformatics_client: TestClient,
    admin_engine: Engine,
) -> None:
    sample_id, report_id, push_id = _upload_report(genomics_client, bioinformatics_client)

    engine = deps.get_engine()
    fast = _fast_settings()

    # First attempt fails -> auto re-queued (not terminal), case stays active.
    assert run_once(engine=engine, portal_client=MockPortalClient(fail_times=1), settings=fast)
    pending = admin_client.get(f"/portal-pushes/{push_id}").json()
    assert pending["status"] == "queued"  # scheduled retry, not a dead end
    assert pending["attempts"] == 1
    assert pending["last_error"]
    assert pending["delivered_at"] is None
    assert genomics_client.get(f"/samples/{sample_id}").json()["status"] == "active"

    # The worker picks up the auto-scheduled retry and succeeds -- no manual step.
    assert run_once(engine=engine, portal_client=MockPortalClient(), settings=fast)

    delivered = admin_client.get(f"/portal-pushes/{push_id}").json()
    assert delivered["status"] == "success"
    assert delivered["delivered_at"] is not None
    assert genomics_client.get(f"/samples/{sample_id}").json()["status"] == "closed"

    # No duplicate delivery: no queued job remains and one push row per report.
    assert run_once(engine=engine, portal_client=MockPortalClient(), settings=fast) is False
    assert admin_client.post(f"/portal-pushes/{push_id}/retry").status_code == 409

    with admin_engine.connect() as conn, conn.begin():
        system_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
        set_session_context(conn, system_id, ("admin",))
        count = conn.execute(
            text("SELECT count(*) FROM portal_pushes WHERE report_id = :report_id"),
            {"report_id": report_id},
        ).scalar_one()
    assert count == 1


def test_push_stops_auto_retrying_at_the_attempt_cap(
    admin_client: TestClient,
    genomics_client: TestClient,
    bioinformatics_client: TestClient,
) -> None:
    sample_id, _report_id, push_id = _upload_report(genomics_client, bioinformatics_client)

    engine = deps.get_engine()
    fast = Settings(PORTAL_RETRY_BACKOFF_SEC=0, PORTAL_MAX_ATTEMPTS=3)

    runs = 0
    while run_once(engine=engine, portal_client=MockPortalClient(fail_times=99), settings=fast):
        runs += 1
        assert runs <= 10  # guard against an infinite retry loop

    assert runs == 3  # the initial attempt + 2 auto-retries, then no new job
    final = admin_client.get(f"/portal-pushes/{push_id}").json()
    assert final["status"] == "failed"
    assert final["attempts"] == 3
    assert final["delivered_at"] is None
    assert genomics_client.get(f"/samples/{sample_id}").json()["status"] == "active"


def test_portal_push_status_is_admin_only(
    genomics_client: TestClient,
    bioinformatics_client: TestClient,
    admin_client: TestClient,
) -> None:
    _, _, push_id = _upload_report(genomics_client, bioinformatics_client)
    assert genomics_client.get(f"/portal-pushes/{push_id}").status_code == 403
    assert admin_client.get(f"/portal-pushes/{push_id}").status_code == 200
    assert genomics_client.post(f"/portal-pushes/{push_id}/retry").status_code == 403
