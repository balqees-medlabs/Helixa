# Helixa Backend — Data Layer & API (Specs 1–2)

The single writer and authority for authentication, role-based access, the
gated 8-stage sample workflow, turnaround metrics, report storage, and
retryable push to the Genomic Data Portal. Built on the Spec 1 data foundation:
identity, roles, the tamper-proof audit trail, per-sample progression history,
vendors, the turnaround calendar, and row-level security.

- **API**: FastAPI app in `app/main.py`; routers in `app/api/`; business logic in `app/services/`
- **Schema**: Alembic migrations `0001_database_foundation.py` → `0002_backend_auth_workflow.py` (`0003` is reserved for Spec 4)
- **Models**: SQLAlchemy 2.x mirrors in `app/db/models.py` (no business logic)
- **Session context**: `app/core/deps.py` sets the acting identity per request; `app/db/session_context.py` is the low-level helper
- **Worker**: `app/worker.py` processes `portal_push` jobs
- **Tests**: real-PostgreSQL suites in `tests/db/` (schema) and `tests/api/` (HTTP/RBAC/gates)

## Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Database connection comes from the environment (no credentials in code):

- `DATABASE_URL` — **admin** connection used by Alembic and `create-admin` (see `../infra/.env.example`)
- `APP_DB_USER` / `APP_DB_PASSWORD` — the non-superuser `helixa_app` role the
  API and worker connect as; provision it with `../infra/bootstrap-app-role.sh`
- `JWT_SECRET` — access-token signing key (server-side only)
- `REPORTS_ROOT` — report filesystem root (default `/data/reports`)
- `REPORT_MAX_BYTES` / `REPORT_ALLOWED_TYPES` — upload limits (default 50 MB, `application/pdf`)
- `PORTAL_BASE_URL` / `PORTAL_TOKEN` — optional; when unset the portal client is the built-in mock
- `PORTAL_MAX_ATTEMPTS` / `PORTAL_RETRY_BACKOFF_SEC` — push retry policy

Test-only: `TEST_DATABASE_URL` points the suite at a provisioned Postgres
instead of spinning up a testcontainer.

## Migrations

```bash
export DATABASE_URL=postgresql://postgres:...@127.0.0.1:5432/helixa
../infra/bootstrap-app-role.sh   # once, before the first upgrade (grants target this role)
alembic upgrade head             # 0001 foundation + 0002 auth/workflow/reports
alembic downgrade base           # clean rebuild (drops everything but the helixa_app role)
alembic history                  # linear history: 0001 -> 0002; 0003 is free for Spec 4
```

Never edit a live schema by hand — changes arrive as new versioned migrations
(`0003` and beyond). Migrations run as the admin role; the application never
does. Credentials must not appear in migrations or version-controlled files
(constitution III.4).

## Create the first administrator

The only account-creation path that does not require an existing admin:

```bash
python -m app.cli create-admin --email admin@medlabs --name "Balqees"
# or non-interactively (e.g. provisioning): pass --password
```

It connects with the admin `DATABASE_URL`, writes an argon2id hash, and assigns
the `admin` role. Additional users are created through `POST /users` by an admin.

## Run the API and worker

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000   # API (internal-only bind)
python -m app.worker                                 # separate process: portal pushes
```

The API is fronted by Caddy (TLS); it binds to loopback only. Interactive docs
are at `/docs`, and the published contract is `openapi.json`:

```bash
python -m app.cli export-openapi    # regenerate after route/schema changes
```

## Sessions & authorization

- Login (`POST /auth/login`) sets two HttpOnly cookies: a short-lived JWT
  `access` cookie (~15 min) and an opaque `refresh` cookie scoped to `/auth`.
- Refresh rotates the token; reuse of an old refresh token revokes the family.
  Logout clears both cookies.
- Every request resolves the user from the access token, loads roles through
  the migration-owned `fn_auth_user` bootstrap, then calls
  `set_session_context` on the request transaction — so RLS and the audit
  trigger see the acting user.
- `require_roles(...)` guards routes; `admin` passes every guard, and denial is
  `403` (unauthenticated is `401`). Files are never served from a public path:
  `GET /reports/{id}/file` re-checks role and RLS.

## Tests

The suite runs against **real PostgreSQL** (SQLite cannot validate triggers,
RLS, or `current_setting`). By default it spins up a disposable
`postgres:16` container (testcontainers); point it at a provisioned instance
instead with:

```bash
export TEST_DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:5432/helixa_test
pytest tests/db tests/api
```

The harness (`tests/db/conftest.py`, re-exported by `tests/api/conftest.py`)
creates the `helixa_app` role, applies `alembic upgrade head`, and tears the
schema down after the session. API tests use `TestClient` with signed access
cookies per role; the portal client is always mocked. The RLS tests connect as
`helixa_app` — row-level security never applies to superusers, which is exactly
why the application role must stay non-superuser.

Schema coverage (`tests/db`):

| File | Proves |
|---|---|
| `test_audit_trigger.py` | every change audited same-transaction, actor attribution (SC-001) |
| `test_append_only.py` | `audit_log` UPDATE/DELETE rejected for all roles (SC-002) |
| `test_workflow.py` | stage events + durations, SLA edits, duplicate `case_id` (FR-006/007/009) |
| `test_stages_seed.py` | 8 ordered stages, SLA split Σ=18, Friday-only calendar (FR-005/008) |
| `test_rls_visibility.py` | two-tier RLS, deny-by-default, no direct audit writes (SC-004) |
| `test_seed.py` | complete reference seed, zero human users (SC-003) |
| `test_migration_rebuild.py` | downgrade/upgrade reproduces an identical schema (SC-005) |

API coverage (`tests/api`):

| File | Proves |
|---|---|
| `test_auth.py`, `test_rbac.py`, `test_audit_attribution.py` | login/refresh/logout, role guards, per-request audit attribution |
| `test_workflow_gates.py`, `test_workflow_concurrency.py` | consent/QC gates, one-step transitions, concurrent-advance conflicts |
| `test_batches.py`, `test_qc_and_metrics.py` | per-member batch results, QC gate, TAT/SLA metrics |
| `test_reports.py`, `test_portal_push.py` | upload validation/storage/RBAC, retryable idempotent push, case close |
| `test_openapi_contract.py` | committed `openapi.json` matches the app (no contract drift) |

## Backups & restore check

```bash
../infra/backup.sh           # pg_dump -Fc → /data/backups/helixa-<ts>.dump
../infra/restore-check.sh    # backup → restore into scratch DB → diff row counts
```

See `../specs/002-backend-api/quickstart.md` for the API validation runbook
(steps 1–7), `../specs/001-database-foundation/quickstart.md` for the schema
runbook, and `../specs/002-backend-api/data-model.md` /
`../specs/001-database-foundation/data-model.md` for the column-level schema.
