"""US2 stage-driving API tests (T027).

Exercises POST /samples/{id}/pipeline-results + POST /samples/{id}/coverage
through the real API as the ``pipeline-reporter`` machine identity
(contracts/stage-driving.md): in-order advance to Stage 4 on ingest, holds
out-of-order, Stage 7 needs conversion **and** a pass, BELOW blocks, and
idempotent no-double-advance.
"""

import uuid

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.session_context import set_session_context

pytestmark = pytest.mark.usefixtures("database_url")


def _register_sample(client: TestClient) -> str:
    resp = client.post("/samples", json={"case_id": f"SD-{uuid.uuid4().hex[:10]}"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _set_stage(admin_engine: Engine, sample_id: str, position: int) -> None:
    with admin_engine.connect() as conn, conn.begin():
        sys_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
        set_session_context(conn, sys_id, ("admin",))
        conn.execute(
            text(
                "UPDATE samples SET current_stage_id = "
                "(SELECT id FROM stages WHERE position = :position) WHERE id = :sample_id"
            ),
            {"position": position, "sample_id": sample_id},
        )


def _link_pipeline_sample(admin_engine: Engine, sample_id: str, sample_type: str = "G") -> None:
    """Create the pipeline_samples link that US1 intake would make, so the
    reporting endpoints find the sample (otherwise 404 PipelineSampleNotFound)."""
    with admin_engine.connect() as conn, conn.begin():
        sys_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
        set_session_context(conn, sys_id, ("admin",))
        conn.execute(
            text(
                "INSERT INTO pipeline_samples (sample_id, ngs_sample_id, sample_type, "
                "coverage_target_x, created_by) VALUES (:sid, :ngs, :type, 30, :uid)"
            ),
            {
                "sid": sample_id,
                "ngs": f"NGS-{uuid.uuid4().hex[:8]}",
                "type": sample_type,
                "uid": str(sys_id),
            },
        )


def _current_stage(client: TestClient, sample_id: str) -> dict:
    resp = client.get(f"/samples/{sample_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()["current_stage"]


def _mint_reporter_token(admin_engine: Engine) -> str:
    """Insert a fresh api_tokens row for the seeded pipeline-reporter service
    user; return the raw token (shown once)."""
    raw = f"hx-{uuid.uuid4().hex[:32]}"
    with admin_engine.connect() as conn, conn.begin():
        sys_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
        set_session_context(conn, sys_id, ("admin",))
        user_id = conn.execute(
            text(
                "SELECT u.id FROM users u "
                "JOIN user_roles ur ON ur.user_id = u.id "
                "JOIN roles r ON r.id = ur.role_id "
                "WHERE r.slug = 'pipeline-reporter' LIMIT 1"
            )
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO api_tokens (name, user_id, token_hash, created_by) "
                "VALUES (:name, :user_id, :hash, :user_id)"
            ),
            {
                "name": f"stage-driving-{uuid.uuid4().hex[:8]}",
                "user_id": str(user_id),
                "hash": PasswordHasher().hash(raw),
            },
        )
    return raw


def _report(client: TestClient, token: str, path: str, body: dict) -> object:
    return client.post(path, json=body, headers={"authorization": f"Bearer {token}"})


def test_ingest_at_stage_3_advances_to_stage_4(
    genomics_client: TestClient, admin_engine: Engine, molecular_client: TestClient
) -> None:
    sample_id = _register_sample(genomics_client)
    _set_stage(admin_engine, sample_id, 3)
    _link_pipeline_sample(admin_engine, sample_id)
    token = _mint_reporter_token(admin_engine)

    resp = _report(
        molecular_client,
        token,
        f"/samples/{sample_id}/pipeline-results",
        {"kind": "ingest", "status": "ok", "idempotency_key": f"ik-{uuid.uuid4().hex}"},
    )
    assert resp.status_code == 201, resp.text

    stage = _current_stage(molecular_client, sample_id)
    assert stage["slug"] == "data_generation"


def test_ingest_out_of_order_is_held(
    genomics_client: TestClient, admin_engine: Engine, molecular_client: TestClient
) -> None:
    sample_id = _register_sample(genomics_client)
    _set_stage(admin_engine, sample_id, 1)
    _link_pipeline_sample(admin_engine, sample_id)
    token = _mint_reporter_token(admin_engine)

    resp = _report(
        molecular_client,
        token,
        f"/samples/{sample_id}/pipeline-results",
        {"kind": "ingest", "status": "ok", "idempotency_key": f"ik-{uuid.uuid4().hex}"},
    )
    assert resp.status_code == 201, resp.text

    stage = _current_stage(molecular_client, sample_id)
    assert stage["slug"] == "received"  # still Stage 1 (received) — ingest held, not advanced


def test_duplicate_ingest_is_idempotent(
    genomics_client: TestClient, admin_engine: Engine, molecular_client: TestClient
) -> None:
    sample_id = _register_sample(genomics_client)
    _set_stage(admin_engine, sample_id, 3)
    _link_pipeline_sample(admin_engine, sample_id)
    token = _mint_reporter_token(admin_engine)
    key = f"ik-{uuid.uuid4().hex}"
    body = {"kind": "ingest", "status": "ok", "idempotency_key": key}

    first = _report(molecular_client, token, f"/samples/{sample_id}/pipeline-results", body)
    second = _report(molecular_client, token, f"/samples/{sample_id}/pipeline-results", body)
    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]

    stage = _current_stage(molecular_client, sample_id)
    assert stage["slug"] == "data_generation"


def test_coverage_pass_alone_does_not_satisfy_stage_7(
    genomics_client: TestClient, admin_engine: Engine, molecular_client: TestClient
) -> None:
    sample_id = _register_sample(genomics_client)
    _set_stage(admin_engine, sample_id, 3)
    _link_pipeline_sample(admin_engine, sample_id)
    token = _mint_reporter_token(admin_engine)

    resp = _report(
        molecular_client,
        token,
        f"/samples/{sample_id}/coverage",
        {
            "read_pairs": 1000,
            "yield_gb": 12.5,
            "depth_x": 32.0,
            "target_x": 30,
            "idempotency_key": f"ck-{uuid.uuid4().hex}",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["verdict"] == "pass"

    stage = _current_stage(molecular_client, sample_id)
    assert stage["slug"] != "data_conversion_qc"


def test_conversion_plus_coverage_pass_advances_to_stage_7(
    genomics_client: TestClient, admin_engine: Engine, molecular_client: TestClient
) -> None:
    sample_id = _register_sample(genomics_client)
    _set_stage(admin_engine, sample_id, 6)
    _link_pipeline_sample(admin_engine, sample_id)
    token = _mint_reporter_token(admin_engine)

    conv = _report(
        molecular_client,
        token,
        f"/samples/{sample_id}/pipeline-results",
        {
            "kind": "conversion",
            "status": "ok",
            "read_length": 123,
            "q30": 92.5,
            "reads_assigned_pct": 99.0,
            "idempotency_key": f"ck-{uuid.uuid4().hex}",
        },
    )
    assert conv.status_code == 201, conv.text

    cov = _report(
        molecular_client,
        token,
        f"/samples/{sample_id}/coverage",
        {
            "read_pairs": 1000,
            "yield_gb": 12.5,
            "depth_x": 30.0,
            "target_x": 30,
            "idempotency_key": f"ck2-{uuid.uuid4().hex}",
        },
    )
    assert cov.status_code == 201, cov.text

    stage = _current_stage(molecular_client, sample_id)
    assert stage["slug"] == "data_conversion_qc"


def test_below_coverage_blocks_stage_7(
    genomics_client: TestClient, admin_engine: Engine, molecular_client: TestClient
) -> None:
    sample_id = _register_sample(genomics_client)
    _set_stage(admin_engine, sample_id, 6)
    _link_pipeline_sample(admin_engine, sample_id)
    token = _mint_reporter_token(admin_engine)

    _report(
        molecular_client,
        token,
        f"/samples/{sample_id}/pipeline-results",
        {"kind": "conversion", "status": "ok", "idempotency_key": f"ck-{uuid.uuid4().hex}"},
    )
    resp = _report(
        molecular_client,
        token,
        f"/samples/{sample_id}/coverage",
        {
            "read_pairs": 1000,
            "yield_gb": 12.5,
            "depth_x": 24.0,
            "target_x": 30,
            "idempotency_key": f"ck2-{uuid.uuid4().hex}",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["verdict"] == "below"

    stage = _current_stage(molecular_client, sample_id)
    assert stage["slug"] == "trf_confirmation"  # Stage 7 not satisfied
