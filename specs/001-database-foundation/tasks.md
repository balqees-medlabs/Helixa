---

description: "Task list for Database Foundation (Spec 1)"
---

# Tasks: Database Foundation (Spec 1)

**Input**: Design documents from `/specs/001-database-foundation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED. The spec's success criteria (SC-002 append-only, SC-004 RLS) and User Story 3's independent test can only be proven by tests against real PostgreSQL (research D9), and plan.md mandates the `backend/tests/db/` suite. Test tasks are therefore first-class here.

**Organization**: Grouped by user story (P1–P4). Because this layer ships as a single Alembic migration (`0001_database_foundation.py`) plus one models file, most DDL tasks edit the **same files** and are therefore sequential (no `[P]`). Tasks in different files (tests, helpers, docs) are marked `[P]`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US4 (maps to spec.md user stories)
- Paths follow plan.md: schema lives in `backend/alembic` + `backend/app/db`; running Postgres + backups in `infra/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Backend project + migration tooling skeleton.

- [X] T001 Create backend project structure per plan.md (`backend/app/db/`, `backend/alembic/versions/`, `backend/tests/db/`)
- [X] T002 Initialize backend Python project in `backend/pyproject.toml` with SQLAlchemy 2.x, Alembic, `psycopg[binary]`, pytest, and a disposable-Postgres test dep (testcontainers or pytest-postgresql)
- [X] T003 [P] Configure Ruff lint/format config in `backend/pyproject.toml`
- [X] T004 Initialize Alembic: `backend/alembic.ini` and `backend/alembic/env.py` reading `DATABASE_URL` from the environment (no hardcoded creds)
- [X] T005 [P] Add database env keys to `infra/.env.example`: `DATABASE_URL` (admin, for migrations), `APP_DB_USER`/`APP_DB_PASSWORD` for the `helixa_app` role

**Checkpoint**: `alembic upgrade head` runs (no migrations yet) against the M0 Postgres.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration scaffold, extensions, app role, model base, and the test harness every story needs.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T006 [P] Create SQLAlchemy declarative metadata in `backend/app/db/base.py`
- [X] T007 Create migration `backend/alembic/versions/0001_database_foundation.py` with empty `upgrade()`/`downgrade()`, enabling extensions `pgcrypto` (for `gen_random_uuid()`) and `citext`
- [X] T008 Provision the non-superuser `helixa_app` login role (no `BYPASSRLS`) in `infra/bootstrap-app-role.sh`, reading `APP_DB_USER`/`APP_DB_PASSWORD` from `.env` — **not** in the migration (constitution III.4: no credentials in version-controlled migrations). The migration only `GRANT`s privileges to the already-existing role (see T039); it must not contain `CREATE ROLE … PASSWORD`. Migrations run as owner/admin; the app connects as `helixa_app` (research D3)
- [X] T009 [P] Implement the session-context helper in `backend/app/db/session_context.py` emitting `SET LOCAL app.user_id` / `app.role_names` / `app.job_id` exactly per `contracts/session-context.md`
- [X] T010 Create pytest harness `backend/tests/db/conftest.py`: spin up a disposable PostgreSQL 16, run `alembic upgrade head`, provide a `helixa_app` connection and a fixture to set the session context

**Checkpoint**: Empty schema builds and tears down in tests; identity can be set on a transaction.

---

## Phase 3: User Story 1 - Tamper-proof clinical record (Priority: P1) 🎯 MVP

**Goal**: Every change is recorded in the same transaction and history cannot be altered or erased.

**Independent Test**: Insert under an identity → exactly one audit row; UPDATE/DELETE on `audit_log` rejected for all roles; a write with no `app.user_id` is refused.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL)

- [X] T011 [P] [US1] `backend/tests/db/test_audit_trigger.py`: an INSERT/UPDATE/DELETE on a tracked table writes exactly one same-transaction `audit_log` row with `actor_id = app.user_id`, correct `before`/`after`, and `job_id` when `app.job_id` set (FR-001, FR-002, FR-004, SC-001); a write with no `app.user_id` raises
- [X] T012 [P] [US1] `backend/tests/db/test_append_only.py`: UPDATE and DELETE on `audit_log` raise for each role {admin, genomics, trf, molecular, bioinformatics}; row count unchanged (FR-003, SC-002)

### Implementation for User Story 1

- [X] T013 [US1] In migration `0001`, create `users` table: `id uuid PK`, `email citext UNIQUE NULL`, `display_name text NOT NULL`, `is_system boolean NOT NULL DEFAULT false`, `is_active boolean NOT NULL DEFAULT true`, partial unique `UNIQUE (is_system) WHERE is_system` (at most one system actor). No credential columns (deferred to M2)
- [X] T014 [US1] In migration `0001`, create `jobs` table per data-model (`kind`, `status CHECK in (queued,running,succeeded,failed)`, `payload jsonb DEFAULT '{}'`, `attempts`, `last_error`, `run_after`, `locked_at`, `updated_at`) — needed for `audit_log.job_id` FK (Article VIII.6)
- [X] T015 [US1] In migration `0001`, create append-only `audit_log` table per data-model: `actor_id uuid FK→users NOT NULL`, `job_id uuid FK→jobs NULL`, `action text CHECK in (INSERT,UPDATE,DELETE)`, `entity_table text NOT NULL`, `entity_id uuid NOT NULL`, `before jsonb NULL`, `after jsonb NULL`, `at timestamptz NOT NULL DEFAULT now()`; indexes on `(entity_table, entity_id)` and `(at)`
- [X] T016 [US1] In migration `0001`, implement `fn_audit()` as a `SECURITY DEFINER` trigger function **owned by the migration/superuser (BYPASSRLS) role** so its `INSERT` into `audit_log` is not blocked by that table's `FORCE ROW LEVEL SECURITY` (no app-facing INSERT policy exists). It reads `current_setting('app.user_id')::uuid` (RAISE if unset on a write) and `nullif(current_setting('app.job_id',true),'')::uuid`, and writes `before=to_jsonb(OLD)`/`after=to_jsonb(NEW)` (per `contracts/audit-contract.md`). Set `search_path` explicitly in the function to avoid definer hijacking
- [X] T017 [US1] In migration `0001`, implement `fn_reject_mutation()` and attach `BEFORE UPDATE OR DELETE` on `audit_log` (RAISE EXCEPTION)
- [X] T018 [US1] In migration `0001`, attach `fn_audit()` `AFTER INSERT/UPDATE/DELETE` triggers to `users` and `jobs`
- [X] T019 [US1] In migration `0001`, seed the `system` actor (one `users` row, `is_system=true`, no credentials, `email NULL`)
- [X] T020 [US1] Add SQLAlchemy models `User`, `Job`, `AuditLog` to `backend/app/db/models.py` (field-for-field with the schema; no business logic)

**Checkpoint**: Audit completeness + append-only provable in isolation — MVP of the integrity guarantee.

---

## Phase 4: User Story 2 - Workflow model and sample progression (Priority: P2)

**Goal**: The 8 ordered stages with editable SLAs, per-sample stage history with durations, and the turnaround calendar exist.

**Independent Test**: 8 ordered stages with SLAs present; a sample advancing records events with durations; editing an SLA leaves past durations unchanged; `sample_stage_events` is append-only; duplicate `case_id` rejected.

### Tests for User Story 2 ⚠️

- [X] T021 [P] [US2] `backend/tests/db/test_workflow.py`: advancing a sample inserts a `sample_stage_events` row with `duration_hours`; UPDATE/DELETE on `sample_stage_events` raise (FR-003); changing `stage_sla.sla_days` does not alter past `duration_hours` (FR-006); inserting a duplicate `samples.case_id` is rejected (FR-009, SC-007)
- [X] T022 [P] [US2] `backend/tests/db/test_stages_seed.py`: exactly 8 stages with `position` 1..8 unique and the default SLA split `1,2,4,4,2,1,2,2` (Σ=18); one default `working_calendar` with `weekend_days = {5}` (Friday) (FR-005, FR-006, FR-008)

### Implementation for User Story 2

- [X] T023 [US2] In migration `0001`, create `stages` table: `position smallint UNIQUE NOT NULL CHECK (position BETWEEN 1 AND 8)`, `slug text UNIQUE NOT NULL`, `name text NOT NULL`
- [X] T024 [US2] In migration `0001`, create `stage_sla` table: `stage_id uuid FK→stages UNIQUE NOT NULL`, `sla_days integer NOT NULL CHECK (sla_days >= 0)`, `updated_at timestamptz NOT NULL DEFAULT now()`
- [X] T025 [US2] In migration `0001`, create `vendors` table: `name text UNIQUE NOT NULL`, `tat_days integer NOT NULL CHECK (tat_days >= 0)`, `tat_anchor text NOT NULL CHECK (tat_anchor IN ('receipt','sequencing'))`, `is_active boolean NOT NULL DEFAULT true`
- [X] T026 [US2] In migration `0001`, create `samples` table: `case_id text UNIQUE NOT NULL` (pseudonymous; no name/MRN columns), `external_ref text NULL` (single optional minimal field), `current_stage_id uuid FK→stages NOT NULL`, `vendor_id uuid FK→vendors NULL`, `received_at timestamptz NOT NULL DEFAULT now()`, `status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','on_hold','closed'))` (FR-009, D6)
- [X] T027 [US2] In migration `0001`, create append-only `sample_stage_events`: `sample_id uuid FK→samples NOT NULL`, `stage_id uuid FK→stages NOT NULL`, `entered_at timestamptz NOT NULL DEFAULT now()`, `duration_hours numeric(10,2) NULL`, `actor_id uuid FK→users NOT NULL`, `note text NULL`
- [X] T028 [US2] In migration `0001`, create `working_calendar` (singleton; `weekend_days smallint[] NOT NULL`, default `{5}` = Friday per the Medlabs work week) and `holidays` (`day date UNIQUE NOT NULL`, `label text NULL`) tables (FR-008)
- [X] T029 [US2] In migration `0001`, attach `fn_reject_mutation()` `BEFORE UPDATE OR DELETE` on `sample_stage_events`
- [X] T030 [US2] In migration `0001`, attach `fn_audit()` triggers to `stages`, `stage_sla`, `vendors`, `samples`, `sample_stage_events` (insert), `working_calendar`, `holidays`
- [X] T031 [US2] In migration `0001`, seed the 8 stages (ordered, with slugs) and their default SLAs `received 1, consent_documentation 2, molecular_processing 4, data_generation 4, trf_preparation 2, trf_confirmation 1, data_conversion_qc 2, report_upload_archive 2`, and one default `working_calendar` row `weekend_days = {5}` with no holidays. Each stage's `name` keeps the full constitution label (e.g., stage 8 name = "report upload/archive/portal push", slug `report_upload_archive`)
- [X] T032 [US2] Add SQLAlchemy models `Stage`, `StageSla`, `Vendor`, `Sample`, `SampleStageEvent`, `WorkingCalendar`, `Holiday` to `backend/app/db/models.py`

**Checkpoint**: Workflow data model and progression history provable independently.

---

## Phase 5: User Story 3 - Role-based access, second line of defense (Priority: P3)

**Goal**: Operational roles read all samples; `users`/`roles`/`user_roles`/`audit_log` are admin-only; no identity → no rows.

**Independent Test**: A `genomics` session reads samples but zero rows from `users`/`audit_log`; an `admin` session reads all; a session with no `app.user_id` reads nothing.

### Tests for User Story 3 ⚠️

- [ ] T033 [P] [US3] `backend/tests/db/test_rls_visibility.py`: with `app.role_names='genomics'`, `SELECT count(*) FROM samples > 0` and `FROM users / audit_log = 0`; with `app.role_names='admin'`, restricted tables return rows; with no identity set, all selects return 0 (FR-014, FR-015, SC-004)

### Implementation for User Story 3

- [ ] T034 [US3] In migration `0001`, create `roles` table (`slug text UNIQUE NOT NULL CHECK slug IN the 5`) and `user_roles` (`user_id FK→users ON DELETE CASCADE`, `role_id FK→roles`, `UNIQUE(user_id, role_id)`); attach `fn_audit()` triggers to both
- [ ] T035 [US3] In migration `0001`, seed the 5 roles: `admin`, `genomics`, `trf`, `molecular`, `bioinformatics`
- [ ] T036 [US3] In migration `0001`, create SQL helpers `app_roles()`, `is_admin()`, `has_identity()` reading `current_setting('app.role_names'/'app.user_id', true)` (research D5)
- [ ] T037 [US3] In migration `0001`, `ENABLE` + `FORCE ROW LEVEL SECURITY` and add SELECT/write policies `USING (is_admin())` on restricted tables `users`, `roles`, `user_roles`, `audit_log` (audit_log: no app INSERT policy — written by the `SECURITY DEFINER` trigger only; mutation already trigger-blocked)
- [ ] T038 [US3] In migration `0001`, `ENABLE` + `FORCE ROW LEVEL SECURITY` and add SELECT `USING (has_identity())` + write `WITH CHECK (has_identity())` policies on operational tables `samples`, `sample_stage_events`, `stages`, `stage_sla`, `vendors`, `working_calendar`, `holidays`, `jobs`
- [ ] T039 [US3] In migration `0001`, `GRANT` the appropriate table/sequence privileges to the pre-existing `helixa_app` role (DML only, no DDL; the role itself is created in `infra/bootstrap-app-role.sh`, T008). Do **not** grant INSERT on `audit_log` to `helixa_app`; audit rows are written only by the `SECURITY DEFINER` `fn_audit()` owned by the superuser/BYPASSRLS role (T016), which is what lets them land under `FORCE RLS`. Add a test assertion that a *direct* `helixa_app` INSERT into `audit_log` is rejected
- [ ] T040 [US3] Add SQLAlchemy models `Role`, `UserRole` to `backend/app/db/models.py`

**Checkpoint**: Two-tier RLS provable; deny-by-default confirmed.

---

## Phase 6: User Story 4 - Reference data and a reproducible, recoverable schema (Priority: P4)

**Goal**: Full seed present, human admin absent, schema reproducible from migrations, backup restorable.

**Independent Test**: From empty, `alembic upgrade head` yields full schema + seed; only the `system` user exists; `downgrade base` then `upgrade head` reproduces the schema; a backup restores into a fresh database with matching contents.

### Tests for User Story 4 ⚠️

- [ ] T041 [P] [US4] `backend/tests/db/test_seed.py`: after seed there are exactly 5 roles, 8 ordered stages+SLAs, the 4 named vendors with anchors (Arcensus 4/receipt, Reviity 28/receipt, Sefdecode 5/receipt, Centogene 30/sequencing), one `system` actor, one calendar, and **zero** non-system users (FR-011, FR-012, SC-003)
- [ ] T042 [P] [US4] `backend/tests/db/test_migration_rebuild.py`: `alembic downgrade base` then `upgrade head` leaves an identical schema with no errors (FR-016, SC-005)

### Implementation for User Story 4

- [ ] T043 [US4] In migration `0001`, seed the 4 vendors with TAT + anchor: Arcensus `4`/`receipt`, Reviity `28`/`receipt`, Sefdecode `5`/`receipt`, Centogene `30`/`sequencing` (FR-011, D7/D8)
- [ ] T044 [US4] In migration `0001`, implement `downgrade()` to drop all policies, triggers, functions, tables, and extensions in reverse dependency order (clean `downgrade base`). Do **not** drop the `helixa_app` role — it is owned by `infra/bootstrap-app-role.sh` (F3), not this migration; only `REVOKE`/drop the grants the migration created
- [ ] T045 [P] [US4] Add `infra/restore-check.sh`: run `infra/backup.sh`, `pg_restore` the dump into a scratch database, and diff key table row counts against the source (SC-006); reference it from `quickstart.md` §7. **Prerequisite**: `infra/backup.sh` is an M0 deliverable — if it is absent, create a minimal `pg_dump -Fc` script here first, otherwise SC-006/FR-017 cannot be validated

**Checkpoint**: Deployable and recoverable; SC-003/005/006 green.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T046 [P] Review and add any missing indexes (FKs, `samples.case_id`, `jobs(status, run_after)`) in migration `0001`
- [ ] T047 [P] Write `backend/README.md`: how to run migrations, set the session context, and run the `tests/db/` suite
- [ ] T048 Run the full `quickstart.md` validation (steps 1–8) end-to-end against the M0 Postgres and confirm every success criterion
- [ ] T049 [P] Commit the migration, models, helpers, and tests; confirm the Alembic history is linear (single `0001` head) and `0002` is left free for Spec 4

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)** → **Foundational (P2)** → **US1 (P3)** → **US2 (P4)** → **US3 (P5)** → **US4 (P6)** → **Polish (P7)**.
- The strict story order here is stronger than a typical feature because all DDL lands in the single migration `0001`: US2 tables reference US1's `users`/audit functions; US3 policies cover tables created in US1/US2; US4 seeds vendors (US2 table) and roles (US3 table) and writes `downgrade()` for everything.

### Within each story

- Tests first (write, see them fail) → migration DDL → seed → SQLAlchemy models.
- All DDL tasks edit `0001_database_foundation.py` → **sequential**, never `[P]` with each other.

### Parallel opportunities

- Setup: T003, T005 `[P]`.
- Foundational: T006, T009 `[P]` (separate files) alongside T007/T008/T010.
- Per story, the **test file** tasks are `[P]` (distinct files) and can be authored before the DDL they target.
- Polish: T046, T047, T049 `[P]`.

---

## Parallel Example: User Story 1

```bash
# Author both US1 test files in parallel (they fail until the migration lands):
Task: "T011 test_audit_trigger.py — same-tx audit row + attribution"
Task: "T012 test_append_only.py — audit_log UPDATE/DELETE rejected for all roles"
# Then the migration DDL (T013→T019) runs sequentially on 0001, followed by models (T020).
```

---

## Implementation Strategy

### MVP first (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **STOP & validate**: audit completeness + append-only against real Postgres. This alone is the minimum viable integrity foundation.

### Incremental delivery

- US1 (integrity) → US2 (workflow model) → US3 (RLS) → US4 (seed + reproducibility/recovery). Each phase ends green and demoable; the whole feature = the full `tests/db/` suite passing + `quickstart.md` validated.

---

## Notes

- `[P]` = different files, no incomplete dependency. DDL on the shared migration is never `[P]`.
- Tests run against **real PostgreSQL 16** (research D9) — SQLite cannot validate triggers/RLS/`current_setting`.
- The backend connects as non-superuser `helixa_app`; this is what makes append-only and RLS real, not cooperative.
- Commit after each task or logical group; keep the Alembic head single so Spec 4 can add `0002`.
- Out of scope (do not add here): auth/credential columns on `users` (M2), `sequencing_runs`/`run_samples` (Spec 4 / migration `0002`).
