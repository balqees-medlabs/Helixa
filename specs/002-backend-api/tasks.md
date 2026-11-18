---

description: "Task list for Backend API (Spec 2)"
---

# Tasks: Backend API (Spec 2)

**Input**: Design documents from `/specs/002-backend-api/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED. SC-001…SC-009 and constitution VIII.2 require tests for every auth path, RBAC guard, and stage-gate rule; the portal client is always mocked. Test tasks are first-class.

**Organization**: Grouped by user story (US1–US4). Additive to the Spec 1 `backend/` project. All schema lands in one migration `0002_backend_auth_workflow.py`, so its DDL tasks are sequential (no `[P]`); services, routers, and test files are separate files and parallelize where noted.

## Format: `[ID] [P?] [Story?] Description with file path`

- `[P]` = different files, no incomplete dependency
- `[US#]` = user story; omitted for Setup/Foundational/Polish
- Paths are repo-relative under `backend/`.

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Add backend API dependencies to `backend/pyproject.toml`: `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `argon2-cffi`, `pyjwt`, and dev `httpx` (TestClient); keep SQLAlchemy/Alembic/psycopg from Spec 1
- [X] T002 [P] Create `backend/app/core/config.py` — Pydantic `Settings` reading from `.env`: `DATABASE_URL`, `APP_DB_USER/PASSWORD`, `JWT_SECRET`, `ACCESS_TTL_MIN` (default 15), `REFRESH_IDLE_H` (default 12), `REFRESH_ABSOLUTE_D` (default 7), `REPORTS_ROOT` (default `/data/reports`), `REPORT_MAX_BYTES` (default 52428800), `REPORT_ALLOWED_TYPES` (default `application/pdf`), `PORTAL_BASE_URL`/`PORTAL_TOKEN` (optional)
- [X] T003 [P] Add API env keys to `infra/.env.example` (JWT_SECRET, REPORTS_ROOT, session TTLs, REPORT_*, PORTAL_*)
- [X] T004 Create `backend/app/main.py` — FastAPI app with OpenAPI metadata and a health route; routers registered in later phases. Document the internal-only bind (serve via `uvicorn --host 127.0.0.1`, fronted by Caddy from M0) so the backend never listens on the LAN interface directly (FR-021)

**Checkpoint**: app imports and serves `/health`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: no user story work begins until this is complete.

- [X] T005 Create migration `backend/alembic/versions/0002_backend_auth_workflow.py` (down_revision `0001`) scaffold with `upgrade`/`downgrade`
- [X] T006 In `0002`, add auth columns to `users`: `password_hash text NULL`, `password_set_at timestamptz NULL`, `last_login_at timestamptz NULL` (no creds for the system actor)
- [X] T007 In `0002`, create `refresh_tokens` (`user_id` FK→users ON DELETE CASCADE, `token_hash text UNIQUE NOT NULL`, `family_id uuid NOT NULL`, `issued_at`, `expires_at NOT NULL`, `revoked_at NULL`; indexes `(user_id)`,`(token_hash)`)
- [X] T008 In `0002`, create `consent_items` (`sample_id` FK→samples ON DELETE CASCADE, `item text NOT NULL`, `required boolean NOT NULL DEFAULT true`, `complete boolean NOT NULL DEFAULT false`, `completed_by` FK→users NULL, `completed_at NULL`, `UNIQUE(sample_id,item)`)
- [X] T009 In `0002`, create `qc_results` (`sample_id` FK→samples NOT NULL, `kind text NOT NULL CHECK (kind IN ('data_generation','qc'))`, `passed boolean NOT NULL`, `detail jsonb NOT NULL DEFAULT '{}'`, `recorded_by` FK→users NOT NULL, `recorded_at`; index `(sample_id, kind)`)
- [X] T010 In `0002`, create `batches` (`name text NOT NULL`, `created_by` FK→users NOT NULL) and `batch_members` (`batch_id` FK→batches ON DELETE CASCADE, `sample_id` FK→samples ON DELETE CASCADE, `UNIQUE(batch_id, sample_id)`)
- [X] T011 In `0002`, create `reports` (`sample_id` FK→samples NOT NULL, `path text NOT NULL`, `content_type text NOT NULL`, `size_bytes bigint NOT NULL CHECK (size_bytes > 0)`, `sha256 text NOT NULL`, `uploaded_by` FK→users NOT NULL, `uploaded_at`)
- [X] T012 In `0002`, create `portal_pushes` (`report_id` FK→reports NOT NULL UNIQUE, `status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','success','failed'))`, `attempts integer NOT NULL DEFAULT 0`, `last_error text NULL`, `next_attempt_at timestamptz NOT NULL DEFAULT now()`, `delivered_at timestamptz NULL`; index `(status, next_attempt_at)`)
- [X] T013 In `0002`, attach the Spec 1 `fn_audit` AFTER I/U/D trigger to every new table (`refresh_tokens`, `consent_items`, `qc_results`, `batches`, `batch_members`, `reports`, `portal_pushes`)
- [X] T014 In `0002`, enable + FORCE RLS and policies: operational tier `USING(has_identity())` + write `WITH CHECK(has_identity())` on the new operational tables; `refresh_tokens` restricted to `is_admin() OR user_id = current_setting('app.user_id')::uuid`; GRANT DML on the new tables to `helixa_app`
- [X] T015 In `0002`, write `downgrade()` dropping new triggers, policies, tables, and the `users` auth columns in reverse order (do not drop the `helixa_app` role)
- [X] T016 [P] Add SQLAlchemy models for the new tables + the `users` auth columns in `backend/app/db/models.py`
- [X] T017 [P] Create `backend/app/core/security.py` — argon2id hash/verify, JWT encode/verify (HS256, `JWT_SECRET`, `sub`+exp), opaque-token generation + SHA-256, and cookie set/clear helpers. Access cookie `HttpOnly; Secure; SameSite=Lax`; refresh cookie `HttpOnly; Secure; SameSite=Strict` scoped to `/auth` (CSRF defense-in-depth for the rotation endpoint, same-origin SPA otherwise)
- [X] T018 Create `backend/app/core/deps.py` — `get_db` dependency that opens one transaction per request and calls Spec 1 `set_session_context(conn, user_id, role_names)` before handler queries (commit/rollback); `current_user` (from the access cookie); `require_roles(*slugs)` (admin passes all, else 403)
- [X] T019 [P] Create Pydantic base schemas in `backend/app/schemas/` (shared error shape, pagination)
- [X] T020 Extend the test harness: `backend/tests/api/conftest.py` — FastAPI `TestClient` over a disposable Postgres with `0002` applied, fixtures that mint a signed-in client per role (`admin`, `genomics`, `trf`, `molecular`, `bioinformatics`)

**Checkpoint**: migration applies/rolls back on real Postgres; a request can authenticate, set identity, and be role-guarded.

---

## Phase 3: User Story 1 — Authenticated, role-bound access (Priority: P1) 🎯 MVP

**Goal**: sign-in, session validation, RBAC, audit attribution, user/role management, first-run admin.

**Independent Test**: create admin → login → `/auth/me` returns roles; protected route without cookie → 401; role-guarded route allowed/denied per role; refresh rotates and detects reuse; every write audited.

### Tests ⚠️ (write first)

- [X] T021 [P] [US1] `backend/tests/api/test_auth.py` — login success/failure (401, no user/password distinction), `/auth/me`, protected-without-cookie 401, refresh rotation + reuse-revokes-family, logout then 401, access-token expiry → 401 (SC-001)
- [X] T022 [P] [US1] `backend/tests/api/test_rbac.py` — each of the 5 roles allowed on its routes and denied (403) on others; admin passes all (SC-002)
- [X] T023 [P] [US1] `backend/tests/api/test_audit_attribution.py` — a create/update via the API produces a same-transaction `audit_log` row attributed to the acting user; no un-attributed writes (SC-003)

### Implementation

- [X] T024 [US1] `backend/app/services/auth_service.py` — verify credentials (argon2), issue access+refresh, rotate refresh (revoke old, new in family), reuse-detection (revoke family), logout, `last_login_at`
- [X] T025 [US1] `backend/app/api/auth.py` — `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout` (204), `GET /auth/me`; set/clear cookies per `contracts/auth-contract.md`
- [X] T026 [US1] `backend/app/api/users.py` — admin-only `GET/POST /users`, `PATCH /users/{id}`, `POST /users/{id}/roles`, `DELETE /users/{id}/roles/{slug}`; `backend/app/api/roles.py` — `GET /roles`
- [X] T027 [US1] `backend/app/cli.py` — `python -m app.cli create-admin --email --name` (prompts password, writes argon2 hash); the only account-creation path needing no existing admin (FR-006)
- [X] T028 [US1] Register the auth/users/roles routers in `backend/app/main.py`

**Checkpoint**: secure, role-bound API with a complete audit trail — MVP.

---

## Phase 4: User Story 2 — Gated sample workflow (Priority: P2)

**Goal**: register samples, consent checklist, advance through 8 ordered stages with server-side gates and optimistic concurrency.

**Independent Test**: register a sample; advance to molecular with consent incomplete → 409; complete consent → advance; skip-a-stage → 409; two concurrent advances → one 200, one 409, one event row.

### Tests ⚠️

- [ ] T029 [P] [US2] `backend/tests/api/test_workflow_gates.py` — consent-before-molecular gate, QC-before-report gate, no-skip rule, each returns 409 with a reason (SC-004)
- [ ] T030 [P] [US2] `backend/tests/api/test_workflow_concurrency.py` — two advances with the same `from_stage` → exactly one success and one 409; exactly one new `sample_stage_events` row (SC-009, FR-010a)

### Implementation

- [ ] T031 [US2] `backend/app/services/workflow_service.py` — `advance(sample_id, from_stage, to_stage, actor)`: assert `to = from + 1` (no skip → 409); gate check (molecular ⇒ all required `consent_items` complete; report ⇒ `qc_results(kind='qc', passed=true)`); guarded `UPDATE samples SET current_stage_id=:to WHERE id=:id AND current_stage_id=:from` (0 rows → 409); the stage event is written by the DB (Spec 1 duration trigger)
- [ ] T032 [US2] `backend/app/services/consent_service.py` — create/read/set `consent_items` completeness; expose required-items-complete for the gate
- [ ] T033 [US2] `backend/app/api/samples.py` — `POST /samples` (stage 1, unique `case_id`, pseudonymous), `GET /samples`, `GET /samples/{id}`, `GET /samples/{id}/events`, `POST /samples/{id}/consent`, `POST /samples/{id}/advance` (body carries `from_stage`); role guards per `research.md` D3
- [ ] T034 [US2] Register the samples router in `backend/app/main.py`

**Checkpoint**: gated workflow authoritative and concurrency-safe.

---

## Phase 5: User Story 3 — Operational support & turnaround (Priority: P3)

**Goal**: batches (advance+assign), data-generation/QC outcomes, vendor management, turnaround metrics.

**Independent Test**: batch-advance several samples (per-member results, a gated member fails without blocking others); record QC fail→blocks report, pass→unblocks; vendor TAT counted by its anchor; metrics reflect durations; SLA edit is future-only.

### Tests ⚠️

- [ ] T035 [P] [US3] `backend/tests/api/test_batches.py` — batch stage-advance applies per member with gates enforced individually; a failing member does not block others (FR-012)
- [ ] T036 [P] [US3] `backend/tests/api/test_qc_and_metrics.py` — QC pass/fail controls the report gate; `GET /metrics/tat` matches recorded durations; `PATCH` stage SLA changes future only, past durations unchanged (SC-005); vendor TAT by anchor (FR-014)

### Implementation

- [ ] T037 [US3] `backend/app/services/qc_service.py` — record `qc_results` rows (`kind` ∈ `data_generation`|`qc`, `passed`, `detail`); QC pass is the report gate (FR-013)
- [ ] T038 [US3] `backend/app/services/batch_service.py` — create batches, add members, batch-advance: advance each member in its **own savepoint** (`conn.begin_nested()`) so one member's 409/gate failure rolls back only that member and the others still commit (FR-012 — a failing member must not block the rest); collect a per-member result/conflict/gate-reason list by reusing `workflow_service.advance`; assignment is the only other batch operation
- [ ] T039 [US3] `backend/app/services/sla_service.py` — compute internal TAT vs per-stage SLAs and the 18-day target using the Spec 1 working calendar; per-vendor TAT by `tat_anchor` (`receipt`|`sequencing`) (FR-014/015)
- [ ] T040 [P] [US3] `backend/app/api/qc.py` (`POST /samples/{id}/qc`) and `backend/app/api/batches.py` (`POST /batches`, `POST /batches/{id}/members`, `POST /batches/{id}/advance`)
- [ ] T041 [P] [US3] `backend/app/api/vendors.py` (`GET/POST /vendors`, `PATCH /vendors/{id}`) and `backend/app/api/metrics.py` (`GET /metrics/tat`, `PATCH /stages/{id}/sla`)
- [ ] T042 [US3] Register the qc/batches/vendors/metrics routers in `backend/app/main.py`

**Checkpoint**: workflow operable at scale and measurable.

---

## Phase 6: User Story 4 — Reports & portal push (Priority: P3)

**Goal**: upload/store/serve reports under RBAC, retryable idempotent portal push behind a mockable client, case-close on success.

**Independent Test**: upload non-PDF→415, oversize→413, QC-missing→409, valid→stored + push queued; unauthorized file GET→403/404; mock fails once then retry→success, no duplicate, sample closed.

### Tests ⚠️

- [ ] T043 [P] [US4] `backend/tests/api/test_reports.py` — QC-gate 409, type 415, size 413, stored with sha256, metadata+file retrievable by admin/bioinformatics/genomics and refused (403) for trf/molecular (SC-007)
- [ ] T044 [P] [US4] `backend/tests/api/test_portal_push.py` — mock push fails then retry → success, `delivered_at` set, no duplicate (UNIQUE report_id), sample `status='closed'` only after success (SC-006/009)

### Implementation

- [ ] T045 [US4] `backend/app/services/portal_client.py` — single `PortalClient` interface with a default **mock** implementation (configurable failure for tests); real HTTP impl stubbed behind the same interface, `PORTAL_*` from config (FR-018)
- [ ] T046 [US4] `backend/app/services/report_service.py` — validate QC gate + type allowlist + max size before writing; stream to `REPORTS_ROOT/<case_id>/<uuid>-<filename>`, compute sha256, write `reports` row, create `portal_pushes` (queued) + enqueue a `jobs` row `kind='portal_push'`
- [ ] T047 [US4] `backend/app/api/reports.py` — `POST /samples/{id}/report` (multipart), `GET /reports/{id}`, `GET /reports/{id}/file` (streamed, RBAC+RLS), `GET /portal-pushes/{id}`, `POST /portal-pushes/{id}/retry`
- [ ] T048 [US4] `backend/app/worker.py` — jobs worker: lease `portal_push` jobs, set system actor + `app.job_id`, call `PortalClient.push`; success → `status='success'`, `delivered_at`, close the case; failure → `status='failed'`, backoff `next_attempt_at`, retry to a cap; idempotent on delivered pushes
- [ ] T049 [US4] Register the reports router in `backend/app/main.py`

**Checkpoint**: end-to-end path complete; results reach the portal reliably.

---

## Phase 7: Polish & Cross-Cutting

- [ ] T050 [P] Add `export-openapi` to `backend/app/cli.py` and commit `backend/openapi.json`; `backend/tests/api/test_openapi_contract.py` asserts the generated schema matches the committed file (no drift, SC-008)
- [ ] T051 [P] Update `backend/README.md` — running the API + worker, auth/session model, create-admin, and the `tests/api` suite
- [ ] T052 Run the full `quickstart.md` validation (steps 1–7) end-to-end against a real Postgres; confirm SC-001…SC-009
- [ ] T053 [P] Confirm the Alembic history is linear (`0001`→`0002`, single head) and `0003` is left free for Spec 4; run ruff over `backend/`

---

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2)** → **US1 (P3)** → **US2 (P4)** → **US3 (P5)** → **US4 (P6)** → **Polish (P7)**.
- US1 is a hard prerequisite for US2–US4 in practice: every endpoint requires an authenticated, role-guarded session and the per-request identity from `core/deps.py` (T018). US2–US4 are then independently testable slices.
- All `0002` DDL tasks (T005–T015) edit the **same migration file** → sequential, never `[P]`.
- Within a story: tests (write first) → service(s) → router(s) → registration.

### Parallel opportunities

- Setup: T002, T003 `[P]`. Foundational: T016, T017, T019 `[P]` alongside the sequential migration tasks; T020 after the migration exists.
- Each story's test files are `[P]`; routers in different files are `[P]` (T040/T041, T050/T051/T053).

---

## Implementation Strategy

- **MVP = Phases 1–3 (US1)**: a secure, role-bound, fully-audited API. Stop and validate (`test_auth`, `test_rbac`, `test_audit_attribution`) before building workflow.
- **Incremental**: US2 (gated workflow) → US3 (operational + metrics) → US4 (reports + portal). Each ends green and demoable; the whole feature = the `tests/api` + `tests/db` suites passing and `quickstart.md` validated.

---

## Notes

- Tests run against **real PostgreSQL** (Spec 1 harness); the portal client is **always mocked**.
- The backend connects as non-superuser `helixa_app`; `core/deps.py` sets the acting identity every request so audit + RLS apply.
- Out of scope: UI (Spec 3), SMTP notifications (Spec 3.1), sequencer ingestion (Spec 4, migration `0003+`).
