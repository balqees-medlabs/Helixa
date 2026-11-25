"""Spec 4 (0003) NGS pipeline schemas — mirrors of the migration data model."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    run_folder: str = Field(min_length=1, max_length=200)
    instrument: str = Field(min_length=1, max_length=200)
    project: str | None = Field(default=None, max_length=200)
    run_side: str | None = Field(default=None, max_length=200)
    run_date: date | None = None
    storage_location: str | None = Field(default=None, max_length=500)
    cycle_r1: int | None = Field(default=None, ge=0)
    cycle_r2: int | None = Field(default=None, ge=0)
    cycle_i1: int | None = Field(default=None, ge=0)
    cycle_i2: int | None = Field(default=None, ge=0)


class RunOut(BaseModel):
    id: uuid.UUID
    run_folder: str
    instrument: str
    project: str | None
    run_side: str | None
    run_date: date | None
    storage_location: str | None
    readiness: str
    cycle_r1: int | None
    cycle_r2: int | None
    cycle_i1: int | None
    cycle_i2: int | None
    created_by: uuid.UUID
    created_at: datetime


class PipelineSampleCreate(BaseModel):
    sample_id: uuid.UUID  # link to the existing workflow Sample (D4)
    ngs_sample_id: str = Field(min_length=1, max_length=200)
    sample_type: Literal["G", "R"]
    coverage_target_x: int | None = Field(default=None, ge=1)  # default 30 (G) / 15 (R)
    vendor_id: uuid.UUID | None = None


class PipelineSampleOut(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    ngs_sample_id: str
    sample_type: str
    coverage_target_x: int
    vendor_id: uuid.UUID | None
    pipeline_state: str
    created_by: uuid.UUID
    created_at: datetime


class MergePlanSet(BaseModel):
    run_ids: list[uuid.UUID] = Field(min_length=1)


class MergePlanOut(BaseModel):
    pipeline_sample_id: uuid.UUID
    run_ids: list[uuid.UUID]


class PipelineResultCreate(BaseModel):
    kind: Literal["ingest", "conversion", "augmentation"]
    status: Literal["ok", "failed"] = "ok"
    read_length: int | None = Field(default=None, ge=0)
    q30: float | None = None
    reads_assigned_pct: float | None = Field(default=None, ge=0, le=100)
    source_run_ids: list[uuid.UUID] | None = None
    integrity_ok: bool | None = None
    plan_match: bool | None = None
    detail: dict = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=500)


class PipelineResultOut(BaseModel):
    id: uuid.UUID
    pipeline_sample_id: uuid.UUID
    kind: str
    status: str
    read_length: int | None
    q30: float | None
    reads_assigned_pct: float | None
    source_run_ids: list[uuid.UUID] | None
    integrity_ok: bool | None
    plan_match: bool | None
    detail: dict
    reported_by: uuid.UUID
    reported_at: datetime
    idempotency_key: str


class CoverageCreate(BaseModel):
    read_pairs: int = Field(ge=0)
    yield_gb: float
    depth_x: float
    target_x: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=500)


class CoverageOut(BaseModel):
    id: uuid.UUID
    pipeline_sample_id: uuid.UUID
    read_pairs: int
    yield_gb: float
    depth_x: float
    target_x: int
    verdict: str
    reported_by: uuid.UUID
    reported_at: datetime
    idempotency_key: str


class DeliveryCreate(BaseModel):
    vendor_id: uuid.UUID


class DeliveryUpdate(BaseModel):
    status: Literal["pending", "uploading", "delivered", "failed"] | None = None
    verification_state: (
        Literal["unverified", "readback_ok", "receipt_confirmed", "checksum_marker_ok"] | None
    ) = None
    completion_marker: str | None = Field(default=None, max_length=500)
    evidence: dict | None = None


class DeliveryOut(BaseModel):
    id: uuid.UUID
    pipeline_sample_id: uuid.UUID
    vendor_id: uuid.UUID
    destination_kind: str
    status: str
    verification_state: str
    completion_marker: str | None
    evidence: dict
    reported_by: uuid.UUID
    reported_at: datetime
    updated_at: datetime


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: Literal["pipeline-reporter"] = "pipeline-reporter"


class ApiTokenOut(BaseModel):
    id: uuid.UUID
    name: str
    user_id: uuid.UUID
    created_by: uuid.UUID
    created_at: datetime
    revoked_at: datetime | None


class ApiTokenMintedOut(ApiTokenOut):
    token: str  # returned once, never persisted
