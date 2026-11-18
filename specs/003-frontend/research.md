# Phase 0 Research: Frontend

**Feature**: 003-frontend · **Date**: 2026-11-18

Stack is fixed by constitution v2.0.0 and the Clarifications session resolved the UX openers, so there were no `NEEDS CLARIFICATION` markers. These decisions record *how* to build the SPA against the Spec 2 backend.

---

## D1 — Same-origin deployment & cookie paths (the key integration seam)

**Decision**: Caddy serves the SPA at `/` and reverse-proxies the backend under **`/api`**, stripping the prefix so the backend still sees its own paths (`/auth/login`, `/samples`, …). The browser calls the API at `/api/...`, same-origin, so the httpOnly cookies ride along.

**Cookie-path alignment**: the Spec 2 **access** cookie is `path=/` (reaches `/api/*` — fine). The Spec 2 **refresh** cookie is `SameSite=Strict; path=/auth`, which would *not* be sent to `/api/auth/refresh` (path mismatch). **Resolution (chosen): Caddy rewrites the `Set-Cookie` path from `/auth` to `/api/auth` on the backend's `/api/auth/*` responses** — a pure-infra fix that keeps Spec 2 untouched, so the frontend scope stays "no backend changes." (A future alternative, if the deployment prefix is ever dropped, is an env-driven backend cookie path — not needed now.)

**Rationale**: Same-origin + httpOnly is the constitution's model (III.1). A single `/api` prefix keeps UI and API route namespaces disjoint (no `/samples` collision). `SameSite=Strict` on refresh remains the CSRF guard; the path only needs to reach the proxied endpoint.

**Alternatives**: Next.js route handlers as a server-side proxy forwarding `Set-Cookie` (double proxy, more moving parts); proxying each backend path at the root (fragile namespace coupling). Rejected.

---

## D2 — Typed client generated from the OpenAPI contract

**Decision**: Generate TypeScript types from `backend/openapi.json` with `openapi-typescript`, wrapped by a small typed `apiFetch` (base `/api`, `credentials: 'include'`). A `check:contract` script regenerates and diffs against the committed types; CI/a test fails on drift (SC-008, FR-021).

**Rationale**: Constitution VIII.4 — the backend's OpenAPI is the single source of API truth. Generated types mean an endpoint the contract doesn't define simply doesn't exist in the client.

**Alternatives**: Hand-written client (drifts); heavier generators (orval/openapi-generator) — overkill for 28 paths and a cookie-auth fetch.

---

## D3 — Auth, session state, and silent refresh

**Decision**: Auth state comes from `GET /auth/me` (200 → `{user, roles}`; 401 → signed out), held in an `AuthProvider` and cached by TanStack Query. The `apiFetch` wrapper, on a `401`, calls `POST /api/auth/refresh` **once** and retries the original request; if refresh fails, it clears auth state and routes to `/login` (preserving the attempted path). A thin Next.js **middleware** does a cheap redirect to `/login` when the access cookie is absent (presence only — it never decodes the token). `login`/`logout` call `/auth/login` / `/auth/logout`.

**Rationale**: Matches the clarified "silently renew and continue". The browser can't read httpOnly cookies, so `/auth/me` is the authority on session state; the single-retry-after-refresh is the standard rotating-refresh client pattern. Middleware presence-check is a fast first gate; the backend remains the real authority.

**Alternatives**: Decode the JWT client-side (impossible/insecure — httpOnly, no secret); refresh on a timer (racy vs actual expiry). Rejected.

---

## D4 — Role-based routing, nav, and the dashboard switcher

**Decision**: `roles` from `/auth/me` drive a `can(role)` helper used by route guards and the top-level nav (which *areas* a role sees). The `(app)` layout redirects unauthenticated users and hides disallowed nav. A multi-role user lands on the **most privileged** dashboard they hold (admin › bioinformatics › the operational roles) with a **switcher** to the others their roles grant (clarified).

The frontend does **not** duplicate the backend's per-stage advance authority map (Spec 2 D3). The advance action is simply offered on a sample; if the acting role may not make that transition, the backend returns `403`/`409` and the UI surfaces the reason (`GateError`). This keeps that business rule single-sourced in the backend (Art. I.3) and immune to drift when the backend's map changes.

**Rationale**: Constitution III.2 and I.3; the UI reflects coarse area access for a clean experience but never re-encodes the backend's fine-grained transition rules — it shows the action and defers to the backend's response.

---

## D5 — Medlabs theme & RTL-safe layout

**Decision**: Tailwind theme tokens for the Medlabs palette (red accent from the logo, neutral grey text, white surfaces) applied through shadcn/ui's token theming; sentence-case copy; WCAG-AA contrast on primary text/controls. RTL-safe from day one via **logical CSS properties** (`ms/me`, `ps/pe`, `start/end`) and a `dir` attribute on `<html>` driven by locale; English ships first, the layout mirrors cleanly when `dir="rtl"`. Exact brand hex comes from the MedLabs logo (noted as a risk until supplied).

**Rationale**: Constitution VII.1–VII.3.

**Alternatives**: Physical left/right utilities (break RTL) — rejected; a full i18n framework now (Arabic content is later) — deferred, but the dir-safe layout is built in now.

---

## D6 — The shared TAT board

**Decision**: Columns are the 8 stages; cards are samples at their `current_stage`, sourced from `GET /samples` joined with `GET /metrics/tat` for time-in-stage and breach flags. Advancing is **a gated action on the card** (calls `POST /samples/{id}/advance`), **not** free drag-and-drop — a drag could imply a move the backend's gates forbid. A refused advance shows the backend reason inline. Auto-refreshes every ~30–60s and on action.

**Rationale**: Honours the server-side gates (V.2) — the board can't suggest an ungated move. Clarified freshness model.

---

## D7 — Testing strategy

**Decision**: Vitest + Testing Library for components/pages with **MSW** mocking the API per the contract (covers role gating, surfaced gate reasons, empty/error states, RTL rendering). Playwright E2E for the key journeys against a running backend: sign in → role nav; register → advance with a gate reason; dashboard work queue; TAT board; report upload. A `check:contract` drift test (D2) guards SC-008.

**Rationale**: Constitution VIII; SC-001…SC-008 are UI behaviors best proven at the component (mocked) and journey (E2E) levels.

---

## D8 — Scope boundary

**Decision**: Spec 3 adds only the `/frontend` app. **No backend change** — the cookie-path alignment (D1) is handled in the reverse proxy (Caddy), not in Spec 2. No notifications (Spec 3.1), no sequencer UI (Spec 4). Data generation appears as a QC-style outcome entry until Spec 4 drives it.

**Rationale**: Constitution I.4 dependency order; keeps the layer clean.
