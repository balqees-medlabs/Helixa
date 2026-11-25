"""NGS pipeline tables & machine-auth support (Spec 4)

Revision ID: 0003
Revises: 0002_backend_auth_workflow
Create Date: 2026-11-25

Full Spec 4 schema — Phase 2 (Foundational, per data-model.md / contracts/):

- T003: seven new tables — ``sequencing_runs``, ``pipeline_samples``,
  ``merge_plan_runs``, ``pipeline_results``, ``coverage_results``,
  ``vendor_deliveries``, ``api_tokens`` — with data-model constraints
  (checks, PKs, FKs, unique keys)
- T004: non-secret delivery-profile columns on the existing ``vendors``
- T005: ``fn_audit()`` triggers on all seven new tables (Article IV.1)
- T006: append-only triggers on ``pipeline_results``/``coverage_results``
  (Article IV.3)
- T007: RLS + two-tier policies on the new tables (Article III.3): read for
  ``molecular``/``bioinformatics``/``admin``; ``pipeline-reporter`` gets
  scoped INSERT/UPDATE/SELECT; deny-by-default otherwise
- T008: seed the ``pipeline-reporter`` role + the non-human service user,
  and backfill the three vendor delivery profiles (Arcensus ``s3``/
  ``readback``, SelfDecode ``s3``/``receipt``, Revvity ``sftp``/
  ``checksum_marker``, ``md5_required=true``)
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES: tuple[str, ...] = (
    "sequencing_runs",
    "pipeline_samples",
    "merge_plan_runs",
    "pipeline_results",
    "coverage_results",
    "vendor_deliveries",
    "api_tokens",
)

# --- T003: new tables ------------------------------------------------------------

CREATE_SEQUENCING_RUNS = r"""
CREATE TABLE sequencing_runs (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_folder       text NOT NULL UNIQUE,
    instrument       text NOT NULL,
    project          text,
    run_side         text,
    run_date         date,
    storage_location text,
    readiness        text NOT NULL DEFAULT 'received'
                           CHECK (readiness IN ('received', 'ready', 'incomplete')),
    cycle_r1         integer,
    cycle_r2         integer,
    cycle_i1         integer,
    cycle_i2         integer,
    created_by       uuid NOT NULL REFERENCES users (id),
    created_at       timestamptz NOT NULL DEFAULT now()
);
"""

CREATE_PIPELINE_SAMPLES = r"""
CREATE TABLE pipeline_samples (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_id         uuid NOT NULL UNIQUE REFERENCES samples (id),
    ngs_sample_id     text NOT NULL,
    sample_type       text NOT NULL CHECK (sample_type IN ('G', 'R')),
    coverage_target_x integer NOT NULL,
    vendor_id         uuid REFERENCES vendors (id),
    pipeline_state    text NOT NULL DEFAULT 'intake'
                           CHECK (pipeline_state IN
                             ('intake', 'ingested', 'converted', 'augmented',
                              'qc_pass', 'qc_below', 'delivered')),
    created_by        uuid NOT NULL REFERENCES users (id),
    created_at        timestamptz NOT NULL DEFAULT now()
);
"""

CREATE_MERGE_PLAN_RUNS = r"""
CREATE TABLE merge_plan_runs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_sample_id  uuid NOT NULL REFERENCES pipeline_samples (id),
    run_id              uuid NOT NULL REFERENCES sequencing_runs (id),
    created_by          uuid NOT NULL REFERENCES users (id),
    UNIQUE (pipeline_sample_id, run_id)
);
"""

CREATE_PIPELINE_RESULTS = r"""
CREATE TABLE pipeline_results (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_sample_id uuid NOT NULL REFERENCES pipeline_samples (id),
    kind               text NOT NULL CHECK (kind IN ('ingest', 'conversion', 'augmentation')),
    status             text NOT NULL CHECK (status IN ('ok', 'failed')),
    read_length        integer,
    q30                numeric,
    reads_assigned_pct numeric,
    source_run_ids     uuid[],
    integrity_ok       boolean,
    plan_match         boolean,
    detail             jsonb NOT NULL DEFAULT '{}',
    reported_by        uuid NOT NULL REFERENCES users (id),
    reported_at        timestamptz NOT NULL DEFAULT now(),
    idempotency_key    text NOT NULL UNIQUE
);
"""

CREATE_COVERAGE_RESULTS = r"""
CREATE TABLE coverage_results (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_sample_id uuid NOT NULL REFERENCES pipeline_samples (id),
    read_pairs         bigint NOT NULL,
    yield_gb           numeric NOT NULL,
    depth_x            numeric NOT NULL,
    target_x           integer NOT NULL,
    verdict            text NOT NULL CHECK (verdict IN ('pass', 'below')),
    reported_by        uuid NOT NULL REFERENCES users (id),
    reported_at        timestamptz NOT NULL DEFAULT now(),
    idempotency_key    text NOT NULL UNIQUE
);
"""

CREATE_VENDOR_DELIVERIES = r"""
CREATE TABLE vendor_deliveries (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_sample_id uuid NOT NULL REFERENCES pipeline_samples (id),
    vendor_id          uuid NOT NULL REFERENCES vendors (id),
    destination_kind   text NOT NULL,
    status             text NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'uploading', 'delivered', 'failed')),
    verification_state text NOT NULL DEFAULT 'unverified'
                           CHECK (verification_state IN
                             ('unverified', 'readback_ok', 'receipt_confirmed',
                              'checksum_marker_ok')),
    completion_marker  text,
    evidence           jsonb NOT NULL DEFAULT '{}',
    reported_by        uuid NOT NULL REFERENCES users (id),
    reported_at        timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
"""

CREATE_API_TOKENS = r"""
CREATE TABLE api_tokens (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text NOT NULL,
    user_id    uuid NOT NULL REFERENCES users (id),
    token_hash text NOT NULL,
    created_by uuid NOT NULL REFERENCES users (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);
"""

# --- T004: vendors delivery-profile columns --------------------------------------

ALTER_VENDORS_DELIVERY_PROFILE = r"""
ALTER TABLE vendors ADD COLUMN delivery_kind text
    CHECK (delivery_kind IN ('s3', 'sftp'));
ALTER TABLE vendors ADD COLUMN endpoint_ref jsonb;
ALTER TABLE vendors ADD COLUMN naming_pattern text;
ALTER TABLE vendors ADD COLUMN md5_required boolean;
ALTER TABLE vendors ADD COLUMN verification_method text
    CHECK (verification_method IN ('readback', 'receipt', 'checksum_marker'));
"""

# --- T006: append-only guard ------------------------------------------------------

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

# --- T007: RLS + two-tier policies on the new tables ------------------------------

# Read set (T007): molecular/bioinformatics/admin per existing visibility rules.
FN_NGS_READ_ALLOWED = r"""
CREATE OR REPLACE FUNCTION fn_ngs_read_allowed() RETURNS boolean
LANGUAGE sql STABLE
SET search_path = pg_catalog, public
AS $fn$
    SELECT is_admin()
        OR 'molecular' = ANY(app_roles())
        OR 'bioinformatics' = ANY(app_roles())
$fn$;
"""

# Intake set: the run/sample entry tables are written by molecular or admin
# (POST /runs, POST /runs/{id}/samples — FR-001, D4; merge-plan — D6).
FN_NGS_INTAKE_ALLOWED = r"""
CREATE OR REPLACE FUNCTION fn_ngs_intake_allowed() RETURNS boolean
LANGUAGE sql STABLE
SET search_path = pg_catalog, public
AS $fn$
    SELECT is_admin() OR 'molecular' = ANY(app_roles())
$fn$;
"""

# The machine identity holds only this role (data-model: D-01).
FN_NGS_REPORTER = r"""
CREATE OR REPLACE FUNCTION fn_ngs_reporter() RETURNS boolean
LANGUAGE sql STABLE
SET search_path = pg_catalog, public
AS $fn$
    SELECT 'pipeline-reporter' = ANY(app_roles())
$fn$;
"""

# Baseline read policy for every new table (deny-by-default elsewhere).
RLS_READ_TEMPLATE = r"""
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_{t}_select ON {t} FOR SELECT
USING (has_identity() AND fn_ngs_read_allowed());
"""

# Reporter read tier: the runs/samples/results it reports on (FR-022), so a
# scoped SELECT works for delivery_clearance and result reads.
RLS_REPORTER_SELECT_TEMPLATE = r"""
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_{t}_select ON {t} FOR SELECT
USING (has_identity() AND (fn_ngs_read_allowed() OR fn_ngs_reporter()));
"""

# Entry tables: read (molecular/bioinformatics/admin) + molecular/admin writes.
RLS_INTAKE_TEMPLATE = r"""
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_{t}_select ON {t} FOR SELECT
USING (has_identity() AND (fn_ngs_read_allowed() OR fn_ngs_reporter()));
CREATE POLICY p_{t}_insert ON {t} FOR INSERT
WITH CHECK (fn_ngs_intake_allowed());
CREATE POLICY p_{t}_update ON {t} FOR UPDATE
USING (fn_ngs_intake_allowed()) WITH CHECK (fn_ngs_intake_allowed());
CREATE POLICY p_{t}_delete ON {t} FOR DELETE
USING (fn_ngs_intake_allowed());
"""

# Merge-plan table: read + molecular/bioinformatics/admin writes (D6).
RLS_MERGE_PLAN_TEMPLATE = r"""
ALTER TABLE merge_plan_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE merge_plan_runs FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_merge_plan_runs_select ON merge_plan_runs FOR SELECT
USING (has_identity() AND fn_ngs_read_allowed());
CREATE POLICY p_merge_plan_runs_insert ON merge_plan_runs FOR INSERT
WITH CHECK (fn_ngs_read_allowed());
CREATE POLICY p_merge_plan_runs_update ON merge_plan_runs FOR UPDATE
USING (fn_ngs_read_allowed()) WITH CHECK (fn_ngs_read_allowed());
CREATE POLICY p_merge_plan_runs_delete ON merge_plan_runs FOR DELETE
USING (fn_ngs_read_allowed());
"""

# Reporter insert tier: scoped INSERT on the reporting tables (T007).
RLS_REPORTER_INSERT_TEMPLATE = r"""
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_{t}_insert ON {t} FOR INSERT
WITH CHECK (fn_ngs_reporter());
"""

# Vendor-delivery tier (T007): reporter scoped INSERT + UPDATE on
# vendor_deliveries (mutable/audited, not append-only).
RLS_DELIVERY_TEMPLATE = r"""
ALTER TABLE vendor_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_deliveries FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_vendor_deliveries_select ON vendor_deliveries FOR SELECT
USING (has_identity() AND (fn_ngs_read_allowed() OR fn_ngs_reporter()));
CREATE POLICY p_vendor_deliveries_insert ON vendor_deliveries FOR INSERT
WITH CHECK (fn_ngs_reporter());
CREATE POLICY p_vendor_deliveries_update ON vendor_deliveries FOR UPDATE
USING (fn_ngs_reporter()) WITH CHECK (fn_ngs_reporter());
"""

# api_tokens: molecular/bioinformatics/admin read; admin mint/revoke writes.
RLS_API_TOKENS_TEMPLATE = r"""
ALTER TABLE api_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_tokens FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_api_tokens_select ON api_tokens FOR SELECT
USING (has_identity() AND fn_ngs_read_allowed());
CREATE POLICY p_api_tokens_insert ON api_tokens FOR INSERT
WITH CHECK (is_admin());
CREATE POLICY p_api_tokens_update ON api_tokens FOR UPDATE
USING (is_admin()) WITH CHECK (is_admin());
"""

GRANTS_APP_ROLE = r"""
GRANT SELECT, INSERT, UPDATE, DELETE ON
    sequencing_runs, pipeline_samples, merge_plan_runs, pipeline_results,
    coverage_results, vendor_deliveries, api_tokens
TO helixa_app;
"""

# --- T008: seeds + delivery-profile backfill --------------------------------------

# The roles.slug CHECK constraint is unnamed in 0001 (the auto name depends on
# tooling), so drop any check on the slug column before re-adding it with the
# models.py-aligned name (app/db/models.py uses name="ck_roles_slug").
DROP_ROLES_SLUG_CHECK = r"""
DO $con$
DECLARE con_name text;
BEGIN
    SELECT conname INTO con_name
    FROM pg_constraint
    WHERE conrelid = 'roles'::regclass
      AND contype = 'c'
      AND conname LIKE '%slug%';
    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE roles DROP CONSTRAINT %I', con_name);
    END IF;
END;
$con$;
"""

SEED_PIPELINE_REPORTER = r"""
DO $seed$
DECLARE
    sys_id           uuid;
    reporter_role_id uuid;
    service_user_id  uuid;
BEGIN
    SELECT id INTO sys_id FROM users WHERE is_system;
    PERFORM set_config('app.user_id', sys_id::text, true);

    INSERT INTO roles (slug) VALUES ('pipeline-reporter') ON CONFLICT DO NOTHING;
    SELECT id INTO reporter_role_id FROM roles WHERE slug = 'pipeline-reporter';

    -- Machine identity (D-01): a service user, not the single system actor;
    -- the role is what marks it non-human and narrowly scoped. Idempotent:
    -- reuse a machine user that survived a prior downgrade (it cannot be
    -- deleted once it has immutable audit history), otherwise create one.
    SELECT id INTO service_user_id FROM users
        WHERE display_name = 'Lab pipeline reporter (machine identity)'
        LIMIT 1;
    IF service_user_id IS NULL THEN
        INSERT INTO users (display_name, is_system)
            VALUES ('Lab pipeline reporter (machine identity)', false)
            RETURNING id INTO service_user_id;
    END IF;

    INSERT INTO user_roles (user_id, role_id)
        SELECT service_user_id, reporter_role_id
        WHERE NOT EXISTS (
            SELECT 1 FROM user_roles
            WHERE user_id = service_user_id AND role_id = reporter_role_id
        );
END;
$seed$;
"""

# Backfill the three current vendors with their delivery profiles
# (data-model: "The three current vendors seeded/backfilled with their
# delivery profiles (Arcensus s3/readback, SelfDecode s3/receipt, Revvity
# sftp/checksum_marker + md5_required=true)"). Match both seed and current
# spellings of the vendor names.
BACKFILL_VENDOR_PROFILES = r"""
DO $seed$
DECLARE
    sys_id uuid;
BEGIN
    SELECT id INTO sys_id FROM users WHERE is_system;
    PERFORM set_config('app.user_id', sys_id::text, true);

    UPDATE vendors SET delivery_kind = 's3', verification_method = 'readback'
        WHERE name = 'Arcensus';
    UPDATE vendors SET delivery_kind = 's3', verification_method = 'receipt'
        WHERE name IN ('Sefdecode', 'SelfDecode');
    UPDATE vendors SET delivery_kind = 'sftp', verification_method = 'checksum_marker',
                        md5_required = true
        WHERE name IN ('Revvity', 'Reviity');
END;
$seed$;
"""

# Machine-auth bootstrap (mirrors 0002 FN_AUTH_USER / FN_AUTH_REFRESH_LOOKUP,
# contracts/reporter-auth.md): SECURITY DEFINER lookup that exposes only the
# minimum needed to authenticate the service identity. ``api_tokens`` stays
# admin/molecular-read-restricted under RLS; auth verification needs the rows
# of non-revoked tokens regardless of caller identity.
FN_API_TOKEN_LOOKUP = r"""
CREATE OR REPLACE FUNCTION fn_api_token_lookup()
RETURNS TABLE (token_hash text, user_id uuid, role_slugs text[])
LANGUAGE sql STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
    SELECT a.token_hash,
           a.user_id,
           ARRAY(
               SELECT r.slug
               FROM user_roles ur
               JOIN roles r ON r.id = ur.role_id
               WHERE ur.user_id = a.user_id
               ORDER BY r.slug
           ) AS role_slugs
    FROM api_tokens a
    WHERE a.revoked_at IS NULL
$fn$;
"""

SECURE_FUNCTIONS = r"""
REVOKE ALL ON FUNCTION fn_api_token_lookup() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fn_api_token_lookup() TO helixa_app;
"""


def upgrade() -> None:
    # --- T003: seven new tables (parents before children) ------------------------
    op.execute(CREATE_SEQUENCING_RUNS)
    op.execute(CREATE_PIPELINE_SAMPLES)
    op.execute(CREATE_MERGE_PLAN_RUNS)
    op.execute(CREATE_PIPELINE_RESULTS)
    op.execute(CREATE_COVERAGE_RESULTS)
    op.execute(CREATE_VENDOR_DELIVERIES)
    op.execute(CREATE_API_TOKENS)

    # --- T004: vendors delivery profile (nullable, existing rows preserved) ------
    op.execute(ALTER_VENDORS_DELIVERY_PROFILE)

    # --- T005: audit triggers on the seven new tables (Article IV.1) ------------
    for table in NEW_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_audit_{table} "
            f"AFTER INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION fn_audit()"
        )

    # --- T006: append-only triggers on pipeline_results / coverage_results (IV.3) -
    op.execute(FN_REJECT_MUTATION)
    op.execute(
        "CREATE TRIGGER trg_append_only_pipeline_results "
        "BEFORE UPDATE OR DELETE ON pipeline_results "
        "FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_append_only_coverage_results "
        "BEFORE UPDATE OR DELETE ON coverage_results "
        "FOR EACH ROW EXECUTE FUNCTION fn_reject_mutation()"
    )

    # --- T007: RLS + two-tier policies on the new tables --------------------------
    op.execute(FN_NGS_READ_ALLOWED)
    op.execute(FN_NGS_INTAKE_ALLOWED)
    op.execute(FN_NGS_REPORTER)

    # Entry tables: read + molecular/admin writes; reporter scoped read too.
    op.execute(RLS_INTAKE_TEMPLATE.format(t="sequencing_runs"))
    op.execute(RLS_INTAKE_TEMPLATE.format(t="pipeline_samples"))
    op.execute(RLS_MERGE_PLAN_TEMPLATE)
    # Append-only reporting tables: read + reporter scoped INSERT.
    op.execute(RLS_REPORTER_SELECT_TEMPLATE.format(t="pipeline_results"))
    op.execute(RLS_REPORTER_INSERT_TEMPLATE.format(t="pipeline_results"))
    op.execute(RLS_REPORTER_SELECT_TEMPLATE.format(t="coverage_results"))
    op.execute(RLS_REPORTER_INSERT_TEMPLATE.format(t="coverage_results"))
    op.execute(RLS_DELIVERY_TEMPLATE)
    # api_tokens: molecular/bioinformatics/admin read; admin mint/revoke writes.
    op.execute(RLS_API_TOKENS_TEMPLATE)

    op.execute(GRANTS_APP_ROLE)

    # --- T008: seed the pipeline-reporter role + service user; backfill vendors ---
    op.execute(DROP_ROLES_SLUG_CHECK)
    op.execute(
        "ALTER TABLE roles ADD CONSTRAINT ck_roles_slug CHECK "
        "(slug IN ('admin', 'genomics', 'trf', 'molecular', 'bioinformatics', "
        "'pipeline-reporter'))"
    )
    op.execute(SEED_PIPELINE_REPORTER)
    op.execute(BACKFILL_VENDOR_PROFILES)
    op.execute(FN_API_TOKEN_LOOKUP)
    op.execute(SECURE_FUNCTIONS)


def downgrade() -> None:
    # T008 (newest): clear vendor delivery profiles; drop the service user + role.
    # (The audit trigger on vendors requires an acting identity, like the
    # seeds above.)
    op.execute(
        """
        DO $d$
        DECLARE
            sys_id uuid;
        BEGIN
            SELECT id INTO sys_id FROM users WHERE is_system;
            PERFORM set_config('app.user_id', sys_id::text, true);
            UPDATE vendors
               SET delivery_kind = NULL, endpoint_ref = NULL, naming_pattern = NULL,
                   md5_required = NULL, verification_method = NULL;
        END;
        $d$;
        """
    )
    # T006: append-only triggers (fn_reject_mutation is 0001/0002's, reused).
    op.execute("DROP TRIGGER IF EXISTS trg_append_only_pipeline_results ON pipeline_results")
    op.execute("DROP TRIGGER IF EXISTS trg_append_only_coverage_results ON coverage_results")

    # T005: audit triggers.
    for table in NEW_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_audit_{table} ON {table}")

    # T003: tables (policies and grants vanish with them), children first.
    # Dropped BEFORE removing the service user so their FKs (api_tokens.user_id,
    # *_results.reported_by, …) no longer reference it.
    op.execute("DROP TABLE IF EXISTS api_tokens")
    op.execute("DROP TABLE IF EXISTS vendor_deliveries")
    op.execute("DROP TABLE IF EXISTS coverage_results")
    op.execute("DROP TABLE IF EXISTS pipeline_results")
    op.execute("DROP TABLE IF EXISTS merge_plan_runs")
    op.execute("DROP TABLE IF EXISTS pipeline_samples")
    op.execute("DROP TABLE IF EXISTS sequencing_runs")

    # Now remove the pipeline-reporter role + service user. The service user is
    # deleted only when nothing immutably references it: once it has posted an
    # audited result, audit_log.actor_id references it forever (append-only, like
    # the system actor), so it is left in place and the idempotent upgrade seed
    # reuses it. Its user_roles and the role are always removed.
    op.execute(
        """
        DO $d$
        DECLARE
            sys_id           uuid;
            reporter_role_id uuid;
            service_user_id  uuid;
        BEGIN
            SELECT id INTO sys_id FROM users WHERE is_system;
            PERFORM set_config('app.user_id', sys_id::text, true);
            SELECT id INTO reporter_role_id
              FROM roles WHERE slug = 'pipeline-reporter';
            IF reporter_role_id IS NOT NULL THEN
                SELECT ur.user_id INTO service_user_id
                  FROM user_roles ur WHERE ur.role_id = reporter_role_id LIMIT 1;
                DELETE FROM user_roles WHERE role_id = reporter_role_id;
                IF service_user_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM audit_log WHERE actor_id = service_user_id
                   ) THEN
                    DELETE FROM users WHERE id = service_user_id;
                END IF;
                DELETE FROM roles WHERE id = reporter_role_id;
            END IF;
        END;
        $d$;
        """
    )

    # T007: RLS helpers (policies vanish with their tables; drop after T003).
    op.execute("DROP FUNCTION IF EXISTS fn_ngs_read_allowed()")
    op.execute("DROP FUNCTION IF EXISTS fn_ngs_intake_allowed()")
    op.execute("DROP FUNCTION IF EXISTS fn_ngs_reporter()")

    # T004: vendors delivery-profile columns.
    op.execute("ALTER TABLE vendors DROP COLUMN IF EXISTS delivery_kind")
    op.execute("ALTER TABLE vendors DROP COLUMN IF EXISTS endpoint_ref")
    op.execute("ALTER TABLE vendors DROP COLUMN IF EXISTS naming_pattern")
    op.execute("ALTER TABLE vendors DROP COLUMN IF EXISTS md5_required")
    op.execute("ALTER TABLE vendors DROP COLUMN IF EXISTS verification_method")

    # roles slug check back to 0001's constraint set.
    op.execute("ALTER TABLE roles DROP CONSTRAINT IF EXISTS ck_roles_slug")
    op.execute(
        "ALTER TABLE roles ADD CONSTRAINT roles_slug_check "
        "CHECK (slug IN ('admin', 'genomics', 'trf', 'molecular', 'bioinformatics'))"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_api_token_lookup()")
