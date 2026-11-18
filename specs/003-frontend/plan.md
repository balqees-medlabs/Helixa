# Implementation Plan: Frontend (Spec 3)

**Branch**: `003-frontend` | **Date**: 2026-11-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-frontend/spec.md`

## Summary

The Next.js frontend: a presentation-only SPA in `/frontend` that consumes the Spec 2 backend over its published OpenAPI contract and holds no business logic. It authenticates via the backend's httpOnly cookie session (silent refresh on expiry), protects routes by role, renders the Medlabs-branded, RTL-safe UI, and delivers the full workflow — sample list/detail/register/advance (with the backend's gate reasons surfaced), consent, QC, batches, vendors, reports and portal status — plus four role dashboards (actionable work queues) and a shared TAT board. A typed API client is generated from `backend/openapi.json` so the two can't drift.

## Technical Context

**Language/Version**: TypeScript 5.x on Node 20.

**Primary Dependencies**: Next.js 14 (App Router), React 18, Tailwind CSS, shadcn/ui (Radix); TanStack Query (data fetching, caching, periodic poll); a typed client generated from the backend OpenAPI (`openapi-typescript` + a typed fetch wrapper); Zod for form validation; Vitest + Testing Library + MSW (component/integration) and Playwright (E2E).

**Storage**: None owned by the frontend. All data via the backend API; only per-viewer UI preferences (e.g., chosen dashboard, dir) in the browser.

**Testing**: Vitest + Testing Library with MSW mocking the API per the contract; Playwright E2E against a running backend for the key journeys; a generated-client drift check against the committed `openapi.json`.

**Target Platform**: Modern browsers; served same-origin behind Caddy on the internal network (TLS); no public exposure.

**Project Type**: Web application — frontend layer (third of Database → Backend → Frontend).

**Performance Goals**: Standard SPA responsiveness for ~10–20 users; first meaningful view fast on the LAN; board/status auto-refresh every ~30–60s (no live streaming).

**Constraints**: No business logic and no DB access (Art. I.3) — the frontend only renders and submits. Tokens never reach page scripts (httpOnly cookies). Calls restricted to contract-defined endpoints (no drift). Medlabs theme, sentence case, accessible contrast, RTL-safe from day one.

**Scale/Scope**: ~12 route areas, 4 dashboards + TAT board, ~28 backend endpoints consumed.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against Helixa Constitution v2.0.0:

| Article | Requirement | How this plan satisfies it | Status |
|---|---|---|---|
| I.3 | Frontend is presentation only; no business logic; MUST NOT touch Postgres | All logic/rules stay in the backend; the SPA renders API data and surfaces the backend's gate reasons verbatim. No DB client anywhere. | ✅ PASS |
| II.1 | Next.js 14 (App Router), TypeScript, Tailwind, shadcn/ui | Exactly this stack in `/frontend`. | ✅ PASS |
| III.1 | Backend issues/validates JWT; token never in frontend JS | Auth is the backend's httpOnly cookie session; the SPA never reads a token, only calls `/auth/*`. | ✅ PASS |
| III.2 | Role-based access (5 roles; multi-role; admin all) | Nav, routes, and actions gated by the roles from `/auth/me`; admin reaches all. Backend still enforces — the UI only reflects. | ✅ PASS |
| III.5 | Internal network behind reverse proxy, TLS | Served same-origin behind Caddy; no public bind. | ✅ PASS |
| VII.1–VII.4 | Medlabs design, sentence case, RTL-safe, four dashboards + shared TAT | Tailwind theme tokens + shadcn theming, logical CSS props + `dir`, four role dashboards and the shared TAT board. | ✅ PASS |
| VIII.4 | Frontend consumes the exported OpenAPI as the single source of API truth | Typed client generated from `backend/openapi.json`; a test fails on drift. | ✅ PASS |

No violations. Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-frontend/
├── plan.md              # This file
├── spec.md              # Clarified spec
├── research.md          # Phase 0 — routing/cookies, client gen, auth/refresh, theme/RTL, board, testing
├── data-model.md        # Phase 1 — client-side view models & UI state (backend owns the data)
├── quickstart.md        # Phase 1 — run & validation guide
├── contracts/           # Phase 1 — route map, API-consumption contract, auth-flow contract
│   ├── routes.md
│   ├── api-consumption.md
│   └── auth-flow.md
└── checklists/requirements.md
```

### Source Code (repository root) — new `/frontend` (constitution II.6)

```text
frontend/
├── app/                        # Next.js App Router
│   ├── (auth)/login/           # sign-in (public)
│   ├── (app)/                  # authenticated shell (layout guard + role nav + dir)
│   │   ├── dashboard/          # role dashboards + switcher (work queues)
│   │   ├── board/              # shared TAT Kanban
│   │   ├── samples/            # list, [id] detail+history, register, advance, consent
│   │   ├── batches/            # create, members, batch advance (per-member results)
│   │   ├── qc/                 # QC / data-generation entry
│   │   ├── vendors/            # list + admin manage
│   │   ├── reports/            # upload, retrieve, portal-push status + retry
│   │   └── metrics/            # turnaround metrics (admin)
│   ├── layout.tsx              # root: theme, dir, providers
│   └── middleware.ts           # cheap redirect to /login when the access cookie is absent
├── lib/
│   ├── api/                    # generated types + typed fetch wrapper (401 → refresh → retry)
│   ├── auth/                   # AuthProvider (user+roles from /auth/me), role helpers, guards
│   ├── query/                  # TanStack Query client + poll config
│   └── i18n/                   # dir handling, sentence-case helpers
├── components/                 # shadcn/ui + app components (StageBoard, GateError, RoleNav, …)
├── styles/                     # Tailwind theme tokens (Medlabs brand)
├── tests/                      # Vitest + Testing Library + MSW
├── e2e/                        # Playwright journeys
├── package.json  tsconfig.json  tailwind.config.ts  next.config.mjs
└── openapi-codegen config + a `check:contract` script (drift guard vs ../backend/openapi.json)
```

**Structure Decision**: New `/frontend` Next.js App Router project (constitution II.6). A route group `(app)` carries the authenticated shell (role nav, dir, providers) with a layout guard; `(auth)` holds the public sign-in. Data fetching is client-side via TanStack Query (enables the silent-refresh wrapper and the periodic poll); the typed client is generated from the backend contract.

## Complexity Tracking

No constitution violations — section intentionally empty.
