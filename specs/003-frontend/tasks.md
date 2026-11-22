---

description: "Task list for Frontend (Spec 3)"
---

# Tasks: Frontend (Spec 3)

**Input**: Design documents from `/specs/003-frontend/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED. SC-008 needs a contract-drift guard, and SC-001…SC-007 are UI behaviours proven by Vitest + Testing Library + MSW (components, mocked per contract) and Playwright (E2E journeys against a live backend), per plan.md / constitution VIII.

**Organization**: Grouped by user story (US1–US5). New `/frontend` Next.js App Router project. `[P]` = different files, no incomplete dependency; shared files (the `apiFetch` wrapper, `AuthProvider`, root/`(app)` layouts) are sequential.

## Format: `[ID] [P?] [Story?] Description with file path`

- Paths are repo-relative under `frontend/`.

---

## Phase 1: Setup

- [X] T001 Scaffold the Next.js 14 (App Router) + TypeScript project in `frontend/` (`package.json`, `tsconfig.json`, `next.config.mjs`); Node 20
- [X] T002 [P] Add Tailwind CSS + shadcn/ui and the Medlabs theme tokens in `frontend/tailwind.config.ts` + `frontend/styles/globals.css` (red accent, neutral grey text, white surfaces; CSS variables for light theme)
- [X] T003 [P] Add deps: `@tanstack/react-query`, `zod`, `openapi-typescript` (dev), Vitest + `@testing-library/react` + `msw` (dev), `@playwright/test` (dev) in `frontend/package.json`
- [X] T004 [P] Configure ESLint/Prettier and a lint rule/convention forbidding hand-written API URLs (only the generated client), in `frontend/.eslintrc` + `frontend/package.json`
- [X] T005 Add the client-generation + drift scripts to `frontend/package.json`: `gen:client` (openapi-typescript from `../backend/openapi.json` → `frontend/lib/api/schema.d.ts`) and `check:contract` (regenerate to a temp file and diff vs committed)
- [X] T006 [P] Add the reverse-proxy config (local dev in `frontend/dev-proxy/` and the `infra/` Caddy mapping) serving the SPA at `/` and the backend at `/api` same-origin, and **rewrite the refresh cookie's `Set-Cookie` path from `/auth` to `/api/auth`** on `/api/auth/*` responses so it reaches the refresh endpoint — pure infra, no backend change (research D1)

**Checkpoint**: `npm run dev` serves an empty app; `npm run gen:client` produces types.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: no user story work begins until this is complete.

- [X] T007 Generate the typed API client: run `gen:client` and commit `frontend/lib/api/schema.d.ts`
- [X] T008 Create the typed fetch wrapper `frontend/lib/api/client.ts` — base `/api`, `credentials: 'include'`, JSON + multipart helpers, typed against the generated schema; **on 401 → one `POST /api/auth/refresh` then retry; concurrent 401s share a single in-flight refresh; failed refresh → clear session + redirect to `/login?next=`** (research D3, auth-flow.md)
- [X] T009 [P] Create `frontend/lib/query/client.ts` — TanStack Query client + a `POLL_MS` (~30–60s) constant for board/status queries
- [X] T010 Create `frontend/lib/auth/AuthProvider.tsx` — holds the session from `GET /api/auth/me` (TanStack key `['me']`), exposes `user`, `roles`, `can(...slugs)` (admin passes all), `login`, `logout`
- [X] T011 [P] Create `frontend/lib/i18n/dir.ts` + sentence-case helpers and wire `dir`/lang on `<html>` (LTR now, RTL-safe via logical CSS properties)
- [X] T012 Create `frontend/app/layout.tsx` (root: providers, theme, dir) and `frontend/app/(app)/layout.tsx` (authenticated shell: redirect when unauthenticated, role-based `RoleNav`, dashboard switcher slot)
- [X] T013 Create `frontend/middleware.ts` — redirect `(app)` routes to `/login` when the `access` cookie is absent (presence check only; never decodes the token)
- [X] T014 [P] Create shared components in `frontend/components/`: `RoleNav`, `GateError` (renders a backend `{detail}` verbatim), `StageBadge`, `EmptyState`, `SubmitButton` (disables while pending — no double-submit)
- [X] T015 [P] Set up the test harness: `frontend/tests/msw/handlers.ts` (mock the API per contract) + `frontend/vitest.config.ts`, and `frontend/playwright.config.ts` (E2E against a running backend)
- [X] T015a [P] Add the Playwright E2E fixture `frontend/e2e/fixtures.ts` + a `global-setup`: provision a backend admin (`python -m app.cli create-admin`), seed a QC-passed sample, and capture an authenticated `storageState` per role for the journeys (so E2E specs start signed in with data)

**Checkpoint**: the shell renders, redirects when signed out, and `apiFetch` refresh/retry works against MSW.

---

## Phase 3: User Story 1 — Sign in and role-bound access (Priority: P1) 🎯 MVP

**Goal**: sign in, role-aware nav/routing, silent session recovery, sign out, themed RTL-safe shell.

**Independent Test**: sign in → role-appropriate home; direct-link to a protected route while signed out → redirect to `/login` and return; single-role user sees only permitted nav/actions; expiry → silent continue, failed refresh → `/login`; sign out → protected routes unreachable.

### Tests ⚠️

- [X] T016 [P] [US1] `frontend/tests/auth.test.tsx` (MSW) — login success → `/auth/me` roles shown; wrong credentials → one non-revealing error; protected route while signed out → redirect; 401 → silent refresh → retry; failed refresh → redirect; logout → signed out (SC-001)
- [X] T017 [P] [US1] `frontend/tests/rbac-nav.test.tsx` (MSW) — for each role, only permitted nav/actions render; admin sees all; multi-role sees all its areas (SC-002)
- [X] T018 [P] [US1] `frontend/e2e/auth.spec.ts` (Playwright) — sign in → land on role home; sign out → `/login`

### Implementation

- [X] T019 [US1] `frontend/app/(auth)/login/page.tsx` — sign-in form (Zod), posts via `authService.login`, one non-revealing error, routes to `?next` or the landing dashboard
- [X] T020 [US1] `frontend/lib/auth/authService.ts` — `login`/`logout`/`me` through `apiFetch`; landing-dashboard resolution (most privileged role, research D4)
- [X] T021 [US1] `frontend/lib/auth/guards.ts` + wire into `(app)/layout.tsx` — redirect unauthenticated; `requireRoles` helper hides/forbids per role
- [X] T022 [US1] Finalize `RoleNav` + the dashboard switcher in `frontend/components/RoleNav.tsx` driven by `can()` and the role→area map (contracts/routes.md)

**Checkpoint**: secure, role-bound, themed shell — MVP.

---

## Phase 4: User Story 2 — Operate the sample workflow (Priority: P2)

**Goal**: list/detail/history, register, advance with backend gate reasons surfaced, consent checklist.

**Independent Test**: register → appears at stage 1; detail shows history; advance blocked by an unmet gate shows the specific reason; complete consent → advance; stage-skip / already-moved → the 409 reason, no duplicate.

### Tests ⚠️

- [X] T023 [P] [US2] `frontend/tests/workflow.test.tsx` (MSW) — advance with consent-incomplete/QC-missing/skip/stale → the backend `{detail}` rendered via `GateError` (not generic); successful advance updates the view (SC-003)
- [X] T024 [P] [US2] `frontend/e2e/workflow.spec.ts` (Playwright) — register → open → complete consent → advance to molecular against a live backend

### Implementation

- [X] T025 [P] [US2] `frontend/app/(app)/samples/page.tsx` + `frontend/lib/features/samples/queries.ts` — sample list (`GET /samples`) with case/stage/status and an empty state
- [X] T026 [US2] `frontend/app/(app)/samples/register/page.tsx` — register form (Zod), `POST /samples`; duplicate case id → the backend reason; genomics/admin only
- [X] T027 [US2] `frontend/app/(app)/samples/[id]/page.tsx` — detail + ordered stage history (`/samples/{id}`, `/events`) with durations
- [X] T028 [US2] `frontend/components/ConsentChecklist.tsx` + wire on the detail page — `GET/POST /samples/{id}/consent`, shows `required_complete` and the molecular-gate state
- [X] T029 [US2] `frontend/components/AdvanceAction.tsx` — advance control sending `from_stage`, offered on any active sample (the frontend does **not** encode the stage→role map; it defers to the backend); maps 403→forbidden and 409/422→`GateError` reason verbatim; invalidates sample/events/board/metrics on success

**Checkpoint**: the gated workflow is operable with reasons surfaced.

---

## Phase 5: User Story 3 — Role dashboards and the TAT board (Priority: P2)

**Goal**: four role work-queue dashboards + switcher, shared TAT Kanban, metrics.

**Independent Test**: each role's dashboard shows its actionable queue + counts/breach flags; multi-role lands on most-privileged + switcher; the board columns the 8 stages, flags past-target, and reflects a move on refresh.

### Tests ⚠️

- [X] T030 [P] [US3] `frontend/tests/dashboards.test.tsx` (MSW) — each role dashboard renders its work queue; multi-role default landing + switcher (SC-002 content)
- [X] T031 [P] [US3] `frontend/tests/tat-board.test.tsx` (MSW) — samples placed in their stage column; past-target flagged; advance moves the card on refetch (SC-005)

### Implementation

- [X] T032 [P] [US3] `frontend/app/(app)/dashboard/page.tsx` + `frontend/lib/features/dashboard/` — role work queues (samples awaiting the role) with counts + breach flags; genomics→intake/consent, molecular→molecular, bioinformatics→data-gen/QC/reporting, admin→all + users/vendors
- [X] T033 [US3] Dashboard switcher + default-landing (most privileged) wired to the switcher slot in `(app)/layout.tsx`
- [X] T034 [P] [US3] `frontend/app/(app)/board/page.tsx` + `frontend/components/StageBoard.tsx` — 8 stage columns from `/samples` + `/metrics/tat`; cards show case + time-in-stage; past-target flagged; **advance is a gated card action (not drag-and-drop)**; `refetchInterval = POLL_MS`
- [X] T035 [P] [US3] `frontend/app/(app)/metrics/page.tsx` — admin TAT metrics (per-stage/18-day breaches, per-vendor), and `PATCH /stages/{id}/sla`

**Checkpoint**: dashboards + board deliver the at-a-glance view.

---

## Phase 6: User Story 4 — QC, batches, vendors (Priority: P3)

**Goal**: QC/data-gen entry, batches with per-member results, vendor management.

**Independent Test**: QC fail blocks report / pass unblocks; batch advance shows per-member outcomes without one blocking others; admin edits vendors, others read-only.

### Tests ⚠️

- [X] T036 [P] [US4] `frontend/tests/batches.test.tsx` (MSW) — batch advance renders a per-member result list (advanced/conflict/gate_failed/forbidden) with reasons; a failing member doesn't block others (FR-015)

### Implementation

- [X] T037 [P] [US4] `frontend/app/(app)/qc/page.tsx` — record `POST /samples/{id}/qc` (`kind` data_generation|qc, passed, detail); bioinformatics/admin only
- [X] T038 [P] [US4] `frontend/app/(app)/batches/page.tsx` + `frontend/lib/features/batches/` — create batch, add members, batch advance; render the per-member `BatchResult` list
- [X] T039 [P] [US4] `frontend/app/(app)/vendors/page.tsx` — list (any role, read) + create/edit (admin) via `/vendors`

**Checkpoint**: operational entry screens complete.

---

## Phase 7: User Story 5 — Reports and portal delivery (Priority: P3)

**Goal**: report upload with refusal reasons, reader-role retrieval, portal status + retry.

**Independent Test**: wrong type/oversize/non-QC → the specific reason; valid PDF stored; permitted role retrieves, unpermitted isn't offered; failed push retry updates status.

### Tests ⚠️

- [ ] T040 [P] [US5] `frontend/tests/reports.test.tsx` (MSW) — upload 415/413/409 reasons surfaced; retrieval offered only to admin/bioinformatics/genomics; portal status chip + retry (SC-006)

### Implementation

- [ ] T041 [US5] `frontend/app/(app)/reports/page.tsx` + `frontend/lib/features/reports/` — report upload (multipart, bioinformatics) mapping 409/413/415 to specific messages; metadata + file retrieval gated to the reader roles (admin/bioinformatics/genomics)
- [ ] T042 [US5] `frontend/components/PortalPushStatus.tsx` — show queued/success/failed from `/portal-pushes/{id}`; admin retry; `refetchInterval = POLL_MS`

**Checkpoint**: end-to-end output path complete in the UI.

---

## Phase 8: Polish & Cross-Cutting

- [ ] T043 [P] Wire `check:contract` into CI + a test so a backend contract change that isn't regenerated fails the build (SC-008)
- [ ] T044 [P] Accessibility & RTL pass: verify WCAG-AA contrast on primary text/controls and that nav/board/forms mirror correctly under `dir="rtl"` (SC-007); add an RTL rendering test
- [ ] T045 [P] `frontend/README.md` — run dev + proxy, `gen:client`/`check:contract`, test + e2e commands, the cookie-path note (research D1)
- [ ] T046 Run the full `quickstart.md` validation (steps 1–8) against a live backend; confirm SC-001…SC-008

---

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2)** → **US1 (P3)** → **US2 (P4)** → **US3 (P5)** → **US4 (P6)** → **US5 (P7)** → **Polish (P8)**.
- US1 is a hard prerequisite: every `(app)` screen needs the auth shell, the `apiFetch` wrapper (T008), `AuthProvider` (T010), and the guards. US2–US5 are then independent slices, each a route area + its queries/components.
- Shared files are sequential: `apiFetch` (T008), `AuthProvider` (T010), root/`(app)` layouts (T012), `RoleNav`/switcher (T022/T033).

### Parallel opportunities

- Setup: T002, T003, T004, T006 `[P]`. Foundational: T009, T011, T014, T015 `[P]` alongside the sequential T008/T010/T012/T013.
- Each story's **test files** are `[P]`; route areas in different folders (samples list, qc, vendors, batches, reports, metrics, board) are `[P]` once the shell exists.

---

## Implementation Strategy

- **MVP = Phases 1–3 (US1)**: a secure, role-bound, themed, RTL-safe shell with working sign-in and silent session recovery. Validate `auth`/`rbac-nav`/`auth.spec` before building screens.
- **Incremental**: US2 (workflow) → US3 (dashboards + board) → US4 (ops) → US5 (reports). Each ends green and demoable; the whole feature = the Vitest/MSW + Playwright suites passing, `check:contract` clean, and `quickstart.md` validated.

---

## Notes

- The frontend holds **no business logic** and never touches the DB; every action goes through the backend, whose gate/permission reasons are surfaced verbatim.
- Only the **generated** client (from `backend/openapi.json`) is called — no hand-written endpoints; drift fails the build.
- Auth is the backend's httpOnly cookie session; tokens never reach page scripts; expiry is recovered silently.
- No backend change: the refresh cookie path reaching `/api/auth` is handled by a Caddy `Set-Cookie` path rewrite (research D1, T006) — Spec 2 stays untouched.
- Out of scope: backend features (Spec 2), notifications (Spec 3.1), sequencer UI (Spec 4).
