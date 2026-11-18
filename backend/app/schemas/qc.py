"""QC / data-generation outcome schemas (FR-013)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QcCreate(BaseModel):
    kind: Literal["data_generation", "qc"]
    passed: bool
    detail: dict = Field(default_factory=dict)


class QcOut(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    kind: str
    passed: bool
    detail: dict
    recorded_by: uuid.UUID
    recorded_at: datetime
