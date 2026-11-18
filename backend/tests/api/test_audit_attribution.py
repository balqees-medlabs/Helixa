"""US1 audit attribution (T023, SC-003).

A create and an update performed through the API must produce ``audit_log``
rows attributed to the acting user (same request transaction, via the Spec 1
trigger). No un-attributed writes are allowed.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.security import ACCESS_COOKIE
from app.db.session_context import set_session_context
from app.main import app

pytestmark = pytest.mark.usefixtures("database_url")


def test_api_writes_are_audited_as_the_acting_user(
    admin_engine: Engine, _user_factory, mint_token
) -> None:
    admin_id = _user_factory("admin")
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(ACCESS_COOKIE, mint_token(admin_id))

    email = f"audited-{uuid.uuid4().hex[:10]}@test.local"
    created = client.post(
        "/users",
        json={
            "email": email,
            "display_name": "Audited User",
            "password": "correct-horse-battery",
            "roles": ["genomics"],
        },
    )
    assert created.status_code == 201, created.text
    new_id = created.json()["id"]

    updated = client.patch(f"/users/{new_id}", json={"display_name": "Renamed User"})
    assert updated.status_code == 200, updated.text

    with admin_engine.connect() as conn, conn.begin():
        set_session_context(conn, admin_id, ("admin",))

        insert_row = (
            conn.execute(
                text(
                    "SELECT actor_id FROM audit_log "
                    "WHERE entity_table = 'users' AND entity_id = :id AND action = 'INSERT'"
                ),
                {"id": new_id},
            )
            .mappings()
            .first()
        )
        assert insert_row is not None, "user INSERT must be audited"
        assert insert_row["actor_id"] == admin_id

        update_row = (
            conn.execute(
                text(
                    "SELECT actor_id FROM audit_log "
                    "WHERE entity_table = 'users' AND entity_id = :id AND action = 'UPDATE'"
                ),
                {"id": new_id},
            )
            .mappings()
            .first()
        )
        assert update_row is not None, "user UPDATE must be audited"
        assert update_row["actor_id"] == admin_id

        role_row = (
            conn.execute(
                text(
                    "SELECT actor_id FROM audit_log "
                    "WHERE entity_table = 'user_roles' AND action = 'INSERT' "
                    "AND (after ->> 'user_id')::uuid = :id"
                ),
                {"id": new_id},
            )
            .mappings()
            .first()
        )
        assert role_row is not None, "role assignment must be audited"
        assert role_row["actor_id"] == admin_id

        unattributed = conn.execute(
            text("SELECT count(*) FROM audit_log WHERE actor_id IS NULL")
        ).scalar_one()
        assert unattributed == 0
