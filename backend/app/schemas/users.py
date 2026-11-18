"""User/role management schemas (admin-only routes, FR-005)."""

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=256)
    roles: list[str] = Field(min_length=1)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


class RoleAssign(BaseModel):
    slug: str = Field(min_length=1, max_length=64)


class RoleOut(BaseModel):
    slug: str
    description: str | None = None
