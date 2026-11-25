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
    """Flat delivery-profile fields (T004, contracts/endpoints.md): no
    credentials are accepted or stored (FR-021)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    tat_days: int | None = Field(default=None, ge=0)
    tat_anchor: Literal["receipt", "sequencing"] | None = None
    is_active: bool | None = None
    delivery_kind: Literal["s3", "sftp"] | None = None
    endpoint_ref: dict | None = None
    naming_pattern: str | None = Field(default=None, max_length=500)
    md5_required: bool | None = None
    verification_method: Literal["readback", "receipt", "checksum_marker"] | None = None


class VendorOut(BaseModel):
    id: uuid.UUID
    name: str
    tat_days: int
    tat_anchor: str
    is_active: bool
    delivery_kind: str | None
    endpoint_ref: dict | None
    naming_pattern: str | None
    md5_required: bool | None
    verification_method: str | None
