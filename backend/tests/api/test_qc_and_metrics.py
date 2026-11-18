"""US3 QC outcomes, turnaround metrics, SLA edits, vendor TAT (T036).

QC pass/fail controls the report gate; TAT metrics reflect the recorded stage
durations and the 18-day target; an SLA edit only affects future measurement;
vendor turnaround is counted from each vendor's configured anchor.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.session_context import set_session_context

pytestmark = pytest.mark.usefixtures("database_url")


def _case_id(prefix: str = "TAT") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _create_sample(client: TestClient, vendor_id: str | None = None) -> str:
    payload: dict = {"case_id": _case_id()}
    if vendor_id is not None:
        payload["vendor_id"] = vendor_id
    response = client.post("/samples", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _set_stage(admin_engine: Engine, sample_id: str, position: int) -> None:
    with admin_engine.connect() as conn, conn.begin():
        system_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
        set_session_context(conn, system_id, ("admin",))
        conn.execute(
            text(
                "UPDATE samples SET current_stage_id = "
                "(SELECT id FROM stages WHERE position = :position) WHERE id = :sample_id"
            ),
            {"position": position, "sample_id": sample_id},
        )


def _insert_sample_with_history(
    admin_engine: Engine,
    *,
    vendor_id: str | None,
    received_at: datetime,
    events: list[tuple[int, datetime]],
) -> str:
    with admin_engine.connect() as conn, conn.begin():
        system_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
        set_session_context(conn, system_id, ("admin",))
        stages = dict(conn.execute(text("SELECT position, id FROM stages")).fetchall())
        sample_id = conn.execute(
            text(
                "INSERT INTO samples (case_id, current_stage_id, vendor_id, received_at) "
                "VALUES (:case_id, :stage_id, :vendor_id, :received_at) RETURNING id"
            ),
            {
                "case_id": _case_id("HIST"),
                "stage_id": str(stages[events[-1][0]]),
                "vendor_id": vendor_id,
                "received_at": received_at,
            },
        ).scalar_one()
        for position, entered_at in events:
            conn.execute(
                text(
                    "INSERT INTO sample_stage_events "
                    "(sample_id, stage_id, actor_id, entered_at) "
                    "VALUES (:sample_id, :stage_id, :actor_id, :entered_at)"
                ),
                {
                    "sample_id": sample_id,
                    "stage_id": str(stages[position]),
                    "actor_id": system_id,
                    "entered_at": entered_at,
                },
            )
        return str(sample_id)


def test_qc_pass_fail_controls_the_report_gate(
    admin_engine: Engine, genomics_client: TestClient, bioinformatics_client: TestClient
) -> None:
    sample_id = _create_sample(genomics_client)
    _set_stage(admin_engine, sample_id, 7)

    failed = bioinformatics_client.post(
        f"/samples/{sample_id}/qc", json={"kind": "qc", "passed": False}
    )
    assert failed.status_code == 200, failed.text

    blocked = bioinformatics_client.post(f"/samples/{sample_id}/advance", json={"from_stage": 7})
    assert blocked.status_code == 409
    assert "quality control" in blocked.json()["detail"].lower()

    # A data-generation outcome is not the QC gate.
    data_gen = bioinformatics_client.post(
        f"/samples/{sample_id}/qc",
        json={"kind": "data_generation", "passed": True, "detail": {"reads": 1200}},
    )
    assert data_gen.status_code == 200
    still_blocked = bioinformatics_client.post(
        f"/samples/{sample_id}/advance", json={"from_stage": 7}
    )
    assert still_blocked.status_code == 409

    passed = bioinformatics_client.post(
        f"/samples/{sample_id}/qc", json={"kind": "qc", "passed": True}
    )
    assert passed.status_code == 200

    advanced = bioinformatics_client.post(f"/samples/{sample_id}/advance", json={"from_stage": 7})
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["current_stage"]["position"] == 8


def test_qc_recording_requires_bioinformatics(
    genomics_client: TestClient, molecular_client: TestClient, bioinformatics_client: TestClient
) -> None:
    sample_id = _create_sample(genomics_client)
    denied = molecular_client.post(f"/samples/{sample_id}/qc", json={"kind": "qc", "passed": True})
    assert denied.status_code == 403

    invalid = bioinformatics_client.post(
        f"/samples/{sample_id}/qc", json={"kind": "not-a-kind", "passed": True}
    )
    assert invalid.status_code == 422


def test_metrics_reflect_durations_and_sla_edits_are_future_only(
    admin_engine: Engine, admin_client: TestClient
) -> None:
    vendors = admin_client.get("/vendors")
    assert vendors.status_code == 200, vendors.text
    by_name = {vendor["name"]: vendor for vendor in vendors.json()}

    now = datetime.now(UTC)
    centogene_sample = _insert_sample_with_history(
        admin_engine,
        vendor_id=by_name["Centogene"]["id"],
        received_at=now - timedelta(days=10),
        events=[
            (1, now - timedelta(days=10)),
            (2, now - timedelta(days=2)),
            (4, now - timedelta(days=1)),
        ],
    )
    arcensus_sample = _insert_sample_with_history(
        admin_engine,
        vendor_id=by_name["Arcensus"]["id"],
        received_at=now - timedelta(days=10),
        events=[(1, now - timedelta(days=10))],
    )

    metrics = admin_client.get("/metrics/tat")
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["target_days"] == 18

    samples = {sample["sample_id"]: sample for sample in body["samples"]}
    centogene = samples[centogene_sample]
    stage_one = next(stage for stage in centogene["stages"] if stage["position"] == 1)
    assert stage_one["duration_hours"] == 192.0  # recorded: 8 days in stage 1
    assert stage_one["breached"] is True
    assert centogene["target_breached"] is False
    assert centogene["elapsed_working_days"] >= 0

    # Centogene's TAT counts from sequencing (stage 4), not receipt.
    assert centogene["vendor"]["tat_anchor"] == "sequencing"
    assert centogene["vendor"]["elapsed_days"] < 2

    arcensus = samples[arcensus_sample]
    assert arcensus["vendor"]["tat_anchor"] == "receipt"
    assert arcensus["vendor"]["elapsed_days"] > 9
    assert arcensus["vendor"]["breached"] is True

    vendor_summary = {vendor["name"]: vendor for vendor in body["vendors"]}
    assert vendor_summary["Centogene"]["assigned_samples"] >= 1
    assert vendor_summary["Arcensus"]["tat_days"] == 4

    # An administrator raises stage 1's SLA: recorded durations are untouched
    # and future measurement uses the new target.
    patched = admin_client.patch(f"/stages/{stage_one['stage_id']}/sla", json={"sla_days": 10})
    assert patched.status_code == 200, patched.text
    assert patched.json()["sla_days"] == 10

    after = admin_client.get("/metrics/tat").json()
    refreshed = {sample["sample_id"]: sample for sample in after["samples"]}
    refreshed_stage = next(
        stage for stage in refreshed[centogene_sample]["stages"] if stage["position"] == 1
    )
    assert refreshed_stage["duration_hours"] == 192.0
    assert refreshed_stage["sla_days"] == 10
    assert refreshed_stage["breached"] is False

    with admin_engine.connect() as conn, conn.begin():
        system_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
        set_session_context(conn, system_id, ("admin",))
        recorded = conn.execute(
            text(
                "SELECT e.duration_hours FROM sample_stage_events e "
                "JOIN stages st ON st.id = e.stage_id "
                "WHERE e.sample_id = :sample_id AND st.position = 2"
            ),
            {"sample_id": centogene_sample},
        ).scalar_one()
    assert float(recorded) == 192.0


def test_metrics_and_sla_edits_are_admin_only(
    genomics_client: TestClient, admin_client: TestClient
) -> None:
    assert genomics_client.get("/metrics/tat").status_code == 403
    assert (
        genomics_client.patch(f"/stages/{uuid.uuid4()}/sla", json={"sla_days": 1}).status_code
        == 403
    )
    assert admin_client.get("/metrics/tat").status_code == 200
