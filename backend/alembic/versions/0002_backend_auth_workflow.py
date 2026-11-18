"""backend auth & workflow support

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17

Spec 2 additive schema (data-model.md):
- auth columns on ``users`` (no credentials for the system actor)
- ``refresh_tokens`` (restricted: admin or owner)
- ``consent_items``, ``qc_results``, ``batches``, ``batch_members``,
  ``reports``, ``portal_pushes`` (operational tier)
- the Spec 1 ``fn_audit`` AFTER I/U/D trigger on every new table
- RLS: operational tier on the new operational tables; ``refresh_tokens``
  admin-or-owner; DML grants to ``helixa_app``

Authentication helpers: the Spec 1 RLS model denies every read with no
acting identity and leaves ``users``/``user_roles`` admin-only, so a fresh
login/refresh/per-request role resolution could never run as ``helixa_app``.
These SECURITY DEFINER functions (owned by the migration/BYPASSRLS role, same
pattern as Spec 1 ``fn_audit``) are the credential/role bootstrap: they expose
only the minimum needed to authenticate and are revoked from PUBLIC.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --- auth columns on users (T006) --------------------------------------------
# NULL password_hash/password_set_at until an admin sets credentials; the
# system actor never gets credentials (data-model: no creds for is_system).
ALTER_USERS_AUTH_COLUMNS = r"""
ALTER TABLE users ADD COLUMN password_hash  text;
ALTER TABLE users ADD COLUMN password_set_at timestamptz;
ALTER TABLE users ADD COLUMN last_login_at   timestamptz;
"""

# --- new tables (T007–T012) ---------------------------------------------------

CREATE_REFRESH_TOKENS = r"""
CREATE TABLE refresh_tokens (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash text        UNIQUE NOT NULL,
    family_id  uuid        NOT NULL,
    issued_at  timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
CREATE INDEX ix_refresh_tokens_user ON refresh_tokens (user_id);
"""

CREATE_CONSENT_ITEMS = r"""
CREATE TABLE consent_items (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_id    uuid        NOT NULL REFERENCES samples (id) ON DELETE CASCADE,
    item         text        NOT NULL,
    required     boolean     NOT NULL DEFAULT true,
    complete     boolean     NOT NULL DEFAULT false,
    completed_by uuid                 REFERENCES users (id),
    completed_at timestamptz,
    UNIQUE (sample_id, item)
);
"""

CREATE_QC_RESULTS = r"""
CREATE TABLE qc_results (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_id   uuid        NOT NULL REFERENCES samples (id),
    kind        text        NOT NULL CHECK (kind IN ('data_generation', 'qc')),
    passed      boolean     NOT NULL,
    detail      jsonb       NOT NULL DEFAULT '{}',
    recorded_by uuid        NOT NULL REFERENCES users (id),
    recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_qc_results_sample_kind ON qc_results (sample_id, kind);
"""

CREATE_BATCHES = r"""
CREATE TABLE batches (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text NOT NULL,
    created_by uuid NOT NULL REFERENCES users (id)
);

CREATE TABLE batch_members (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id  uuid NOT NULL REFERENCES batches (id) ON DELETE CASCADE,
    sample_id uuid NOT NULL REFERENCES samples (id) ON DELETE CASCADE,
    UNIQUE (batch_id, sample_id)
);
"""

CREATE_REPORTS = r"""
CREATE TABLE reports (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_id    uuid        NOT NULL REFERENCES samples (id),
    path         text        NOT NULL,
    content_type text        NOT NULL,
    size_bytes   bigint      NOT NULL CHECK (size_bytes > 0),
    sha256       text        NOT NULL,
    uploaded_by  uuid        NOT NULL REFERENCES users (id),
    uploaded_at  timestamptz NOT NULL DEFAULT now()
);
"""

CREATE_PORTAL_PUSHES = r"""
CREATE TABLE portal_pushes (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id       uuid        NOT NULL UNIQUE REFERENCES reports (id),
    status          text        NOT NULL DEFAULT 'queued'
                                 CHECK (status IN ('queued', 'success', 'failed')),
    attempts        integer     NOT NULL DEFAULT 0,
    last_error      text,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    delivered_at    timestamptz
);
CREATE INDEX ix_portal_pushes_queue ON portal_pushes (status, next_attempt_at);
"""

# --- Spec 1 fn_audit trigger on every new table (T013) ------------------------
NEW_TABLES: tuple[str, ...] = (
    "refresh_tokens",
    "consent_items",
    "qc_results",
    "batches",
    "batch_members",
    "reports",
    "portal_pushes",
)

# --- RLS (T014) ----------------------------------------------------------------

# refresh_tokens: admin, or the row owner (app.user_id = user_id). one FOR ALL
# policy covers SELECT/INSERT/UPDATE/DELETE for both legs.
RLS_REFRESH_TOKENS = r"""
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_refresh_tokens_all ON refresh_tokens FOR ALL
USING (
    is_admin()
    OR user_id = nullif(current_setting('app.user_id', true), '')::uuid
)
WITH CHECK (
    is_admin()
    OR user_id = nullif(current_setting('app.user_id', true), '')::uuid
);
"""

# Operational tier: same pattern as Spec 1 — any session carrying an identity
# may read; writes require the same identity. Fine-grained write gating is the
# backend's job (research D3/D4).
RLS_OPERATIONAL_TEMPLATE = r"""
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {t} FORCE  ROW LEVEL SECURITY;
CREATE POLICY p_{t}_select ON {t} FOR SELECT USING (has_identity());
CREATE POLICY p_{t}_insert ON {t} FOR INSERT WITH CHECK (has_identity());
CREATE POLICY p_{t}_update ON {t} FOR UPDATE USING (has_identity()) WITH CHECK (has_identity());
CREATE POLICY p_{t}_delete ON {t} FOR DELETE USING (has_identity());
"""

OPERATIONAL_TABLES: tuple[str, ...] = (
    "consent_items",
    "qc_results",
    "batches",
    "batch_members",
    "reports",
    "portal_pushes",
)

GRANTS_APP_ROLE = r"""
GRANT SELECT, INSERT, UPDATE, DELETE ON
    refresh_tokens, consent_items, qc_results, batches, batch_members,
    reports, portal_pushes
TO helixa_app;
"""

# --- authentication helpers (see module docstring) -----------------------------

# User + roles lookup by id (per-request identity, refresh) or by email (login).
# SECURITY DEFINER so it can read the admin-only users/user_roles tables before
# any identity exists; the caller sets app.user_id/role_names afterwards.
FN_AUTH_USER = r"""
CREATE OR REPLACE FUNCTION fn_auth_user(p_user_id uuid, p_email text DEFAULT NULL)
RETURNS TABLE (id uuid, password_hash text, is_active boolean, display_name text, role_slugs text[])
LANGUAGE sql STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
    SELECT u.id, u.password_hash, u.is_active, u.display_name,
           ARRAY(
               SELECT r.slug
               FROM user_roles ur
               JOIN roles r ON r.id = ur.role_id
               WHERE ur.user_id = u.id
               ORDER BY r.slug
           ) AS role_slugs
    FROM users u
    WHERE (p_user_id IS NOT NULL AND u.id = p_user_id AND NOT u.is_system)
       OR (p_user_id IS NULL AND p_email IS NOT NULL AND u.email = p_email
           AND NOT u.is_system)
$fn$;
"""

# Refresh-token lookup by hash. SECURITY DEFINER: at refresh time there is no
# valid access session yet, so the owner RLS policy cannot be satisfied. The
# service decides validity/rotation; raw token hashes never leave the DB row.
FN_AUTH_REFRESH_LOOKUP = r"""
CREATE OR REPLACE FUNCTION fn_auth_refresh_lookup(p_token_hash text)
RETURNS TABLE (user_id uuid, family_id uuid, expires_at timestamptz, revoked_at timestamptz)
LANGUAGE sql STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
    SELECT rt.user_id, rt.family_id, rt.expires_at, rt.revoked_at
    FROM refresh_tokens rt
    WHERE rt.token_hash = p_token_hash
$fn$;
"""

# Login touch: updates last_login_at as the definer (users is admin-only for
# writes), while the fn_audit trigger attributes the row to the caller because
# the caller MUST have set app.user_id = the logging-in user first.
FN_AUTH_TOUCH_LOGIN = r"""
CREATE OR REPLACE FUNCTION fn_auth_touch_login(p_user_id uuid) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
BEGIN
    UPDATE users SET last_login_at = now() WHERE id = p_user_id;
END;
$fn$;
"""

SECURE_FUNCTIONS = r"""
REVOKE ALL ON FUNCTION fn_auth_user(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fn_auth_user(uuid, text) TO helixa_app;
REVOKE ALL ON FUNCTION fn_auth_refresh_lookup(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fn_auth_refresh_lookup(text) TO helixa_app;
REVOKE ALL ON FUNCTION fn_auth_touch_login(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fn_auth_touch_login(uuid) TO helixa_app;
"""


def upgrade() -> None:
    # --- auth columns on users (T006) ---------------------------------------
    op.execute(ALTER_USERS_AUTH_COLUMNS)

    # --- new tables (T007–T012), parents before children ----------------------
    op.execute(CREATE_REFRESH_TOKENS)
    op.execute(CREATE_CONSENT_ITEMS)
    op.execute(CREATE_QC_RESULTS)
    op.execute(CREATE_BATCHES)
    op.execute(CREATE_REPORTS)
    op.execute(CREATE_PORTAL_PUSHES)

    # --- audit triggers on every new table (T013) -----------------------------
    for table in NEW_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_audit_{table} "
            f"AFTER INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION fn_audit()"
        )

    # --- RLS: refresh_tokens admin-or-owner; operational tier elsewhere (T014) -
    op.execute(RLS_REFRESH_TOKENS)
    for table in OPERATIONAL_TABLES:
        op.execute(RLS_OPERATIONAL_TEMPLATE.format(t=table))

    # --- grants to helixa_app (T014) ------------------------------------------
    op.execute(GRANTS_APP_ROLE)

    # --- authentication helpers ------------------------------------------------
    op.execute(FN_AUTH_USER)
    op.execute(FN_AUTH_REFRESH_LOOKUP)
    op.execute(FN_AUTH_TOUCH_LOGIN)
    op.execute(SECURE_FUNCTIONS)


def downgrade() -> None:
    # Reverse order (T015): functions, then triggers, then tables (policies and
    # grants vanish with their tables), then the users auth columns. The
    # helixa_app role is NOT dropped — owned by infra/bootstrap-app-role.sh.
    op.execute("DROP FUNCTION IF EXISTS fn_auth_touch_login(uuid)")
    op.execute("DROP FUNCTION IF EXISTS fn_auth_refresh_lookup(text)")
    op.execute("DROP FUNCTION IF EXISTS fn_auth_user(uuid, text)")

    for table in NEW_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_audit_{table} ON {table}")

    op.execute("DROP TABLE IF EXISTS portal_pushes")
    op.execute("DROP TABLE IF EXISTS reports")
    op.execute("DROP TABLE IF EXISTS batch_members")
    op.execute("DROP TABLE IF EXISTS batches")
    op.execute("DROP TABLE IF EXISTS qc_results")
    op.execute("DROP TABLE IF EXISTS consent_items")
    op.execute("DROP TABLE IF EXISTS refresh_tokens")

    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_login_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_set_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_hash")
