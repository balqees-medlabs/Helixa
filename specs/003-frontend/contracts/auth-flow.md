# Contract: Auth & Session Flow

**Feature**: 003-frontend · Traces FR-001..FR-006, SC-001/002, research D1/D3.

## Sign in
- `/login` posts `{email, password}` to `POST /api/auth/login`. Success → backend sets httpOnly `access` + `refresh` cookies; the app reads `{user, roles}` from the response and routes to the landing dashboard. Failure → one non-revealing error ("Invalid email or password").

## Session state
- The app never reads a token. Session truth = `GET /api/auth/me`: `200` ⇒ signed in (`{user, roles}`); `401` ⇒ signed out.
- Next.js middleware redirects `(app)` routes to `/login` when the `access` cookie is absent (presence check only; never decodes the token). The `(app)` layout confirms via `/auth/me`.

## Silent refresh (expiry mid-task)
- `apiFetch`: on any `401`, call `POST /api/auth/refresh` exactly once and retry the original request.
  - Refresh `200` ⇒ retry succeeds; the action continues with no interruption (FR-004).
  - Refresh fails ⇒ clear `['me']`, route to `/login?next=<attempted>`, preserving context where feasible.
- Concurrent 401s share one in-flight refresh (no stampede).

## Sign out
- `POST /api/auth/logout` → backend revokes the refresh family and clears cookies; app clears auth state and routes to `/login`. Protected routes then unreachable (FR-005).

## Deployment note (research D1)
- Same-origin behind Caddy; API under `/api` (prefix stripped to the backend). The refresh cookie's path must reach `/api/auth/refresh` — handled by a **Caddy `Set-Cookie` path rewrite** (`/auth` → `/api/auth`). Pure infra; no backend change (research D1).
