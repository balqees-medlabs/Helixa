"""database foundation

Revision ID: 0001
Revises:
Create Date: 2026-11-14

Identity, audit, and append-only guarantees (Spec 1, User Story 1):
- ``users`` and ``jobs`` identity tables
- append-only ``audit_log`` written only by the SECURITY DEFINER ``fn_audit()``
- mutation-rejection trigger on ``audit_log``
- the seeded system actor

Later phases of Spec 1 (workflow tables, RLS, seeds, downgrade) are appended
to this same migration by their tasks.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SECURITY DEFINER audit function, owned by the migration/superuser (BYPASSRLS)
# role so its INSERT into audit_log is not blocked by that table's
# FORCE ROW LEVEL SECURITY (no app-facing INSERT policy exists). A fixed
# search_path avoids definer hijacking. Raises when app.user_id is unset so
# no write can land un-attributed.
FN_AUDIT = r"""
CREATE OR REPLACE FUNCTION fn_audit() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_actor uuid;
    v_job   uuid;
BEGIN
    v_actor := nullif(current_setting('app.user_id', true), '')::uuid;
    IF v_actor IS NULL THEN
        RAISE EXCEPTION
            'audit: app.user_id is not set; refusing un-attributed % on %',
            TG_OP, TG_TABLE_NAME;
    END IF;
    v_job := nullif(current_setting('app.job_id', true), '')::uuid;

    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_log (actor_id, job_id, action, entity_table, entity_id, before, after)
        VALUES (v_actor, v_job, 'INSERT', TG_TABLE_NAME, NEW.id, NULL, to_jsonb(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_log (actor_id, job_id, action, entity_table, entity_id, before, after)
        VALUES (v_actor, v_job, 'UPDATE', TG_TABLE_NAME, NEW.id, to_jsonb(OLD), to_jsonb(NEW));
    ELSE  -- DELETE
        INSERT INTO audit_log (actor_id, job_id, action, entity_table, entity_id, before, after)
        VALUES (v_actor, v_job, 'DELETE', TG_TABLE_NAME, OLD.id, to_jsonb(OLD), NULL);
    END IF;
    RETURN NULL;
END;
$fn$;
"""

# Append-only guard: BEFORE UPDATE OR DELETE must fail outright.
FN_REJECT_MUTATION = r"""
CREATE OR REPLACE FUNCTION fn_reject_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    RAISE EXCEPTION 'append-only: % on % is rejected', TG_OP, TG_TABLE_NAME;
    RETURN NULL;
END;
$fn$;
"""

CREATE_USERS = r"""
CREATE TABLE users (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email        citext UNIQUE,
    display_name text    NOT NULL,
    is_system    boolean NOT NULL DEFAULT false,
    is_active    boolean NOT NULL DEFAULT true
);
CREATE UNIQUE INDEX uq_users_is_system ON users (is_system) WHERE is_system;
"""

CREATE_JOBS = r"""
CREATE TABLE jobs (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind       text        NOT NULL,
    status     text        NOT NULL DEFAULT 'queued'
                           CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    payload    jsonb       NOT NULL DEFAULT '{}',
    attempts   integer     NOT NULL DEFAULT 0,
    last_error text,
    run_after  timestamptz NOT NULL DEFAULT now(),
    locked_at  timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""

CREATE_AUDIT_LOG = r"""
CREATE TABLE audit_log (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id     uuid        NOT NULL REFERENCES users (id),
    job_id       uuid                 REFERENCES jobs (id),
    action       text        NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    entity_table text        NOT NULL,
    entity_id    uuid        NOT NULL,
    before       jsonb,
    after        jsonb,
    at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_log_entity ON audit_log (entity_table, entity_id);
CREATE INDEX ix_audit_log_at ON audit_log (at);
"""

# Seeded inside a DO block with app.user_id set to the actor's own id, so the
# fn_audit trigger records its creation like any other write.
SEED_SYSTEM_ACTOR = r"""
DO $seed$
DECLARE
    sys_id uuid := gen_random_uuid();
BEGIN
    PERFORM set_config('app.user_id', sys_id::text, true);
    INSERT INTO users (id, email, display_name, is_system, is_active)
    VALUES (sys_id, NULL, 'System', true, true);
END;
$seed$;
"""

# --- US2: workflow model and sample progression (T023–T031) ------------------

CREATE_STAGES = r"""
CREATE TABLE stages (
    id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    position smallint UNIQUE NOT NULL CHECK (position BETWEEN 1 AND 8),
    slug     text    UNIQUE NOT NULL,
    name     text    NOT NULL
);
"""

CREATE_STAGE_SLA = r"""
CREATE TABLE stage_sla (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stage_id   uuid        UNIQUE NOT NULL REFERENCES stages (id),
    sla_days   integer     NOT NULL CHECK (sla_days >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""

CREATE_VENDORS = r"""
CREATE TABLE vendors (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text    UNIQUE NOT NULL,
    tat_days   integer NOT NULL CHECK (tat_days >= 0),
    tat_anchor text    NOT NULL CHECK (tat_anchor IN ('receipt', 'sequencing')),
    is_active  boolean NOT NULL DEFAULT true
);
"""

CREATE_SAMPLES = r"""
CREATE TABLE samples (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id          text        UNIQUE NOT NULL,
    external_ref     text,
    current_stage_id uuid        NOT NULL REFERENCES stages (id),
    vendor_id        uuid                 REFERENCES vendors (id),
    received_at      timestamptz NOT NULL DEFAULT now(),
    status           text        NOT NULL DEFAULT 'active'
                                 CHECK (status IN ('active', 'on_hold', 'closed'))
);
"""

CREATE_SAMPLE_STAGE_EVENTS = r"""
CREATE TABLE sample_stage_events (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_id      uuid          NOT NULL REFERENCES samples (id),
    stage_id       uuid          NOT NULL REFERENCES stages (id),
    entered_at     timestamptz   NOT NULL DEFAULT now(),
    duration_hours numeric(10,2),
    actor_id       uuid          NOT NULL REFERENCES users (id),
    note           text
);
"""

# Singleton calendar: the unique index on the constant expression true allows
# exactly one row (data-model: "UNIQUE ((true))").
CREATE_WORKING_CALENDAR = r"""
CREATE TABLE working_calendar (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    weekend_days smallint[] NOT NULL
);
CREATE UNIQUE INDEX uq_working_calendar_singleton ON working_calendar ((true));
"""

CREATE_HOLIDAYS = r"""
CREATE TABLE holidays (
    id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    day   date UNIQUE NOT NULL,
    label text
);
"""

# Stage-event duration helper (data-model triggers #3): when the caller does
# not supply duration_hours, derive it from the sample's prior event. It only
# fills in the row being inserted — past rows are never touched.
FN_STAGE_EVENT_DURATION = r"""
CREATE OR REPLACE FUNCTION fn_stage_event_duration() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $fn$
BEGIN
    IF NEW.duration_hours IS NOT NULL THEN
        RETURN NEW;
    END IF;
    NEW.duration_hours := round(
        EXTRACT(EPOCH FROM (NEW.entered_at - (
            SELECT MAX(entered_at) FROM sample_stage_events WHERE sample_id = NEW.sample_id
        ))) / 3600.0,
        2
    );
    RETURN NEW;
END;
$fn$;
"""

# Seed the 8 stages with the constitution's full labels, their default SLAs
# summing to the 18-day internal target (FR-006), and one default calendar
# with weekend_days = {5} (Friday, the Medlabs work week). Run inside a DO
# block with app.user_id set to the system actor so every row is audited.
SEED_STAGES_AND_CALENDAR = r"""
DO $seed$
DECLARE
    sys_id uuid;
BEGIN
    SELECT id INTO sys_id FROM users WHERE is_system;
    PERFORM set_config('app.user_id', sys_id::text, true);

    WITH s AS (
        INSERT INTO stages (position, slug, name) VALUES
            (1, 'received',              'sample received'),
            (2, 'consent_documentation', 'consent & documentation'),
            (3, 'molecular_processing',  'molecular processing'),
            (4, 'data_generation',       'data generation'),
            (5, 'trf_preparation',       'TRF preparation'),
            (6, 'trf_confirmation',      'TRF confirmation'),
            (7, 'data_conversion_qc',    'data conversion & QC'),
            (8, 'report_upload_archive', 'report upload/archive/portal push')
        RETURNING id, position
    )
    INSERT INTO stage_sla (stage_id, sla_days)
    SELECT s.id, v.days
    FROM s
    JOIN (VALUES (1, 1), (2, 2), (3, 4), (4, 4), (5, 2), (6, 1), (7, 2), (8, 2))
         AS v(position, days) ON s.position = v.position;

    INSERT INTO working_calendar (weekend_days) VALUES (ARRAY[5]::smallint[]);
END;
$seed$;
"""

# --- US3: role-based access, second line of defense (T034–T039) --------------

CREATE_ROLES = r"""
CREATE TABLE roles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        text UNIQUE NOT NULL
                CHECK (slug IN ('admin', 'genomics', 'trf', 'molecular', 'bioinformatics')),
    description text
);

CREATE TABLE user_roles (
    id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role_id uuid NOT NULL REFERENCES roles (id),
    UNIQUE (user_id, role_id)
);
"""

SEED_ROLES = r"""
DO $seed$
DECLARE
    sys_id uuid;
BEGIN
    SELECT id INTO sys_id FROM users WHERE is_system;
    PERFORM set_config('app.user_id', sys_id::text, true);
    INSERT INTO roles (slug) VALUES
        ('admin'), ('genomics'), ('trf'), ('molecular'), ('bioinformatics');
END;
$seed$;
"""

# Row-visibility helpers (research D5): read the transaction-scoped identity
# from current_setting, tolerating unset/empty values.
CREATE_RLS_HELPERS = r"""
CREATE OR REPLACE FUNCTION app_roles() RETURNS text[]
LANGUAGE sql STABLE
SET search_path = pg_catalog, public
AS $fn$
    SELECT COALESCE(
        string_to_array(nullif(current_setting('app.role_names', true), ''), ','),
        '{}'
    )
$fn$;

CREATE OR REPLACE FUNCTION is_admin() RETURNS boolean
LANGUAGE sql STABLE
SET search_path = pg_catalog, public
AS $fn$
    SELECT 'admin' = ANY (app_roles())
$fn$;

CREATE OR REPLACE FUNCTION has_identity() RETURNS boolean
LANGUAGE sql STABLE
SET search_path = pg_catalog, public
AS $fn$
    SELECT nullif(current_setting('app.user_id', true), '') IS NOT NULL
$fn$;
"""

RESTRICTED_TABLES = ("users", "roles", "user_roles")
OPERATIONAL_TABLES = (
    "samples",
    "sample_stage_events",
    "stages",
    "stage_sla",
    "vendors",
    "working_calendar",
    "holidays",
    "jobs",
)

# Restricted tables: admin-only reads and writes. audit_log is special-cased:
# it deliberately gets NO INSERT policy, so the only way rows reach it is the
# SECURITY DEFINER fn_audit() owned by the migration (BYPASSRLS) role; reads
# are admin-only and mutation is trigger-blocked anyway (US1).
RLS_RESTRICTED = r"""
ALTER TABLE users      ENABLE ROW LEVEL SECURITY;
ALTER TABLE users      FORCE  ROW LEVEL SECURITY;
ALTER TABLE roles      ENABLE ROW LEVEL SECURITY;
ALTER TABLE roles      FORCE  ROW LEVEL SECURITY;
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_roles FORCE  ROW LEVEL SECURITY;

CREATE POLICY p_users_all      ON users      FOR ALL USING (is_admin()) WITH CHECK (is_admin());
CREATE POLICY p_roles_all      ON roles      FOR ALL USING (is_admin()) WITH CHECK (is_admin());
CREATE POLICY p_user_roles_all ON user_roles FOR ALL USING (is_admin()) WITH CHECK (is_admin());

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_audit_log_select ON audit_log FOR SELECT USING (is_admin());
CREATE POLICY p_audit_log_update ON audit_log FOR UPDATE USING (is_admin());
CREATE POLICY p_audit_log_delete ON audit_log FOR DELETE USING (is_admin());
"""

# Operational tables: any session that carries an identity (one of the five
# roles) may read; writes require the same identity. Fine-grained write gating
# is Spec 2's backend logic.
RLS_OPERATIONAL_TEMPLATE = r"""
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_{t}_select ON {t} FOR SELECT USING (has_identity());
CREATE POLICY p_{t}_insert ON {t} FOR INSERT WITH CHECK (has_identity());
CREATE POLICY p_{t}_update ON {t} FOR UPDATE USING (has_identity()) WITH CHECK (has_identity());
CREATE POLICY p_{t}_delete ON {t} FOR DELETE USING (has_identity());
"""

# DML-only grants to the pre-existing helixa_app role (created by
# infra/bootstrap-app-role.sh, not here). No INSERT on audit_log: audit rows
# are written only by the SECURITY DEFINER fn_audit() owned by the
# migration/superuser (BYPASSRLS) role, which is what lets them land under
# FORCE ROW LEVEL SECURITY. No sequences exist (uuid PKs).
GRANTS_APP_ROLE = r"""
GRANT USAGE ON SCHEMA public TO helixa_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON users, roles, user_roles TO helixa_app;
GRANT SELECT ON audit_log TO helixa_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    samples, sample_stage_events, stages, stage_sla, vendors,
    working_calendar, holidays, jobs
TO helixa_app;
"""

# --- US4: reference data and reproducibility (T043) ---------------------------

# Hot-path indexes (T046): the worker's queue lookup, the vendor FK, the
# stage-event history lookup used by fn_stage_event_duration(), and the
# user_roles FK for role-side deletes.
CREATE_INDEXES = r"""
CREATE INDEX ix_jobs_queue ON jobs (status, run_after);
CREATE INDEX ix_samples_vendor ON samples (vendor_id);
CREATE INDEX ix_sample_stage_events_sample ON sample_stage_events (sample_id, entered_at);
CREATE INDEX ix_user_roles_role ON user_roles (role_id);
"""

# The 4 named external vendors with their turnaround targets and clocks
# (FR-011, D7/D8): Centogene's TAT is counted from sequencing, the rest from
# receipt. Seeded audited under the system actor; admin-editable afterwards.
SEED_VENDORS = r"""
DO $seed$
DECLARE
    sys_id uuid;
BEGIN
    SELECT id INTO sys_id FROM users WHERE is_system;
    PERFORM set_config('app.user_id', sys_id::text, true);
    INSERT INTO vendors (name, tat_days, tat_anchor) VALUES
        ('Arcensus',  4, 'receipt'),
        ('Reviity',  28, 'receipt'),
        ('Sefdecode', 5, 'receipt'),
        ('Centogene', 30, 'sequencing');
END;
$seed$;
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # --- tables (US1: T013 users, T014 jobs, T015 audit_log) ---------------
    op.execute(CREATE_USERS)
    op.execute(CREATE_JOBS)
    op.execute(CREATE_AUDIT_LOG)

    # --- append-only guard on audit_log (T017) -----------------------------
    op.execute(FN_REJECT_MUTATION)
    op.execute(
        "CREATE TRIGGER trg_reject_mutation_audit_log "
        "BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation()"
    )

    # --- audit trigger (T016) and tracked tables (T018) --------------------
    op.execute(FN_AUDIT)
    op.execute(
        "CREATE TRIGGER trg_audit_users "
        "AFTER INSERT OR UPDATE OR DELETE ON users "
        "FOR EACH ROW EXECUTE FUNCTION fn_audit()"
    )
    op.execute(
        "CREATE TRIGGER trg_audit_jobs "
        "AFTER INSERT OR UPDATE OR DELETE ON jobs "
        "FOR EACH ROW EXECUTE FUNCTION fn_audit()"
    )

    # --- seed: the system actor (T019) -------------------------------------
    op.execute(SEED_SYSTEM_ACTOR)

    # --- US2 tables (T023–T028) --------------------------------------------
    op.execute(CREATE_STAGES)
    op.execute(CREATE_STAGE_SLA)
    op.execute(CREATE_VENDORS)
    op.execute(CREATE_SAMPLES)
    op.execute(CREATE_SAMPLE_STAGE_EVENTS)
    op.execute(CREATE_WORKING_CALENDAR)
    op.execute(CREATE_HOLIDAYS)

    # --- append-only guard on sample_stage_events (T029) --------------------
    op.execute(
        "CREATE TRIGGER trg_reject_mutation_sample_stage_events "
        "BEFORE UPDATE OR DELETE ON sample_stage_events "
        "FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation()"
    )

    # --- stage-event duration helper ----------------------------------------
    op.execute(FN_STAGE_EVENT_DURATION)
    op.execute(
        "CREATE TRIGGER trg_stage_event_duration "
        "BEFORE INSERT ON sample_stage_events "
        "FOR EACH ROW EXECUTE FUNCTION fn_stage_event_duration()"
    )

    # --- audit triggers on the US2 tables (T030) ----------------------------
    for table in (
        "stages",
        "stage_sla",
        "vendors",
        "samples",
        "sample_stage_events",
        "working_calendar",
        "holidays",
    ):
        op.execute(
            f"CREATE TRIGGER trg_audit_{table} "
            f"AFTER INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION fn_audit()"
        )

    # --- seed: stages + default SLAs + default calendar (T031) --------------
    op.execute(SEED_STAGES_AND_CALENDAR)

    # --- US3 tables + seed (T034, T035) -------------------------------------
    op.execute(CREATE_ROLES)
    op.execute(
        "CREATE TRIGGER trg_audit_roles "
        "AFTER INSERT OR UPDATE OR DELETE ON roles "
        "FOR EACH ROW EXECUTE FUNCTION fn_audit()"
    )
    op.execute(
        "CREATE TRIGGER trg_audit_user_roles "
        "AFTER INSERT OR UPDATE OR DELETE ON user_roles "
        "FOR EACH ROW EXECUTE FUNCTION fn_audit()"
    )
    op.execute(SEED_ROLES)

    # --- seed: the 4 vendors with their TAT targets (T043) -------------------
    # Seeded before RLS is enabled, consistent with the other seeds.
    op.execute(SEED_VENDORS)

    # --- RLS helpers, policies, grants (T036–T039) ---------------------------
    op.execute(CREATE_RLS_HELPERS)
    op.execute(RLS_RESTRICTED)
    for table in OPERATIONAL_TABLES:
        op.execute(RLS_OPERATIONAL_TEMPLATE.format(t=table))
    op.execute(GRANTS_APP_ROLE)

    # --- hot-path indexes (T046) ---------------------------------------------
    op.execute(CREATE_INDEXES)


def downgrade() -> None:
    # Reverse dependency order: grants first (REVOKE the schema USAGE the
    # migration granted; table-level grants vanish with their tables), then
    # triggers, functions, tables (policies and constraints go with them),
    # and finally extensions. The helixa_app role is NOT dropped — it is
    # owned by infra/bootstrap-app-role.sh, not this migration.
    op.execute("REVOKE USAGE ON SCHEMA public FROM helixa_app")
    op.execute("DROP TRIGGER IF EXISTS trg_stage_event_duration ON sample_stage_events")
    op.execute("DROP FUNCTION IF EXISTS fn_stage_event_duration()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_reject_mutation_sample_stage_events ON sample_stage_events"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_audit_user_roles ON user_roles")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_roles ON roles")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_holidays ON holidays")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_working_calendar ON working_calendar")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_sample_stage_events ON sample_stage_events")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_samples ON samples")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_vendors ON vendors")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_stage_sla ON stage_sla")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_stages ON stages")
    op.execute("DROP TABLE IF EXISTS user_roles")
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("DROP TABLE IF EXISTS holidays")
    op.execute("DROP TABLE IF EXISTS working_calendar")
    op.execute("DROP TABLE IF EXISTS sample_stage_events")
    op.execute("DROP TABLE IF EXISTS samples")
    op.execute("DROP TABLE IF EXISTS vendors")
    op.execute("DROP TABLE IF EXISTS stage_sla")
    op.execute("DROP TABLE IF EXISTS stages")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_jobs ON jobs")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_users ON users")
    op.execute("DROP TRIGGER IF EXISTS trg_reject_mutation_audit_log ON audit_log")
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP TABLE IF EXISTS jobs")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP FUNCTION IF EXISTS app_roles()")
    op.execute("DROP FUNCTION IF EXISTS is_admin()")
    op.execute("DROP FUNCTION IF EXISTS has_identity()")
    op.execute("DROP FUNCTION IF EXISTS fn_audit()")
    op.execute("DROP FUNCTION IF EXISTS fn_reject_mutation()")
    op.execute("DROP EXTENSION IF EXISTS citext")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
