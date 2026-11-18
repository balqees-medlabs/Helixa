# Phase 1 Data Model: Frontend

**Feature**: 003-frontend · **Date**: 2026-11-18

The frontend owns **no persistent data** — every entity is defined by the backend and typed from `backend/openapi.json` (the generated client is the source of shape truth). This document captures the **client-side view models and UI state** the app composes from API responses, plus the per-viewer preferences kept in the browser.

## View models (derived from API responses — generated types, not redefined here)

- **Session** ← `GET /auth/me`: `{ id, email, display_name, roles[] }`. Drives nav, guards, the dashboard switcher. Absent/401 ⇒ signed out.
- **SampleRow** ← `GET /samples`: `{ id, case_id, status, current_stage {position, slug, name} }` — list + board cards.
- **SampleDetail** ← `GET /samples/{id}` + `GET /samples/{id}/events`: the sample plus ordered stage history with `duration_hours`.
- **ConsentView** ← `GET /samples/{id}/consent`: `{ items[{item, required, complete}], required_complete }` — drives the checklist and the molecular-gate indicator.
- **GateError** ← a `409`/`403`/`422` body `{ detail }` from `advance`/`report`/role guards: surfaced verbatim as the reason (never reinterpreted).
- **BatchResult** ← `POST /batches/{id}/advance`: per-member `{ sample_id, status: advanced|conflict|gate_failed|forbidden|not_found, detail }`.
- **TatView** ← `GET /metrics/tat`: per-sample stage durations, per-stage and 18-day breaches, per-vendor elapsed/anchor — board flags + metrics screen.
- **PortalPushView** ← `GET /portal-pushes/{id}`: `{ status: queued|success|failed, attempts, last_error, delivered_at }` — status chip + retry affordance.
- **Vendor / Report / QcResult**: thin renderings of the corresponding backend rows.

## Client UI state

- **Auth state** (TanStack Query, key `['me']`): the Session; invalidated on login/logout; a `401` anywhere triggers the silent-refresh-then-retry path (research D3).
- **Query cache & polling**: list/detail/board/status queries; the board and portal-status queries use `refetchInterval` ~30–60s; mutations (register, advance, consent, qc, batch, upload, retry) invalidate the affected keys.
- **Dashboard selection**: for a multi-role user the default landing is always the **most privileged** dashboard they hold (the clarified rule); the switcher lets them change the active view, and `localStorage` only remembers that explicit in-session choice as a convenience — it never overrides the most-privileged default on a fresh sign-in, and falls back cleanly if unavailable.
- **Direction / locale**: `dir` (`ltr`|`rtl`) on `<html>`; English for v1 with an RTL-safe layout; a per-viewer preference.
- **Pending-action flags**: per in-flight mutation, to disable controls and prevent double-submit (edge case).

## Rules traced to requirements

| Rule | Source |
|---|---|
| Session/roles drive nav + guards; multi-role lands on most-privileged + switcher | FR-003/011, D4 |
| Silent refresh on 401, then retry; failed refresh → sign in preserving context | FR-004, D3 |
| Backend gate/permission reasons surfaced verbatim; UI never bypasses | FR-009/017, SC-003 |
| Board places samples by `current_stage`, flags past-target; advance is a gated action | FR-012, D6 |
| Report retrieval only offered to permitted roles | FR-018, SC-006 |
| Calls limited to generated (contract) client; drift fails a check | FR-021, SC-008, D2 |
| No persistent app data; only per-viewer prefs in the browser | Art. I.3 |
