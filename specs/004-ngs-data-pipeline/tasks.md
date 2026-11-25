---
description: "Task list for NGS Data-Generation & Delivery Pipeline Tracking (Spec 4)"
---

# Tasks: NGS Data-Generation & Delivery Pipeline Tracking

**Input**: Design documents from `/specs/004-ngs-data-pipeline/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Included — Article VIII.2 mandates pytest coverage for auth, RBAC, and every stage-gate rule; the frontend follows the Spec 3 Vitest + MSW + Testing Library pattern.

**Governance**: Proceeds under constitution **v2.1.0** (ADR 0001 machine auth, ADR 0002 external-pipeline reporting — both Accepted). Delivery order within this cross-layer feature: DB migration `0003` → backend → frontend (Articles I, VIII.5).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5 (user-story phases only)

## Path Conventions

Web monorepo: `backend/` (FastAPI + Alembic), `frontend/` (Next.js). Migration under `backend/alembic/versions/`.

---

## Phase 1: Setup

- [X] T001 Create Alembic revision `backend/alembic/versions/0003_ngs_pipeline.py` with `down_revision = "0002"` (the revision id of `0002_backend_auth_workflow.py`) and empty `upgrade()`/`downgrade()` scaffolds
- [X] T002 [P] Add a "Spec 4 — NGS pipeline" section header and model-class stubs block to `backend/app/db/models.py` (names only, filled in T009)

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: schema, shared backend infra, and the machine-auth path every reporting story depends on. No user story can complete until this phase is done.

### Database — migration `0003` (all in `backend/alembic/versions/0003_ngs_pipeline.py`)

- [ ] T003 Create tables `sequencing_runs`, `pipeline_samples`, `merge_plan_runs`, `pipeline_results`, `coverage_results`, `vendor_deliveries`, `api_tokens` with columns, PKs, FKs and uniqueness per [data-model.md](./data-model.md) — including: `sequencing_runs.run_folder` unique not-null; `sequencing_runs.readiness` check `in ('received','ready','incomplete')`; `pipeline_samples.sample_id` **unique** FK→`samples`; `pipeline_samples.sample_type` check `in ('G','R')`; `pipeline_samples.coverage_target_x` not-null; `pipeline_results.kind` check `in ('ingest','conversion','augmentation')` and `idempotency_key` unique not-null; `coverage_results.verdict` check `in ('pass','below')` and `idempotency_key` unique not-null; `vendor_deliveries.status` check `in ('pending','uploading','delivered','failed')` and `verification_state` check `in ('unverified','readback_ok','receipt_confirmed','checksum_marker_ok')`; `merge_plan_runs` unique `(pipeline_sample_id, run_id)`
- [ ] T004 Extend `vendors` with `delivery_kind` (check `in ('s3','sftp')`), `endpoint_ref` jsonb, `naming_pattern` text, `md5_required` boolean, `verification_method` (check `in ('readback','receipt','checksum_marker')`) — all nullable to preserve existing rows
- [ ] T005 Add `audit_log` triggers (reusing `fn_audit()`) on all seven new tables so every change is logged in-transaction (Article IV.1)
- [ ] T006 Add append-only triggers rejecting UPDATE and DELETE for every role on `pipeline_results` and `coverage_results` (Article IV.3)
- [ ] T007 Enable RLS and add two-tier policies on the new tables: read for `molecular`/`bioinformatics`/`admin` per existing visibility rules; for the `pipeline-reporter` role — scoped **INSERT** on `pipeline_results`/`coverage_results`/`vendor_deliveries`, **UPDATE** on `vendor_deliveries` (delivery status transitions; it is mutable/audited, not append-only), and scoped **SELECT** on the runs/samples/results it reports on (so it can read a sample's coverage clearance before opening a delivery — FR-022); deny-by-default otherwise (Article III.3)
- [ ] T008 Seed the `pipeline-reporter` role, a non-human service user holding only that role, and backfill the three vendor delivery profiles (Arcensus `s3`/`readback`, SelfDecode `s3`/`receipt`, Revvity `sftp`/`checksum_marker` + `md5_required=true`); write matching `downgrade()`

### Backend — shared models, schemas, machine auth

- [ ] T009 [P] Add SQLAlchemy models for the seven new tables and the new `vendors` columns in `backend/app/db/models.py` (no business logic — mirrors only)
- [ ] T010 [P] Add Pydantic v2 request/response schemas (runs, pipeline samples, merge plan, pipeline results, coverage, deliveries, vendor profile, api-tokens) under `backend/app/schemas/`
- [ ] T011 Implement `pipeline-reporter` bearer-token auth in `backend/app/core/service_auth.py`: hash-compare against non-revoked `api_tokens`, resolve the service user + scoped role, set `app.user_id`/`app.role_names` on the transaction; reject missing/invalid/revoked with 401 and out-of-scope routes with 403 (see [contracts/reporter-auth.md](./contracts/reporter-auth.md))
- [ ] T012 Implement api-token admin endpoints in `backend/app/api/api_tokens.py` (`POST` mints + returns token once, `GET` metadata only, `DELETE` revokes) guarded to `admin`; wire the router into `backend/app/main.py`

### Foundational tests

- [ ] T013 [P] DB test: RLS visibility + deny-by-default on the new tables in `backend/tests/db/test_pipeline_rls.py`
- [ ] T014 [P] DB test: append-only UPDATE/DELETE rejection on `pipeline_results` and `coverage_results` in `backend/tests/db/test_pipeline_append_only.py`
- [ ] T015 [P] API test: token auth valid / invalid / revoked / out-of-scope-403 in `backend/tests/api/test_service_auth.py`

**Checkpoint**: schema live, machine-auth usable, shared models/schemas ready.

---

## Phase 3: User Story 1 — Run & sample intake (Priority: P1) 🎯 MVP

**Goal**: Molecular records a run and its samples (linked to existing workflow Samples) — Helixa replaces the tracking spreadsheet.

**Independent test**: create a run with several samples (mixed G/R, vendor, target); linking to a registered Sample succeeds with type-based target defaults; an unregistered sample is refused; the CSV export returns the list.

- [ ] T016 [US1] Implement `runs_service` (create run, record sample with link-to-existing-`samples` enforcement, duplicate `ngs_sample_id` check, target defaults 30 G / 15 R) in `backend/app/services/runs_service.py`
- [ ] T017 [US1] Implement runs API (`POST /runs`, `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/samples`, `GET /runs/export`) in `backend/app/api/runs.py` guarded to `molecular`/`admin`; wire router (see [contracts/endpoints.md](./contracts/endpoints.md))
- [ ] T018 [P] [US1] API test: intake RBAC, linkage refusal (422), duplicate id (409), target defaults in `backend/tests/api/test_runs_intake.py`
- [ ] T019 [US1] Regenerate OpenAPI (`python -m app.cli export-openapi`) and run frontend `gen:client` + `check:contract`
- [ ] T020 [P] [US1] Typed TanStack Query hooks in `frontend/lib/features/runs/queries.ts`
- [ ] T021 [US1] Run list + intake form in `frontend/app/(app)/runs/page.tsx` and `frontend/components/RunIntakeForm.tsx` (molecular; sentence case, RTL-safe, brand)
- [ ] T022 [US1] Run detail view in `frontend/app/(app)/runs/[id]/page.tsx`
- [ ] T023 [P] [US1] Frontend test (MSW): intake form success, linkage-refusal message, default target in `frontend/tests/runs.test.tsx`

**Checkpoint**: US1 independently shippable — the spreadsheet is retired.

---

## Phase 4: User Story 2 — Sequencing milestones drive the stages (Priority: P2)

**Goal**: ingest → Stage 4; FASTQ conversion + coverage PASS → Stage 7 (Article V.3), in order, idempotent.

**Independent test**: ingest at Stage 3 advances to Stage 4 (held otherwise); conversion + coverage ≥ target advances to Stage 7; coverage < target → BELOW, blocked; duplicate report → no double-advance.

- [ ] T024 [US2] Implement result recording + stage driving in `backend/app/services/pipeline_service.py`: record `ingest`/`conversion` results with idempotency key; drive Stage 4 (ingest) and Stage 7 (conversion **and** coverage pass) via the existing optimistic-concurrency advance; hold out-of-order as a no-op (see [contracts/stage-driving.md](./contracts/stage-driving.md))
- [ ] T025 [US2] Add coverage recording to `pipeline_service` (derive `verdict` = `pass` iff `depth_x >= target_x`; append-only; latest governs the gate)
- [ ] T026 [US2] Implement pipeline API (`POST /samples/{id}/pipeline-results`, `POST /samples/{id}/coverage`) in `backend/app/api/pipeline.py` authenticated as `pipeline-reporter`; wire router
- [ ] T027 [P] [US2] API test: in-order/hold, Stage 7 needs both signals, BELOW blocks, idempotent no-double-advance in `backend/tests/api/test_stage_driving.py`
- [ ] T028 [US2] Regenerate OpenAPI + frontend `check:contract`
- [ ] T029 [P] [US2] Typed hooks in `frontend/lib/features/pipeline/queries.ts`
- [ ] T030 [US2] Coverage panel + pipeline timeline in `frontend/components/CoveragePanel.tsx`, `frontend/components/PipelineTimeline.tsx`, wired into `frontend/app/(app)/samples/[id]/page.tsx`
- [ ] T031 [P] [US2] Frontend test (MSW): coverage/timeline render, BELOW flag, gate reason in `frontend/tests/pipeline.test.tsx`

**Checkpoint**: sequencing outcomes drive the workflow automatically.

---

## Phase 5: User Story 3 — Pipeline progress visible + merge plan validated (Priority: P3)

**Goal**: ingest/conversion/augmentation visible per sample; augmentation validated against a recorded merge plan.

**Independent test**: record a merge plan; a matching augmentation is accepted (`plan_match=true`); a mismatching one is recorded with `plan_match=false` and holds the sample not-ready for QC; a failed integrity check marks the sample not-ready.

- [ ] T032 [US3] Merge-plan recording (`POST /samples/{id}/merge-plan`) in `backend/app/api/runs.py` + `runs_service` (molecular/bioinformatics/admin)
- [ ] T033 [US3] Augmentation result handling + validation against the merge plan in `backend/app/services/pipeline_service.py`: always record (append-only) with `plan_match` set; a mismatch or failed integrity holds the sample **not-ready for QC** and surfaces the reason (recorded, not a 422 — a corrected run is a new result row)
- [ ] T034 [P] [US3] API test: merge-plan match/mismatch, integrity-fail not-ready in `backend/tests/api/test_augmentation.py`
- [ ] T035 [US3] Merge-plan editor + augmentation/progress display in `frontend/components/MergePlanEditor.tsx` and extend `PipelineTimeline` (shown on run/sample detail)
- [ ] T036 [P] [US3] Frontend test (MSW): merge-plan editor + progress states in `frontend/tests/pipeline-progress.test.tsx`

**Checkpoint**: full pipeline visibility with merge integrity.

---

## Phase 6: User Story 4 — Vendor delivery tracked to completion (Priority: P3)

**Goal**: PASS-gated deliveries with per-profile verification; no secrets stored.

**Independent test**: delivery refused for a BELOW sample; read-back vendor needs `readback_ok` before `delivered`; write-only needs `receipt_confirmed`; checksum vendor needs checksums + marker; no credentials anywhere.

- [ ] T037 [US4] Implement `delivery_service` (open delivery only when latest verdict = PASS; per-profile verification rules; status transitions) in `backend/app/services/delivery_service.py`
- [ ] T038 [US4] Deliveries API (`GET /samples/{id}/delivery-clearance`, `POST /samples/{id}/deliveries`, `PATCH /deliveries/{id}`, `GET /samples/{id}/deliveries`) in `backend/app/api/deliveries.py` (reporter reads clearance + posts/updates; molecular/bioinformatics/admin read); wire router
- [ ] T039 [US4] Extend `PATCH /vendors/{id}` to set the non-secret delivery profile in `backend/app/api/vendors.py` (admin; reject any credential field)
- [ ] T040 [P] [US4] API test: PASS gate (409), verification rules per destination, delivered-precondition (422), zero secrets stored in `backend/tests/api/test_deliveries.py`
- [ ] T041 [US4] Regenerate OpenAPI + frontend `check:contract`
- [ ] T042 [P] [US4] Typed hooks in `frontend/lib/features/deliveries/queries.ts`
- [ ] T043 [US4] Delivery status component + vendor-profile admin UI in `frontend/components/DeliveryStatus.tsx` and extend `frontend/app/(app)/vendors/page.tsx`
- [ ] T044 [P] [US4] Frontend test (MSW): delivery status, PASS gate, verification states in `frontend/tests/deliveries.test.tsx`

**Checkpoint**: outbound delivery loop closed and verifiable.

---

## Phase 7: User Story 5 — Returned reports reach the portal (Priority: P4)

**Goal**: a returned company report for a delivered sample reuses the existing report storage + portal push.

**Independent test**: attach a returned report to a delivered sample → stored under `/data/reports`, portal push queued, status visible; attaching for a not-delivered sample is refused.

- [ ] T045 [US5] Add a delivered-precondition to the existing report attach path and ensure it queues the existing portal push for returned reports in `backend/app/api/reports.py` / the report service (reuse Article VI.1–4 machinery; no new portal client)
- [ ] T046 [P] [US5] API test: returned report stored + portal push queued + not-delivered refusal in `backend/tests/api/test_returned_report.py`
- [ ] T047 [US5] Surface returned-report attach + push status on `frontend/app/(app)/samples/[id]/page.tsx`, reusing `frontend/components/PortalPushStatus.tsx`
- [ ] T048 [P] [US5] Frontend test (MSW): returned-report attach + push status in `frontend/tests/returned-report.test.tsx`

**Checkpoint**: end-to-end from run intake to portal-delivered result.

---

## Phase 8: Polish & Cross-Cutting

- [ ] T049 [P] Full backend suite green incl. Spec 1–3 regression: `pytest tests/db tests/api` (no existing gate weakened)
- [ ] T050 [P] Full frontend suite + build + contract: `npm test`, `npm run build`, `npm run check:contract`
- [ ] T051 Run the [quickstart.md](./quickstart.md) scenarios 1–5 against the live stack and confirm SC-001…SC-006
- [ ] T052 [P] Add the new "Runs" area to role-bound navigation/dashboards (molecular + bioinformatics) and update `frontend/README.md`
- [ ] T053 [P] Extend `frontend/e2e/global-setup.ts` + an e2e journey: mint a reporter token, drive intake → ingest → conversion+coverage → delivery → returned report
- [ ] T054 Remove the temporary Sync Impact Report comment from `.specify/memory/constitution.md`; ensure `docs/decisions/0001`,`0002` and all Spec 4 artifacts are committed with the code (Article VIII.3)

---

## Dependencies & Execution Order

- **Setup (P1 tasks T001–T002)** → **Foundational (T003–T015)** block everything.
- **Within Foundational**: T003→T004→T005→T006→T007→T008 are sequential (same migration file); T009/T010 depend on T003–T004; T011→T012; tests T013–T015 after their targets.
- **User stories** then proceed in priority order and are largely independent once Foundational is done:
  - **US1 (T016–T023)** — MVP; no dependency on US2–US5.
  - **US2 (T024–T031)** — needs Foundational; independent of US1 data but shares the sample-detail view.
  - **US3 (T032–T036)** — builds on US2's `pipeline_service` and sample detail.
  - **US4 (T037–T044)** — needs the PASS verdict from US2; otherwise independent.
  - **US5 (T045–T048)** — needs US4's delivered state.
- **Polish (T049–T054)** last.
- Each `export-openapi` task (T019/T028/T041) must precede its story's frontend `check:contract` and typed-hook tasks.

## Parallel Opportunities

- Foundational: **T009, T010** parallel after the schema tables exist; **T013, T014, T015** parallel after their targets.
- Per story, the `[P]` tasks (tests + typed query hooks) run alongside their sibling implementation once the endpoint exists — e.g. US1: **T020 ∥ T023**; US2: **T029 ∥ T031**; US4: **T042 ∥ T044**.
- Polish: **T049 ∥ T050 ∥ T052 ∥ T053**.

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + Phase 3 (US1).** Delivers Helixa as the source of truth for runs/samples and retires the spreadsheet — demonstrable on its own.
- **Increment 2 = US2** (the stage-driving payoff), then **US3** (visibility + merge integrity), **US4** (delivery), **US5** (report-back).
- Commit per phase (the established Spec 1–3 rhythm): review → run DB/pytest + frontend tooling → commit → push.

## Totals

- **54 tasks** — Setup 2, Foundational 13, US1 8, US2 8, US3 5, US4 8, US5 4, Polish 6.
- Test tasks: 11 (6 backend pytest, 4 frontend Vitest, 1 e2e) + the quickstart validation.
