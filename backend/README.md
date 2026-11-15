# Helixa Backend — Data Layer (Spec 1, Database Foundation)

The data foundation for Medlabs Genomics' NGS workflow: identity, roles, the
tamper-proof audit trail, the 8-stage workflow with per-sample progression
history, vendors, the turnaround calendar, and role-based row-level security.

- **Schema**: one hand-written Alembic migration, `alembic/versions/0001_database_foundation.py`
- **Models**: SQLAlchemy 2.x mirrors in `app/db/models.py` (no business logic)
- **Session context**: `app/db/session_context.py` — transaction-scoped acting identity
- **Tests**: real-PostgreSQL suite in `tests/db/`

## Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Database connection comes from the environment (no credentials in code):

- `DATABASE_URL` — **admin** connection used by Alembic (see `../infra/.env.example`)
- `APP_DB_USER` / `APP_DB_PASSWORD` — the non-superuser `helixa_app` role the
  backend will eventually connect as; provision it with `../infra/bootstrap-app-role.sh`

## Migrations

```bash
export DATABASE_URL=postgresql://postgres:...@127.0.0.1:5432/helixa
../infra/bootstrap-app-role.sh   # once, before the first upgrade (grants target this role)
alembic upgrade head             # full schema + seed in one command
alembic downgrade base           # clean rebuild (drops everything but the helixa_app role)
alembic history                  # single linear head (0001); 0002 is reserved for Spec 4
```

Never edit a live schema by hand — changes arrive as new versioned migrations
(`0002` and beyond). Migrations run as the admin role; the application never
does. Credentials must not appear in migrations or version-controlled files
(constitution III.4).

## Setting the session context

Every transaction must carry an acting identity **before** any statement —
writes are refused (audit trigger) and reads return nothing (RLS) without one:

```python
import uuid
from sqlalchemy import text
from app.db.session_context import set_session_context

with engine.connect() as conn, conn.begin():
    set_session_context(
        conn,
        user_id=uuid.UUID("<acting user id>"),   # app.user_id
        role_names=["genomics"],                 # app.role_names (comma-joined)
        job_id=None,                             # app.job_id, for automated work
    )
    conn.execute(text("INSERT INTO samples (case_id, current_stage_id) ..."))
```

Values are transaction-scoped (`set_config(..., is_local => true)`), so they
never leak across pooled connections. Role slugs: `admin`, `genomics`, `trf`,
`molecular`, `bioinformatics`.

Key schema facts the code above relies on:

- `audit_log` and `sample_stage_events` are **append-only** (trigger-rejected
  UPDATE/DELETE for every role); audit rows are written only by the
  `SECURITY DEFINER` trigger, never by the application.
- `stages`, `stage_sla`, `vendors`, `working_calendar`, `holidays` are seeded
  reference data, administrator-editable in operation.
- `samples` are pseudonymous (`case_id`), no name/MRN columns.

## Tests

The suite runs against **real PostgreSQL** (SQLite cannot validate triggers,
RLS, or `current_setting`). By default it spins up a disposable
`postgres:16` container (testcontainers); point it at a provisioned instance
instead with:

```bash
export TEST_DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:5432/helixa_test
pytest tests/db
```

The harness (`tests/db/conftest.py`) creates the `helixa_app` role, applies
`alembic upgrade head`, and tears the schema down after the session. The
RLS tests connect as `helixa_app` — row-level security never applies to
superusers, which is exactly why the application role must stay
non-superuser.

Current coverage:

| File | Proves |
|---|---|
| `test_audit_trigger.py` | every change audited same-transaction, actor attribution (SC-001) |
| `test_append_only.py` | `audit_log` UPDATE/DELETE rejected for all roles (SC-002) |
| `test_workflow.py` | stage events + durations, SLA edits, duplicate `case_id` (FR-006/007/009) |
| `test_stages_seed.py` | 8 ordered stages, SLA split Σ=18, Friday-only calendar (FR-005/008) |
| `test_rls_visibility.py` | two-tier RLS, deny-by-default, no direct audit writes (SC-004) |
| `test_seed.py` | complete reference seed, zero human users (SC-003) |
| `test_migration_rebuild.py` | downgrade/upgrade reproduces an identical schema (SC-005) |

## Backups & restore check

```bash
../infra/backup.sh           # pg_dump -Fc → /data/backups/helixa-<ts>.dump
../infra/restore-check.sh    # backup → restore into scratch DB → diff row counts
```

See `../specs/001-database-foundation/quickstart.md` for the full validation
runbook and `../specs/001-database-foundation/data-model.md` for the
column-level schema.
