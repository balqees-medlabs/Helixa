"""Batch grouping and per-member advance schemas (FR-012)."""

import uuid

from pydantic import BaseModel, Field


class BatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class BatchMembers(BaseModel):
    sample_ids: list[uuid.UUID] = Field(min_length=1)


class BatchOut(BaseModel):
    id: uuid.UUID
    name: str
    created_by: uuid.UUID
    member_ids: list[uuid.UUID]


class BatchAdvanceRequest(BaseModel):
    from_stage: int | None = Field(
        default=None,
        ge=1,
        le=8,
        description="Optional observed stage; when omitted, each member's current stage is used.",
    )
    to_stage: int | None = Field(default=None, ge=1, le=8)
    note: str | None = Field(default=None, max_length=2000)


class MemberAdvanceResult(BaseModel):
    sample_id: uuid.UUID
    status: str
    detail: str | None = None
    from_stage: int | None = None
    to_stage: int | None = None
