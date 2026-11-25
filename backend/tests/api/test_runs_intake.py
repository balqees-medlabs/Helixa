"""US1 run & sample intake tests (T018).

Exercises POST /runs, POST /runs/{run_id}/samples, GET /runs/export against the
real API (Phase 3, US1 — contracts/endpoints.md FR-001..FR-006): molecular/admin
intake, linkage refusal (422), duplicate ngs id (409), target defaults
(30× G / 15× R, FR-003), and the molecular/admin role guard.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("database_url")


def _run_body(**overrides):
    body = {
        "run_folder": f"RUN-{uuid.uuid4().hex[:8]}",
        "instrument": "AV242301",
        "project": "AMJ",
    }
    body.update(overrides)
    return body


def _register_sample(client: TestClient) -> str:
    resp = client.post("/samples", json={"case_id": f"CASE-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_molecular_creates_run_and_records_samples(
    genomics_client: TestClient, molecular_client: TestClient
) -> None:
    sample_id = _register_sample(genomics_client)

    run = molecular_client.post("/runs", json=_run_body())
    assert run.status_code == 201, run.text
    run_body = run.json()
    assert run_body["run_folder"].startswith("RUN-")
    assert run_body["readiness"] == "received"

    recorded = molecular_client.post(
        f"/runs/{run_body['id']}/samples",
        json={
            "sample_id": sample_id,
            "ngs_sample_id": f"G-{uuid.uuid4().hex[:8]}",
            "sample_type": "G",
        },
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["sample_type"] == "G"
    assert recorded.json()["coverage_target_x"] == 30  # default for clinical G
    assert recorded.json()["pipeline_state"] == "intake"


def test_target_defaults_and_override(
    genomics_client: TestClient, molecular_client: TestClient
) -> None:
    run = molecular_client.post("/runs", json=_run_body())
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]

    r_sample = molecular_client.post(
        f"/runs/{run_id}/samples",
        json={
            "sample_id": _register_sample(genomics_client),
            "ngs_sample_id": f"R-{uuid.uuid4().hex[:8]}",
            "sample_type": "R",
        },
    )
    assert r_sample.status_code == 201, r_sample.text
    assert r_sample.json()["coverage_target_x"] == 15  # default for lifestyle R

    g_sample = molecular_client.post(
        f"/runs/{run_id}/samples",
        json={
            "sample_id": _register_sample(genomics_client),
            "ngs_sample_id": f"G2-{uuid.uuid4().hex[:8]}",
            "sample_type": "G",
            "coverage_target_x": 42,
        },
    )
    assert g_sample.status_code == 201, g_sample.text
    assert g_sample.json()["coverage_target_x"] == 42  # explicit override


def test_linkage_refused_when_sample_not_registered(molecular_client: TestClient) -> None:
    run = molecular_client.post("/runs", json=_run_body())
    run_id = run.json()["id"]
    resp = molecular_client.post(
        f"/runs/{run_id}/samples",
        json={
            "sample_id": str(uuid.uuid4()),
            "ngs_sample_id": f"NOPE-{uuid.uuid4().hex[:8]}",
            "sample_type": "G",
        },
    )
    assert resp.status_code == 422, resp.text
    assert "register the sample first" in resp.json()["detail"]


def test_duplicate_ngs_sample_id_rejected(
    genomics_client: TestClient, molecular_client: TestClient
) -> None:
    run = molecular_client.post("/runs", json=_run_body())
    run_id = run.json()["id"]
    ngs_id = f"DUP-{uuid.uuid4().hex[:8]}"
    first = molecular_client.post(
        f"/runs/{run_id}/samples",
        json={
            "sample_id": _register_sample(genomics_client),
            "ngs_sample_id": ngs_id,
            "sample_type": "G",
        },
    )
    assert first.status_code == 201, first.text
    second = molecular_client.post(
        f"/runs/{run_id}/samples",
        json={
            "sample_id": _register_sample(genomics_client),
            "ngs_sample_id": ngs_id,
            "sample_type": "G",
        },
    )
    assert second.status_code == 409, second.text


@pytest.mark.parametrize(
    "client_fixture", ["trf_client", "genomics_client", "bioinformatics_client"]
)
def test_intake_rbac(request, client_fixture: str) -> None:
    client: TestClient = request.getfixturevalue(client_fixture)
    assert client.post("/runs", json=_run_body()).status_code == 403
    assert client.get("/runs").status_code == 403


def test_export_runs_csv(molecular_client: TestClient) -> None:
    molecular_client.post("/runs", json=_run_body())
    resp = molecular_client.get("/runs/export")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "run_folder" in resp.text
