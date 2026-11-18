"""Vendor management schemas (FR-014)."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class VendorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    tat_days: int = Field(ge=0)
    tat_anchor: Literal["receipt", "sequencing"]
    is_active: bool = True


class VendorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    tat_days: int | None = Field(default=None, ge=0)
    tat_anchor: Literal["receipt", "sequencing"] | None = None
    is_active: bool | None = None


class VendorOut(BaseModel):
    id: uuid.UUID
    name: str
    tat_days: int
    tat_anchor: str
    is_active: bool
