# Quickstart & Validation: Backend API

**Feature**: 002-backend-api · Proves the backend end-to-end against real PostgreSQL. Run/verify guide, not implementation.

## Prerequisites
- Spec 1 applied; PostgreSQL 16 reachable; `helixa_app` role provisioned (`infra/bootstrap-app-role.sh`).
- `backend/` env with the new deps (`fastapi`, `pydantic`, `argon2-cffi`, `pyjwt`, `uvicorn`, `httpx` for tests).
- `.env`: `DATABASE_URL`, `JWT_SECRET`, `REPORTS_ROOT`, session lifetimes, `PORTAL_*` (optional; mock if absent).

## 1. Migrate & create the first admin
```bash
cd backend
alembic upgrade head                      # applies 0002
python -m app.cli create-admin --email admin@medlabs --name "Balqees"   # prompts for password
```
Expect: `0002` applied; one human admin exists with an argon2 hash. → FR-006.

## 2. Run the API and worker
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m app.worker          # separate process: portal_push jobs
```

## 3. Auth & RBAC  → SC-001/002
- `POST /auth/login` as admin → cookies set; `GET /auth/me` → admin + roles.
- Call any protected route without cookies → `401`.
- Create a `genomics` user; sign in; call an admin-only route → `403`; call a genomics route → ok.
- `POST /auth/refresh` rotates; reusing the old refresh token → `401` + family revoked; `logout` then protected route → `401`.

## 4. Gated workflow  → SC-004/009
- Register a sample; advance toward molecular processing with consent incomplete → `409` (reason); complete consent → advance ok.
- Attempt a skip-a-stage advance → `409`.
- Fire two concurrent advances (same `from_stage`) → exactly one `200`, one `409`; one new event row.

## 5. QC, metrics, batch  → SC-005
- Record a `qc` fail → report upload blocked; record a pass → unblocked.
- `GET /metrics/tat` reflects recorded durations; `PATCH` a stage SLA → future only, past durations unchanged.
- Batch-advance several samples → per-member results; a gated member fails without blocking others.

## 6. Reports & portal  → SC-006/007
- Upload a non-PDF → `415`; oversize → `413`; valid PDF for a QC-passed sample → stored (+ `portal_pushes` queued).
- Unauthorized role GETs the file → `403`/`404`.
- With the mock set to fail once: the worker records the error and auto-retries with backoff (push stays `queued` under the attempt cap, case stays open); the next worker run succeeds, `delivered_at` is set, no duplicate, sample `status='closed'`. A push that reaches the attempt cap stays `failed`; `POST /portal-pushes/{id}/retry` re-queues it only while under the cap.

## 7. Contract & audit  → SC-003/008
- Export OpenAPI (`python -m app.cli export-openapi`) → matches the committed `openapi.json` (no drift).
- Every write in the steps above produced an attributed `audit_log` row; none un-attributed.

## Automated equivalent
`tests/api/` (TestClient) + `tests/db/` (0002 schema) mirror all of the above against a disposable Postgres with the portal client mocked. Green suite = acceptance.
