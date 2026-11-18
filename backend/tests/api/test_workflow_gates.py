"""US2 stage gates and registration (T029, SC-004 / FR-008..FR-011).

Consent-before-molecular, QC-before-report, no-skip, duplicate case ids, and
the per-stage role authority are all asserted through the real API against
real Postgres. QC rows are seeded directly because the QC endpoint is US3.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.session_context import set_session_context
from app.services.consent_service import REQUIRED_CONSENT_ITEMS

pytestmark = pytest.mark.usefixtures("database_url")


def _case_id() -> str:
    return f"WG-{uuid.uuid4().hex[:12]}"


def _create_sample(client: TestClient, case_id: str | None = None) -> dict:
    response = client.post("/samples", json={"case_id": case_id or _case_id()})
    assert response.status_code == 201, response.text
    return response.json()


def _advance(client: TestClient, sample_id: str, from_stage: int, to_stage: int | None = None):
    body: dict = {"from_stage": from_stage}
    if to_stage is not None:
        body["to_stage"] = to_stage
    return client.post(f"/samples/{sample_id}/advance", json=body)


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


def _record_passing_qc(admin_engine: Engine, sample_id: str) -> None:
    with admin_engine.connect() as conn, conn.begin():
        system_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
        set_session_context(conn, system_id, ("admin",))
        conn.execute(
            text(
                "INSERT INTO qc_results (sample_id, kind, passed, recorded_by) "
                "VALUES (:sample_id, 'qc', true, :recorded_by)"
            ),
            {"sample_id": sample_id, "recorded_by": system_id},
        )


def _complete_all_consent(client: TestClient, sample_id: str):
    """Mark every seeded required consent item complete."""
    items = [
        {"item": item, "required": True, "complete": True}
        for item in REQUIRED_CONSENT_ITEMS
    ]
    return client.post(f"/samples/{sample_id}/consent", json={"items": items})


def test_registration_seeds_required_consent_incomplete(genomics_client: TestClient) -> None:
    sample = _create_sample(genomics_client)
    consent = genomics_client.get(f"/samples/{sample['id']}/consent")
    assert consent.status_code == 200, consent.text
    seeded = {item["item"] for item in consent.json()["items"] if item["required"]}
    assert set(REQUIRED_CONSENT_ITEMS) <= seeded
    assert consent.json()["required_complete"] is False


def test_consent_gate_blocks_molecular_until_complete(
    genomics_client: TestClient, molecular_client: TestClient
) -> None:
    sample = _create_sample(genomics_client)
    assert _advance(genomics_client, sample["id"], 1).status_code == 200

    # A freshly registered sample carries the seeded (incomplete) checklist, so
    # it cannot advance to molecular processing — no consent documented yet.
    blocked = _advance(molecular_client, sample["id"], 2)
    assert blocked.status_code == 409
    assert "consent" in blocked.json()["detail"].lower()

    # Partially complete is still blocked.
    genomics_client.post(
        f"/samples/{sample['id']}/consent",
        json={"items": [{"item": REQUIRED_CONSENT_ITEMS[0], "required": True, "complete": True}]},
    )
    assert _advance(molecular_client, sample["id"], 2).status_code == 409

    completed = _complete_all_consent(genomics_client, sample["id"])
    assert completed.status_code == 200
    assert completed.json()["required_complete"] is True

    advanced = _advance(molecular_client, sample["id"], 2)
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["current_stage"]["position"] == 3


def test_qc_gate_blocks_report_until_passed(
    admin_engine: Engine, genomics_client: TestClient, bioinformatics_client: TestClient
) -> None:
    sample = _create_sample(genomics_client)
    _set_stage(admin_engine, sample["id"], 7)

    blocked = _advance(bioinformatics_client, sample["id"], 7)
    assert blocked.status_code == 409
    assert "quality control" in blocked.json()["detail"].lower()

    _record_passing_qc(admin_engine, sample["id"])

    advanced = _advance(bioinformatics_client, sample["id"], 7)
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["current_stage"]["position"] == 8


def test_skipping_a_stage_is_refused(
    genomics_client: TestClient, molecular_client: TestClient
) -> None:
    sample = _create_sample(genomics_client)

    skipped = _advance(genomics_client, sample["id"], 1, to_stage=3)
    assert skipped.status_code == 409
    assert "skip" in skipped.json()["detail"].lower()

    # Still at stage 1 afterwards.
    current = genomics_client.get(f"/samples/{sample['id']}")
    assert current.status_code == 200
    assert current.json()["current_stage"]["position"] == 1

    # A correct one-step advance as the wrong role is forbidden.
    wrong_role = _advance(molecular_client, sample["id"], 1)
    assert wrong_role.status_code == 403


def test_duplicate_case_id_is_rejected(genomics_client: TestClient) -> None:
    case_id = _case_id()
    _create_sample(genomics_client, case_id)

    duplicate = genomics_client.post("/samples", json={"case_id": case_id})
    assert duplicate.status_code == 409


def test_new_sample_starts_at_stage_one_with_history(genomics_client: TestClient) -> None:
    sample = _create_sample(genomics_client)
    assert sample["current_stage"]["position"] == 1
    assert sample["current_stage"]["slug"] == "received"

    events = genomics_client.get(f"/samples/{sample['id']}/events")
    assert events.status_code == 200
    assert [event["stage"]["position"] for event in events.json()] == [1]

    listing = genomics_client.get("/samples", params={"limit": 200})
    assert listing.status_code == 200
    assert any(item["id"] == sample["id"] for item in listing.json()["items"])


def test_consent_update_requires_genomics_role(
    genomics_client: TestClient, molecular_client: TestClient
) -> None:
    sample = _create_sample(genomics_client)

    denied = molecular_client.post(
        f"/samples/{sample['id']}/consent",
        json={"items": [{"item": "signed_consent", "required": True, "complete": True}]},
    )
    assert denied.status_code == 403
