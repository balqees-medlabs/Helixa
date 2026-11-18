"""Admin-only account and role management (api-overview.md, FR-005)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Connection

from app.core.deps import AuthContext, get_tx, require_roles
from app.schemas.auth import UserOut
from app.schemas.base import Page
from app.schemas.users import RoleAssign, UserCreate, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])

Admin = Annotated[AuthContext, Depends(require_roles("admin"))]
Conn = Annotated[Connection, Depends(get_tx)]


def _out(user: dict) -> UserOut:
    return UserOut(**user)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="User not found")


@router.get("", response_model=Page[UserOut])
def list_users(
    _admin: Admin,
    conn: Conn,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[UserOut]:
    items, total = user_service.list_users(conn, limit=limit, offset=offset)
    return Page(items=[_out(u) for u in items], total=total, limit=limit, offset=offset)


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, _admin: Admin, conn: Conn) -> UserOut:
    try:
        created = user_service.create_user(
            conn,
            email=body.email,
            display_name=body.display_name,
            password=body.password,
            roles=body.roles,
        )
    except user_service.UnknownRole as exc:
        raise HTTPException(status_code=422, detail=f"Unknown role: {exc}") from exc
    except user_service.UserExists as exc:
        raise HTTPException(status_code=409, detail=f"User already exists: {exc}") from exc
    return _out(created)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    _admin: Admin,
    conn: Conn,
) -> UserOut:
    try:
        updated = user_service.update_user(
            conn,
            user_id,
            display_name=body.display_name,
            is_active=body.is_active,
            password=body.password,
        )
    except user_service.UserNotFound as exc:
        raise _not_found() from exc
    return _out(updated)


@router.post("/{user_id}/roles", response_model=UserOut)
def assign_role(user_id: uuid.UUID, body: RoleAssign, _admin: Admin, conn: Conn) -> UserOut:
    try:
        updated = user_service.assign_role(conn, user_id, body.slug)
    except user_service.UnknownRole as exc:
        raise HTTPException(status_code=422, detail=f"Unknown role: {exc}") from exc
    except user_service.UserNotFound as exc:
        raise _not_found() from exc
    except user_service.UserExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _out(updated)


@router.delete("/{user_id}/roles/{slug}", status_code=204)
def revoke_role(user_id: uuid.UUID, slug: str, _admin: Admin, conn: Conn) -> None:
    try:
        user_service.revoke_role(conn, user_id, slug)
    except user_service.UserNotFound as exc:
        raise HTTPException(status_code=404, detail="User or role assignment not found") from exc
