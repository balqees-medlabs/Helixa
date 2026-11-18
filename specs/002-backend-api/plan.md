# Implementation Plan: Backend API (Spec 2)

**Branch**: `002-backend-api` | **Date**: 2026-11-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-backend-api/spec.md`

## Summary

The FastAPI backend: the single writer and the sole authority for authentication, role-based access, the gated 8-stage workflow, turnaround metrics, report storage, and retryable push to the Genomic Data Portal. It sets the per-transaction acting identity that Spec 1's audit triggers and RLS depend on, enforces every stage gate server-side with optimistic concurrency, runs long portal pushes on the Spec 1 jobs worker behind an isolated client, and publishes an OpenAPI contract for the frontend. Delivered in three milestone slices matching the spec's user stories: auth/RBAC/audit (US1), the gated workflow (US2), operational support + turnaround (US3), and reports + portal (US4).

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic (migration `0002`), psycopg 3; `argon2-cffi` (password hashing), `PyJWT` (access/refresh tokens). All additive to the Spec 1 `backend/` project.

**Storage**: PostgreSQL 16 (Spec 1 schema, connected to as the non-superuser `helixa_app` role for request handling; the admin role only for migrations). Report files on the filesystem under `REPORTS_ROOT` (`/data/reports`), metadata in Postgres.

**Testing**: pytest against real PostgreSQL (extends the Spec 1 `tests/db` harness) plus FastAPI `TestClient` for API/RBAC/auth and gate tests; the portal client is mocked.

**Target Platform**: Linux server, internal network / VPN behind Caddy (TLS); backend binds to localhost/compose network only.

**Project Type**: Web application — backend layer (second of Database → Backend → Frontend).

**Performance Goals**: Standard web-service responsiveness for ~10–20 users; no high-concurrency targets. Stage advances and report reads are the hot paths (indexed in Spec 1).

**Constraints**: Backend connects as `helixa_app` (no `BYPASSRLS`); every request sets `app.user_id`/`app.role_names` via the Spec 1 session-context contract before touching data. Stage gates and the case-close rule are server-side only. Secrets from `.env`. Schema changes are Alembic-only (`0002`).

**Scale/Scope**: 4 user stories; ~8 new tables/columns in migration `0002`; ~10 routers; one portal worker; one `create-admin` CLI.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against Helixa Constitution v2.0.0:

| Article | Requirement | How this plan satisfies it | Status |
|---|---|---|---|
| I.2 | Backend owns ALL business logic; single writer | All rules (auth, RBAC, gates, SLA, case-close) live in `app/services`; only the backend writes, as `helixa_app`. | ✅ PASS |
| III.1 | Backend issues & validates JWT; token never in frontend JS | Access JWT in an httpOnly/Secure/SameSite cookie; validated by a dependency on every protected route. | ✅ PASS |
| III.2 | RBAC over the 5 roles; multi-role; admin all | Role dependency guards; roles read from the user's `user_roles`; `admin` short-circuits. | ✅ PASS |
| III.3 | RLS as second layer, acting identity per tx | A per-request dependency opens a transaction and sets `app.user_id`/`app.role_names` (Spec 1 `session_context`). | ✅ PASS |
| III.4 | Secrets only in server `.env` | Pydantic `Settings` reads `.env`; JWT key, DB creds, portal token never in code. | ✅ PASS |
| IV | Same-transaction audit; system/job attribution | Spec 1 triggers write audit; the backend sets the actor; worker sets `app.job_id`. | ✅ PASS |
| V.1–V.5 | 8 ordered stages, server-side gates, SLA, TAT | `workflow_service` enforces order + gates with optimistic concurrency; `sla_service` computes TAT against targets/calendar. | ✅ PASS |
| VI.1–VI.5 | Portal push isolated/retryable; filesystem reports | `PortalClient` behind one interface (mock default); `portal_pushes` + jobs worker with retry; reports under `REPORTS_ROOT`, served with RBAC. | ✅ PASS |
| VIII.1–VIII.7 | Migrations, pytest, OpenAPI, jobs worker | Migration `0002`; pytest for every gate/guard/auth path; FastAPI OpenAPI exported; portal worker on the `jobs` table. | ✅ PASS |

No violations. Complexity Tracking left empty.

**Note on migration numbering**: Spec 1 reserved `0002` "for Spec 4", but the backend ships before sequencer ingestion, so Spec 2 takes `0002` and Spec 4 becomes `0003+`. Recorded here so the chain stays linear.

## Project Structure

### Documentation (this feature)

```text
specs/002-backend-api/
├── plan.md              # This file
├── spec.md              # Clarified spec
├── research.md          # Phase 0 — auth, concurrency, portal, RBAC decisions
├── data-model.md        # Phase 1 — migration 0002 tables + state machine
├── quickstart.md        # Phase 1 — run & validation guide
├── contracts/           # Phase 1 — API surface + key contracts
│   ├── api-overview.md
│   ├── auth-contract.md
│   ├── workflow-contract.md
│   └── reports-portal-contract.md
└── checklists/requirements.md
```

### Source Code (repository root) — additive to the Spec 1 `backend/`

```text
backend/
├── alembic/versions/
│   └── 0002_backend_auth_workflow.py   # auth columns, refresh tokens, consent, batches, qc, reports, portal_pushes
├── app/
│   ├── main.py                 # FastAPI app, router registration, OpenAPI metadata
│   ├── cli.py                  # `python -m app.cli create-admin`
│   ├── worker.py               # jobs worker: processes portal_push jobs
│   ├── core/
│   │   ├── config.py           # Pydantic Settings from .env
│   │   ├── security.py         # argon2 hashing, JWT encode/verify, cookie helpers
│   │   └── deps.py             # get_db (sets session context), current_user, require_roles(...)
│   ├── db/                     # Spec 1 models + new models (auth cols, new tables)
│   ├── schemas/                # Pydantic request/response models
│   ├── services/
│   │   ├── auth_service.py     # login, refresh rotation, logout, account mgmt
│   │   ├── workflow_service.py # stage gates + optimistic concurrency + events
│   │   ├── batch_service.py    # batch advance/assignment
│   │   ├── qc_service.py       # data-generation & QC outcomes
│   │   ├── sla_service.py      # TAT metrics vs targets/calendar
│   │   ├── report_service.py   # upload/store/serve reports
│   │   └── portal_client.py    # isolated, mockable portal interface
│   └── api/
│       ├── auth.py  users.py  roles.py  samples.py  workflow.py
│       └── batches.py  qc.py  vendors.py  reports.py  metrics.py
└── tests/
    ├── db/                     # Spec 1 suite (unchanged) + 0002 schema tests
    └── api/                    # TestClient: auth, RBAC, gates, concurrency, reports, portal
```

**Structure Decision**: Extend the existing Spec 1 `backend/` project (constitution II: one monorepo, one backend). Business logic lives in `app/services`, HTTP shells in `app/api`, cross-cutting auth/session in `app/core/deps.py`. The portal worker reuses the Spec 1 `jobs` table and the session-context contract, so background changes are audited exactly like request changes.

## Complexity Tracking

No constitution violations — section intentionally empty.
