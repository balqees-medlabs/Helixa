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


def downgrade() -> None:
    # Reverse dependency order; grants/policies/triggers/functions first so
    # nothing dangling survives a clean "downgrade base". (T044 extends this
    # as more tables, seeds, and RLS policies land in later phases.)
    op.execute("DROP TRIGGER IF EXISTS trg_audit_jobs ON jobs")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_users ON users")
    op.execute("DROP TRIGGER IF EXISTS trg_reject_mutation_audit_log ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS fn_audit()")
    op.execute("DROP FUNCTION IF EXISTS fn_reject_mutation()")
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP TABLE IF EXISTS jobs")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP EXTENSION IF EXISTS citext")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
