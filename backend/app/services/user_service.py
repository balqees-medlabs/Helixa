"""Account and role management (admin-only routes, FR-005/FR-006).

Runs under the admin request identity, so Spec 1's admin-only RLS policies on
``users``/``user_roles`` apply and every change is audited by the Spec 1
triggers. The system actor is never listed or editable.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db.session_context import ROLE_SLUGS


class UserExists(Exception):
    """Email already in use (or role already assigned)."""


class UserNotFound(Exception):
    """No such non-system user (or role assignment)."""


class UnknownRole(Exception):
    """Role slug is not one of the five known roles."""


_USER_SELECT = """
    SELECT u.id, u.email::text AS email, u.display_name, u.is_active,
           ARRAY(
               SELECT r.slug
               FROM user_roles ur
               JOIN roles r ON r.id = ur.role_id
               WHERE ur.user_id = u.id
               ORDER BY r.slug
           ) AS roles
    FROM users u
"""


def _to_dict(row) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "is_active": row["is_active"],
        "roles": list(row["roles"]),
    }


def _validate_roles(roles: list[str]) -> None:
    unknown = sorted(set(roles) - ROLE_SLUGS)
    if unknown:
        raise UnknownRole(", ".join(unknown))


def list_users(conn: Connection, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    rows = (
        conn.execute(
            text(
                f"{_USER_SELECT} WHERE NOT u.is_system ORDER BY u.display_name, u.id "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset},
        )
        .mappings()
        .all()
    )
    total = conn.execute(text("SELECT count(*) FROM users WHERE NOT is_system")).scalar_one()
    return [_to_dict(row) for row in rows], total


def get_user(conn: Connection, user_id: uuid.UUID) -> dict:
    row = (
        conn.execute(
            text(f"{_USER_SELECT} WHERE u.id = :user_id AND NOT u.is_system"),
            {"user_id": user_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise UserNotFound(str(user_id))
    return _to_dict(row)


def _insert_roles(conn: Connection, user_id: uuid.UUID, roles: list[str]) -> None:
    for slug in dict.fromkeys(roles):
        conn.execute(
            text(
                "INSERT INTO user_roles (user_id, role_id) "
                "SELECT :user_id, id FROM roles WHERE slug = :slug"
            ),
            {"user_id": user_id, "slug": slug},
        )


def create_user(
    conn: Connection,
    *,
    email: str,
    display_name: str,
    password: str,
    roles: list[str],
) -> dict:
    _validate_roles(roles)
    exists = conn.execute(
        text("SELECT 1 FROM users WHERE email = :email"), {"email": email}
    ).scalar()
    if exists:
        raise UserExists(email)

    try:
        user_id = conn.execute(
            text(
                "INSERT INTO users (email, display_name, password_hash, password_set_at) "
                "VALUES (:email, :display_name, :password_hash, now()) RETURNING id"
            ),
            {
                "email": email,
                "display_name": display_name,
                "password_hash": hash_password(password),
            },
        ).scalar_one()
        _insert_roles(conn, user_id, roles)
    except IntegrityError as exc:
        raise UserExists(email) from exc

    return get_user(conn, user_id)


def update_user(
    conn: Connection,
    user_id: uuid.UUID,
    *,
    display_name: str | None = None,
    is_active: bool | None = None,
    password: str | None = None,
) -> dict:
    get_user(conn, user_id)  # 404 for unknown/system actors

    assignments: list[str] = []
    params: dict = {"user_id": user_id}
    if display_name is not None:
        assignments.append("display_name = :display_name")
        params["display_name"] = display_name
    if is_active is not None:
        assignments.append("is_active = :is_active")
        params["is_active"] = is_active
    if password is not None:
        assignments.append("password_hash = :password_hash")
        assignments.append("password_set_at = now()")
        params["password_hash"] = hash_password(password)

    if assignments:
        conn.execute(
            text(
                f"UPDATE users SET {', '.join(assignments)} WHERE id = :user_id AND NOT is_system"
            ),
            params,
        )

    return get_user(conn, user_id)


def assign_role(conn: Connection, user_id: uuid.UUID, slug: str) -> dict:
    _validate_roles([slug])
    get_user(conn, user_id)
    try:
        conn.execute(
            text(
                "INSERT INTO user_roles (user_id, role_id) "
                "SELECT :user_id, id FROM roles WHERE slug = :slug"
            ),
            {"user_id": user_id, "slug": slug},
        )
    except IntegrityError as exc:
        raise UserExists(f"role {slug} already assigned") from exc
    return get_user(conn, user_id)


def revoke_role(conn: Connection, user_id: uuid.UUID, slug: str) -> dict:
    get_user(conn, user_id)
    result = conn.execute(
        text(
            "DELETE FROM user_roles "
            "WHERE user_id = :user_id "
            "AND role_id = (SELECT id FROM roles WHERE slug = :slug)"
        ),
        {"user_id": user_id, "slug": slug},
    )
    if result.rowcount == 0:
        raise UserNotFound(f"role {slug} not assigned")
    return get_user(conn, user_id)
