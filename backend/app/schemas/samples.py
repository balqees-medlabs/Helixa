"""Sample registration, workflow and consent schemas (workflow-contract.md)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class StageOut(BaseModel):
    position: int
    slug: str
    name: str


class SampleCreate(BaseModel):
    case_id: str = Field(min_length=1, max_length=200)
    external_ref: str | None = Field(default=None, max_length=200)
    vendor_id: uuid.UUID | None = None


class SampleOut(BaseModel):
    id: uuid.UUID
    case_id: str
    external_ref: str | None
    vendor_id: uuid.UUID | None
    received_at: datetime
    status: str
    current_stage: StageOut


class SampleEventOut(BaseModel):
    id: uuid.UUID
    stage: StageOut
    entered_at: datetime
    duration_hours: float | None
    actor_id: uuid.UUID
    note: str | None


class ConsentItemIn(BaseModel):
    item: str = Field(min_length=1, max_length=200)
    complete: bool
    required: bool = True


class ConsentRequest(BaseModel):
    items: list[ConsentItemIn] = Field(min_length=1)


class ConsentItemOut(BaseModel):
    item: str
    required: bool
    complete: bool
    completed_by: uuid.UUID | None
    completed_at: datetime | None


class ConsentOut(BaseModel):
    sample_id: uuid.UUID
    items: list[ConsentItemOut]
    required_complete: bool


class AdvanceRequest(BaseModel):
    from_stage: int = Field(ge=1, le=8, description="The client's observed stage position.")
    to_stage: int | None = Field(
        default=None,
        ge=1,
        le=8,
        description="Optional target; must equal from_stage + 1.",
    )
    note: str | None = Field(default=None, max_length=2000)
