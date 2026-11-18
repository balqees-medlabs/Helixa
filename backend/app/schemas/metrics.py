"""Turnaround metrics and stage-SLA schemas (FR-015, SC-005)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.samples import StageOut


class SlaUpdate(BaseModel):
    sla_days: int = Field(ge=0)


class StageSlaOut(BaseModel):
    stage_id: uuid.UUID
    position: int
    slug: str
    name: str
    sla_days: int
    updated_at: datetime


class StageMetric(BaseModel):
    stage_id: uuid.UUID
    position: int
    slug: str
    name: str
    sla_days: int | None
    duration_hours: float | None
    breached: bool | None


class VendorSampleMetric(BaseModel):
    id: uuid.UUID
    name: str
    tat_days: int
    tat_anchor: str
    anchor_at: datetime | None
    elapsed_days: float | None
    breached: bool | None


class SampleTat(BaseModel):
    sample_id: uuid.UUID
    case_id: str
    status: str
    current_stage: StageOut
    received_at: datetime
    elapsed_calendar_days: float
    elapsed_working_days: int
    target_days: int
    target_breached: bool
    baseline_working_days: int
    baseline_breached: bool
    stages: list[StageMetric]
    vendor: VendorSampleMetric | None


class VendorTatSummary(BaseModel):
    vendor_id: uuid.UUID
    name: str
    tat_days: int
    tat_anchor: str
    assigned_samples: int
    breached_samples: int


class TatMetrics(BaseModel):
    generated_at: datetime
    target_days: int
    baseline_working_days: int
    samples: list[SampleTat]
    vendors: list[VendorTatSummary]
