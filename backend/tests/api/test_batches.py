"""US3 batches (T035, FR-012).

A batch-advance applies the same single-step transition to each member in its
own savepoint: a member failing its gate or carrying a stale stage is reported
individually and never blocks the others.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.services.consent_service import REQUIRED_CONSENT_ITEMS

pytestmark = pytest.mark.usefixtures("database_url")


def _case_id() -> str:
    return f"BATCH-{uuid.uuid4().hex[:12]}"


def _create_sample(client: TestClient) -> str:
    response = client.post("/samples", json={"case_id": _case_id()})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _advance(client: TestClient, sample_id: str, from_stage: int):
    return client.post(f"/samples/{sample_id}/advance", json={"from_stage": from_stage})


def _stage_position(client: TestClient, sample_id: str) -> int:
    response = client.get(f"/samples/{sample_id}")
    assert response.status_code == 200
    return response.json()["current_stage"]["position"]


def test_batch_advance_reports_each_member_and_isolates_failures(
    genomics_client: TestClient, molecular_client: TestClient
) -> None:
    first = _create_sample(genomics_client)
    second = _create_sample(genomics_client)
    stale = _create_sample(genomics_client)

    batch = genomics_client.post("/batches", json={"name": f"run-{uuid.uuid4().hex[:8]}"})
    assert batch.status_code == 201, batch.text
    batch_id = batch.json()["id"]

    members = genomics_client.post(
        f"/batches/{batch_id}/members",
        json={"sample_ids": [first, second, stale]},
    )
    assert members.status_code == 200, members.text
    assert set(members.json()["member_ids"]) == {first, second, stale}

    # Move two members to stage 2; complete consent for one of them only.
    for sample_id in (first, second):
        assert _advance(genomics_client, sample_id, 1).status_code == 200
    consent = genomics_client.post(
        f"/samples/{first}/consent",
        json={
            "items": [
                {"item": item, "required": True, "complete": True}
                for item in REQUIRED_CONSENT_ITEMS
            ]
        },
    )
    assert consent.status_code == 200

    response = molecular_client.post(f"/batches/{batch_id}/advance", json={"from_stage": 2})
    assert response.status_code == 200, response.text
    results = {item["sample_id"]: item for item in response.json()}
    assert results[first]["status"] == "advanced"
    assert results[second]["status"] == "gate_failed"
    assert "consent" in results[second]["detail"].lower()
    assert results[stale]["status"] == "conflict"

    # The successful member moved; the gated and stale members did not.
    assert _stage_position(genomics_client, first) == 3
    assert _stage_position(genomics_client, second) == 2
    assert _stage_position(genomics_client, stale) == 1


def test_batch_creation_requires_a_batch_role(molecular_client: TestClient) -> None:
    denied = molecular_client.post("/batches", json={"name": "nope"})
    assert denied.status_code == 403
