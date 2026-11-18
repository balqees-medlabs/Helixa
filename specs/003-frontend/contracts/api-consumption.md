# Contract: API Consumption

**Feature**: 003-frontend · Traces FR-020/021, SC-008, research D2.

## The client
- TypeScript types generated from `backend/openapi.json` (`openapi-typescript`).
- A typed `apiFetch(path, init)`: base `/api`, `credentials: 'include'`, JSON (multipart for report upload), the silent-refresh behaviour (auth-flow.md), typed responses.
- **No endpoint is called that the contract does not define** — the generated path types are the only surface; hand-written URLs are disallowed by convention/lint.

## Drift guard (SC-008)
- `npm run check:contract` regenerates types from `../backend/openapi.json` and fails if they differ from the committed generated file. Run in CI and as a test, so a backend contract change that isn't regenerated breaks the build — no silent drift.

## Error & empty handling
- `401` → silent refresh (never shown raw). `403` → "not permitted". `404` → not-found view. `409`/`422` → backend `{detail}` surfaced verbatim (gate/validation). `413`/`415` → the specific report reason. Network/5xx → a clear retryable message. Empty collections → helpful empty states.

## Mutations → cache
- Each mutation invalidates the affected TanStack Query keys (advance → sample, events, board, metrics). Board/status queries poll ~30–60s.
