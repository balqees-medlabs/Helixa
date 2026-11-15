# Implementation Plan: Database Foundation (Spec 1)

**Branch**: `001-database-foundation` | **Date**: 2026-11-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-database-foundation/spec.md`

## Summary

Deliver Helixa's authoritative data layer: the schema, constraints, triggers, row-level security, and seed data that record users/roles, the 8-stage clinical workflow, every sample's progression, external vendors, queued background work, and a tamper-proof audit trail. The approach is a single Alembic migration chain owning the PostgreSQL `public` schema, with **trigger-enforced** auditability and append-only history (so no change can escape the trail regardless of the caller), and **RLS policies driven by a per-transaction session context** the backend sets. No business/workflow logic lives here — the data store only guarantees integrity; the backend (Spec 2) is the single writer that enforces stage gates and sets the acting identity.

## Technical Context

**Language/Version**: Python 3.11+ (migrations & models); SQL (DDL, PL/pgSQL triggers/policies)

**Primary Dependencies**: PostgreSQL 16; SQLAlchemy 2.x (model metadata); Alembic (migrations); psycopg (driver). Argon2 hashing is **not** in scope here (admin creation is Spec 2 / M2).

**Storage**: PostgreSQL 16 in Docker on the lab server, bound to `127.0.0.1:5432` (per `/infra` from M0). Large artifacts (reports, FASTQs) live on the filesystem, not in the database — only metadata/paths are stored.

**Testing**: pytest with a disposable Postgres (the real engine, not SQLite) — append-only rejection, RLS visibility, seed correctness, and migration reproducibility must be verified against actual Postgres trigger/policy behavior.

**Target Platform**: Linux server (Debian Trixie), internal network / VPN only.

**Project Type**: Web application — database layer (first of Database → Backend → Frontend).

**Performance Goals**: Not a bottleneck at this scale; keep audit triggers O(1) per row and index the foreign keys and the case-identifier uniqueness lookup.

**Constraints**: Backend connects as a non-superuser application role subject to RLS (no `BYPASSRLS`), so it cannot disable triggers or sidestep policies. Migrations only — no manual schema edits. Schema must rebuild from empty in one command. Sequencing-ingestion tables deferred to migration 1.1 (Spec 4).

**Scale/Scope**: ~10–20 users, five roles; thousands of samples/year; 12 tables in this feature (incl. `holidays`, split from `working_calendar`). Single database, single writer.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against Helixa Constitution v2.0.0:

| Article | Requirement | How this plan satisfies it | Status |
|---|---|---|---|
| I — Layer boundaries | DB owns schema, constraints, RLS, triggers, seed; no app logic | Only integrity rules (constraints, append-only, audit, RLS, seed). Stage-gate *ordering* logic stays in Spec 2; here stages are just ordered reference rows. Audit rows are written by triggers — an integrity rule under I.1, not business logic; this is a deliberate reading of I.2 ("single writer") that reviewers accept because it strengthens, not bypasses, the trail (see research D1). | ✅ PASS |
| III.1 — Backend issues JWT | n/a to DB layer | DB stores users/roles but performs no auth; acting identity arrives via session context. | ✅ PASS |
| III.3 — RLS as second layer | RLS enforced beneath backend guards, reading acting user/roles | Policies read `app.user_id` / `app.role_names` set by `SET LOCAL`; app role is non-superuser. | ✅ PASS |
| IV.1–IV.3 — Immutable audit | Same-transaction audit on every change; append-only audit + stage events; system actor | Generic audit **triggers** write `audit_log` in the same transaction as the change; BEFORE UPDATE/DELETE triggers reject mutation of `audit_log` and `sample_stage_events` for all roles; `system` actor seeded. | ✅ PASS |
| V.1, V.3–V.4 — Workflow integrity | 8 ordered stages, configurable SLAs, events with duration, calendar | `stages` (ordered) + `stage_sla` + `sample_stage_events` (append-only, duration) + `working_calendar`. Gate *enforcement* is Spec 2. | ✅ PASS |
| VIII.1 — Migrations only | Alembic, never manual edits | Single migration chain; seed in a migration; 1.1 reserved for Spec 4. | ✅ PASS |
| VIII.6 — Jobs table + worker | Durable job records surviving restarts | `jobs` table defined here; the worker process is Spec 2. | ✅ PASS |
| VIII.7 — Backups from first data milestone | Nightly `pg_dump`, restorable | Backup script lives in `/infra` (M0 deliverable); this feature's quickstart verifies a restore. | ✅ PASS |

No violations. Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-database-foundation/
├── plan.md              # This file
├── spec.md              # Feature spec (clarified)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — tables, constraints, triggers, RLS
├── quickstart.md        # Phase 1 output — bring-up & verification guide
├── contracts/           # Phase 1 output — schema & session-context contracts
│   ├── session-context.md
│   ├── audit-contract.md
│   └── schema-overview.md
└── checklists/
    └── requirements.md  # Spec quality checklist (passing)
```

### Source Code (repository root)

The database layer is delivered as migrations plus model metadata inside `backend/` (the schema is Python-managed via Alembic), with the running Postgres provided by `infra/`. Spec 2 later adds the FastAPI app under `backend/app/`.

```text
backend/
├── alembic/
│   ├── env.py                      # Alembic environment (reads DB URL from env)
│   ├── script.py.mako
│   └── versions/
│       └── 0001_database_foundation.py   # Schema + triggers + RLS + seed (this feature)
├── app/
│   └── db/
│       ├── __init__.py
│       ├── base.py                 # SQLAlchemy declarative metadata
│       ├── models.py               # Model classes mirroring the schema (no business logic)
│       └── session_context.py      # Contract helpers: SET LOCAL app.user_id / app.role_names
├── alembic.ini
├── pyproject.toml                  # backend deps (sqlalchemy, alembic, psycopg, pytest)
└── tests/
    └── db/
        ├── conftest.py             # Spins up a disposable Postgres, applies migrations
        ├── test_append_only.py     # UPDATE/DELETE on audit_log & sample_stage_events rejected
        ├── test_audit_trigger.py   # Every change writes a same-tx audit row; system actor
        ├── test_rls_visibility.py  # Operational roles read samples; admin-only tables hidden
        ├── test_seed.py            # 5 roles, 8 ordered stages+SLAs, 4 vendors, system actor, calendar; no human admin
        └── test_migration_rebuild.py  # Empty DB → upgrade head → full schema reproducible

infra/
├── compose.yml                     # postgres:16 (from M0) + caddy + adminer
├── backup.sh                       # nightly pg_dump -Fc + rotation (from M0)
├── bootstrap-app-role.sh           # creates the helixa_app login role from .env (this feature; keeps the credential out of migrations)
├── restore-check.sh                # backup → pg_restore into scratch DB → row-count diff (SC-006)
└── .env.example                    # DB_PASSWORD, APP_DB_USER, APP_DB_PASSWORD, etc.
```

**Structure Decision**: Single monorepo (constitution II.6). Schema artifacts sit in `backend/alembic` and `backend/app/db` because the schema is Alembic/SQLAlchemy-managed Python; this keeps one migration chain and one set of model metadata that Spec 2 builds directly upon, rather than a separate `/database` project that would fork the dependency chain. Running Postgres and backups come from `infra/` (M0).

## Complexity Tracking

No constitution violations — section intentionally empty.
