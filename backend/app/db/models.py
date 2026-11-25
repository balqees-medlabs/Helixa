"""SQLAlchemy models for the Spec 1 data layer.

Field-for-field mirrors of the schema created by migrations
``0001_database_foundation`` and ``0002_backend_auth_workflow``; no business
logic lives here.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Auth columns (0002): NULL until an admin sets credentials; the system
    # actor never gets credentials.
    password_hash: Mapped[str | None] = mapped_column(Text)
    password_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_users_is_system", "is_system", unique=True, postgresql_where=text("is_system")),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'queued'"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_jobs_status"
        ),
        Index("ix_jobs_queue", "status", "run_after"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id"))
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_table: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    before: Mapped[dict | None] = mapped_column("before", JSONB)
    after: Mapped[dict | None] = mapped_column("after", JSONB)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("action IN ('INSERT', 'UPDATE', 'DELETE')", name="ck_audit_log_action"),
        Index("ix_audit_log_entity", "entity_table", "entity_id"),
        Index("ix_audit_log_at", "at"),
    )


# --- US2: workflow model and sample progression -------------------------------


class Stage(Base):
    __tablename__ = "stages"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (CheckConstraint("position BETWEEN 1 AND 8", name="ck_stages_position"),)


class StageSla(Base):
    __tablename__ = "stage_sla"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stages.id"), nullable=False, unique=True
    )
    sla_days: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (CheckConstraint("sla_days >= 0", name="ck_stage_sla_days"),)


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    tat_days: Mapped[int] = mapped_column(Integer, nullable=False)
    tat_anchor: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Spec 4 (0003): non-secret delivery profile (T004) — nullable to preserve
    # existing rows; credentials are never part of the profile.
    delivery_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    endpoint_ref: Mapped[dict | None] = mapped_column(JSONB)
    naming_pattern: Mapped[str | None] = mapped_column(Text)
    md5_required: Mapped[bool | None] = mapped_column(Boolean)
    verification_method: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        CheckConstraint("tat_days >= 0", name="ck_vendors_tat_days"),
        CheckConstraint("tat_anchor IN ('receipt', 'sequencing')", name="ck_vendors_tat_anchor"),
        CheckConstraint("delivery_kind IN ('s3', 'sftp')", name="ck_vendors_delivery_kind"),
        CheckConstraint(
            "verification_method IN ('readback', 'receipt', 'checksum_marker')",
            name="ck_vendors_verification_method",
        ),
    )


class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    case_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    external_ref: Mapped[str | None] = mapped_column(Text)
    current_stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stages.id"), nullable=False)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vendors.id"))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'active'"))

    __table_args__ = (
        CheckConstraint("status IN ('active', 'on_hold', 'closed')", name="ck_samples_status"),
        Index("ix_samples_vendor", "vendor_id"),
    )


class SampleStageEvent(Base):
    __tablename__ = "sample_stage_events"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("samples.id"), nullable=False)
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stages.id"), nullable=False)
    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    duration_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_sample_stage_events_sample", "sample_id", "entered_at"),)


class WorkingCalendar(Base):
    __tablename__ = "working_calendar"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    weekend_days: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    label: Mapped[str | None] = mapped_column(Text)


# --- US3: role-based access ----------------------------------------------------


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "slug IN ('admin', 'genomics', 'trf', 'molecular', 'bioinformatics', "
            "'pipeline-reporter')",
            name="ck_roles_slug",
        ),
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        Index("ix_user_roles_role", "role_id"),
    )


# --- Spec 2 (0002): auth & workflow-support tables -----------------------------


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_refresh_tokens_user", "user_id"),)


class ConsentItem(Base):
    __tablename__ = "consent_items"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("samples.id", ondelete="CASCADE"), nullable=False
    )
    item: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("sample_id", "item", name="uq_consent_items_sample_item"),)


class QcResult(Base):
    __tablename__ = "qc_results"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("samples.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("kind IN ('data_generation', 'qc')", name="ck_qc_results_kind"),
        Index("ix_qc_results_sample_kind", "sample_id", "kind"),
    )


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class BatchMember(Base):
    __tablename__ = "batch_members"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), nullable=False
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("samples.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("batch_id", "sample_id", name="uq_batch_members_batch_sample"),
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("samples.id"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (CheckConstraint("size_bytes > 0", name="ck_reports_size_positive"),)


class PortalPush(Base):
    __tablename__ = "portal_pushes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reports.id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'success', 'failed')", name="ck_portal_pushes_status"
        ),
        Index("ix_portal_pushes_queue", "status", "next_attempt_at"),
    )


# --- Spec 4 (0003): NGS pipeline tables (stubs added in T002, filled in T009) ---


class SequencingRun(Base):
    __tablename__ = "sequencing_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_folder: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    instrument: Mapped[str] = mapped_column(Text, nullable=False)
    project: Mapped[str | None] = mapped_column(Text)
    run_side: Mapped[str | None] = mapped_column(String)
    run_date: Mapped[date | None] = mapped_column(Date)
    storage_location: Mapped[str | None] = mapped_column(Text)
    readiness: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'received'")
    )
    cycle_r1: Mapped[int | None] = mapped_column(Integer)
    cycle_r2: Mapped[int | None] = mapped_column(Integer)
    cycle_i1: Mapped[int | None] = mapped_column(Integer)
    cycle_i2: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "readiness IN ('received', 'ready', 'incomplete')", name="ck_sequencing_runs_readiness"
        ),
    )


class PipelineSample(Base):
    __tablename__ = "pipeline_samples"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("samples.id"), nullable=False, unique=True
    )
    ngs_sample_id: Mapped[str] = mapped_column(Text, nullable=False)
    sample_type: Mapped[str] = mapped_column(String, nullable=False)
    coverage_target_x: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vendors.id"))
    pipeline_state: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'intake'")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("sample_type IN ('G', 'R')", name="ck_pipeline_samples_sample_type"),
        CheckConstraint(
            "pipeline_state IN ('intake', 'ingested', 'converted', 'augmented', "
            "'qc_pass', 'qc_below', 'delivered')",
            name="ck_pipeline_samples_state",
        ),
    )


class MergePlanRun(Base):
    __tablename__ = "merge_plan_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    pipeline_sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_samples.id"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sequencing_runs.id"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("pipeline_sample_id", "run_id", name="uq_merge_plan_runs_sample_run"),
    )


class PipelineResult(Base):
    __tablename__ = "pipeline_results"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    pipeline_sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_samples.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    read_length: Mapped[int | None] = mapped_column(Integer)
    q30: Mapped[Decimal | None] = mapped_column(Numeric)
    reads_assigned_pct: Mapped[Decimal | None] = mapped_column(Numeric)
    source_run_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(Uuid))
    integrity_ok: Mapped[bool | None] = mapped_column(Boolean)
    plan_match: Mapped[bool | None] = mapped_column(Boolean)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    reported_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('ingest', 'conversion', 'augmentation')", name="ck_pipeline_results_kind"
        ),
        CheckConstraint("status IN ('ok', 'failed')", name="ck_pipeline_results_status"),
    )


class CoverageResult(Base):
    __tablename__ = "coverage_results"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    pipeline_sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_samples.id"), nullable=False
    )
    read_pairs: Mapped[int] = mapped_column(BigInteger, nullable=False)
    yield_gb: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    depth_x: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    target_x: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    reported_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    __table_args__ = (
        CheckConstraint("verdict IN ('pass', 'below')", name="ck_coverage_results_verdict"),
    )


class VendorDelivery(Base):
    __tablename__ = "vendor_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    pipeline_sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_samples.id"), nullable=False
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    destination_kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    verification_state: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'unverified'")
    )
    completion_marker: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    reported_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'uploading', 'delivered', 'failed')",
            name="ck_vendor_deliveries_status",
        ),
        CheckConstraint(
            "verification_state IN ('unverified', 'readback_ok', 'receipt_confirmed', "
            "'checksum_marker_ok')",
            name="ck_vendor_deliveries_verification_state",
        ),
    )


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
