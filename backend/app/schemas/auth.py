"""Auth request/response schemas (contracts/auth-contract.md, api-overview.md)."""

import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    """The caller's account plus its role slugs (never any credential)."""

    id: uuid.UUID
    email: str | None
    display_name: str
    is_active: bool
    roles: list[str]
