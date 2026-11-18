# Contract: Authentication & Sessions

**Feature**: 002-backend-api · Traces FR-001..FR-007, SC-001/002/003, research D1/D2/D3.

## Session mechanics
- `POST /auth/login` `{email, password}` → verify argon2id hash → set `access` cookie (JWT, ~15 min) + `refresh` cookie (opaque, ~7 d absolute / ~12 h idle). Body: the user + roles. Wrong credentials → `401` (no distinction between unknown user and bad password).
- `POST /auth/refresh` → look up the presented refresh token by hash; if valid and unrevoked, **rotate** (revoke it, issue a new one in the same family) and reissue the access cookie. A presented token that was already rotated (reuse) → revoke the whole family and `401` (breach response).
- `POST /auth/logout` → revoke the refresh family, clear both cookies. Always `204`.
- Access token carries `sub` (user id) and is the sole per-request identity source; expiry → `401`, client calls `/auth/refresh`.

## Guarantees
- Every protected route rejects a missing/invalid/expired access token with `401`, returning no data and making no change (SC-001).
- `require_roles(*slugs)` returns `403` for an authenticated user lacking the role; `admin` passes all guards (SC-002).
- Raw refresh tokens are never stored (only SHA-256) and never appear in a response body; access/refresh live only in HttpOnly cookies (III.1).
- Account/role management is admin-only; `GET /auth/me` returns the caller's own account and roles (FR-005).
- First admin: `python -m app.cli create-admin --email … ` (prompts for a password, writes an argon2 hash) — the only account-creation path that doesn't require an existing admin (FR-006).

## Verification hooks
- login→me round-trip returns correct roles; protected route without cookie → 401; each role allowed/denied on a role-guarded route; refresh rotates (old token 401 on reuse, family revoked); logout then protected route → 401.
