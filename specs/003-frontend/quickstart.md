# Quickstart & Validation: Frontend

**Feature**: 003-frontend · Proves the SPA works end-to-end against the Spec 2 backend. Run/verify guide, not implementation.

## Prerequisites
- Spec 2 backend running and reachable (API + a `create-admin` account); its `openapi.json` present.
- Caddy (or local dev proxy) serving the SPA at `/` and the API at `/api` same-origin; the refresh cookie path reaches `/api/auth` (research D1).
- `frontend/` deps installed (`npm install`); Node 20.

## 1. Generate the client & guard drift  → SC-008
```bash
cd frontend
npm run gen:client       # types from ../backend/openapi.json
npm run check:contract   # fails if the committed client drifts from the contract
```
Expect: client in sync; a deliberate backend contract change makes `check:contract` fail.

## 2. Run the app
```bash
npm run dev              # or build + start behind Caddy
```
Open the app; you should be redirected to `/login` when signed out.

## 3. Sign in & role access  → SC-001/002
- Sign in as the admin → land on the admin dashboard; name + roles shown.
- Open a protected route while signed out (incognito) → redirected to `/login`, returned after sign-in.
- Sign in as a single-role user (e.g., genomics) → only genomics nav/actions offered; admin-only areas absent; a direct visit to an admin route is refused.
- Let the access session expire mid-task → the next action continues silently (refresh); kill the refresh too → returned to `/login`.

## 4. Workflow with surfaced gates  → SC-003/004
- Register a sample → appears in the list at stage 1.
- Open it → stage history shown; advance to molecular with consent incomplete → the backend reason is shown inline; complete the consent checklist → advance succeeds.
- Attempt a stage skip / advance an already-moved sample → the specific 409 reason is shown, no silent/duplicate change.

## 5. Dashboards & TAT board  → SC-005
- Each role's dashboard shows its actionable work queue + counts/breach flags; a multi-role user lands on the most privileged and can switch.
- The board shows samples in the 8 stage columns with time-in-stage; past-target samples flagged; advance a sample and confirm it moves columns on refresh (~30–60s or on action).

## 6. QC, batches, vendors  → FR-014/015/016
- Record a QC fail → report upload blocked; a pass → unblocked.
- Batch-advance several samples → per-member results (advanced / blocked-with-reason); one member's failure doesn't block others.
- Vendors: admin can edit; a non-admin sees read-only.

## 7. Reports & portal  → SC-006
- Upload a wrong type / oversize / non-QC sample → the specific reason; a valid PDF for a QC-passed sample → stored.
- A permitted role opens a stored report; an unpermitted role isn't offered retrieval.
- View a portal push status; retry a failed one and see the status change.

## 8. Theme & RTL  → SC-007
- Confirm the Medlabs palette, sentence case, and accessible contrast; toggle `dir="rtl"` and confirm the layout (nav, board, forms) mirrors correctly.

## Automated equivalent
`frontend/tests/` (Vitest + Testing Library + MSW) cover role gating, surfaced gate reasons, empty/error states, and RTL rendering against the mocked contract; `frontend/e2e/` (Playwright) runs the sign-in → register → advance-with-gate → dashboard → board → upload journeys against a live backend; `check:contract` guards drift. Green = acceptance.
