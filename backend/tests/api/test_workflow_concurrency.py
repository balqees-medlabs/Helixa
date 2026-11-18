"""US2 optimistic concurrency (T030, SC-009 / FR-010a).

Two advances that both observed the same ``from_stage`` race for one sample:
exactly one succeeds, the other gets 409, and exactly one new stage event is
written.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core import deps
from app.core.security import ACCESS_COOKIE
from app.db.session_context import set_session_context
from app.main import app

pytestmark = pytest.mark.usefixtures("database_url")


def _signed_client(mint_token, user_id) -> TestClient:
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(ACCESS_COOKIE, mint_token(user_id))
    return client


def _advance(client: TestClient, sample_id: str):
    return client.post(f"/samples/{sample_id}/advance", json={"from_stage": 1})


def test_two_advances_from_same_stage_one_wins(
    admin_engine: Engine, _user_factory, mint_token
) -> None:
    creator = _signed_client(mint_token, _user_factory("genomics"))
    created = creator.post("/samples", json={"case_id": f"RACE-{uuid.uuid4().hex[:12]}"})
    assert created.status_code == 201, created.text
    sample_id = created.json()["id"]

    # Warm the shared engine so the worker threads do not race on construction.
    deps.get_engine()

    first = _signed_client(mint_token, _user_factory("genomics"))
    second = _signed_client(mint_token, _user_factory("genomics"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(
            future.result().status_code
            for future in (
                pool.submit(_advance, first, sample_id),
                pool.submit(_advance, second, sample_id),
            )
        )

    assert statuses == [200, 409]

    with admin_engine.connect() as conn, conn.begin():
        system_id = conn.execute(text("SELECT id FROM users WHERE is_system")).scalar_one()
        set_session_context(conn, system_id, ("admin",))
        position = conn.execute(
            text(
                "SELECT st.position FROM samples s JOIN stages st ON st.id = s.current_stage_id "
                "WHERE s.id = :sample_id"
            ),
            {"sample_id": sample_id},
        ).scalar_one()
        event_count = conn.execute(
            text(
                "SELECT count(*) FROM sample_stage_events e "
                "JOIN stages st ON st.id = e.stage_id "
                "WHERE e.sample_id = :sample_id AND st.position = 2"
            ),
            {"sample_id": sample_id},
        ).scalar_one()

    assert position == 2
    assert event_count == 1
