"""US1 role guards (T022, SC-002).

Every role is checked on the admin-only management routes (denied for the four
non-admin roles, allowed for admin) and on the any-authenticated ``/roles``
route (allowed for all five). Admin passes every guard.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.usefixtures("database_url")

NON_ADMIN_FIXTURES = ("genomics_client", "trf_client", "molecular_client", "bioinformatics_client")

NEW_USER = {
    "email": "rbac-created@test.local",
    "display_name": "RBAC Created",
    "password": "correct-horse-battery",
    "roles": ["genomics"],
}


def test_unauthenticated_management_route_is_401() -> None:
    client = TestClient(app, base_url="https://testserver")
    assert client.get("/users").status_code == 401


@pytest.mark.parametrize("fixture_name", NON_ADMIN_FIXTURES)
def test_non_admin_is_denied_management_routes(fixture_name, request) -> None:
    client: TestClient = request.getfixturevalue(fixture_name)

    assert client.get("/users").status_code == 403
    assert client.post("/users", json=NEW_USER).status_code == 403


def test_admin_is_allowed_management_routes(admin_client: TestClient) -> None:
    assert admin_client.get("/users").status_code == 200
    assert admin_client.get("/roles").status_code == 200


@pytest.mark.parametrize(
    "fixture_name",
    ("admin_client", *NON_ADMIN_FIXTURES),
)
def test_all_roles_can_list_roles(fixture_name, request) -> None:
    client: TestClient = request.getfixturevalue(fixture_name)
    response = client.get("/roles")
    assert response.status_code == 200
    slugs = {role["slug"] for role in response.json()}
    assert slugs == {"admin", "genomics", "trf", "molecular", "bioinformatics"}
