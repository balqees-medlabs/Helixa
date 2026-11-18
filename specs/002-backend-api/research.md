# Phase 0 Research: Backend API

**Feature**: 002-backend-api · **Date**: 2026-11-15

The stack is fixed by constitution v2.0.0 and the Clarifications session resolved the open behaviors, so there were no `NEEDS CLARIFICATION` markers. These decisions record *how* to realize the backend.

---

## D1 — Authentication: tokens, hashing, delivery

**Decision**: Backend-native auth. Passwords hashed with **argon2id** (`argon2-cffi`). A short-lived **access JWT** (~15 min, HS256 signed with a key from `.env`) delivered as an `HttpOnly; Secure; SameSite=Lax` cookie; a **rotating refresh token** (opaque random, stored only as a hash in `refresh_tokens`) in a second HttpOnly cookie scoped to `/auth`. `/auth/refresh` verifies+rotates (old token revoked, new issued); `/auth/logout` revokes the refresh family. Re-auth after ~12 h idle / 7 d absolute (refresh-token `expires_at`).

**Rationale**: Matches constitution III.1 (backend issues JWT, never exposed to JS) and the session clarification. Access tokens stay stateless and short; the refresh token is server-tracked so logout/rotation/breach-revocation are real. Storing only the refresh **hash** means a DB read can't impersonate a user.

**CSRF**: the refresh cookie is `SameSite=Strict` scoped to `/auth` (the rotation endpoint is the sensitive one); the access cookie is `SameSite=Lax`. The frontend (Spec 3) is a same-origin SPA behind the same Caddy proxy, so cross-site requests don't carry the cookies; if a cross-origin client is ever added, a CSRF token / custom-header check is layered on then.

**Alternatives**: Server-side session store (simpler revocation, but adds a store and a lookup per request — unnecessary when the refresh table already gives revocation); long-lived access tokens (rejected — weaker, can't revoke).

---

## D2 — Per-request transaction & acting identity

**Decision**: A `get_db` dependency opens one transaction per request, resolves the authenticated user, and calls Spec 1 `set_session_context(conn, user_id, role_names)` **before** any handler query; commit on success, roll back on exception. The acting user id comes from the validated access token, never from a DB lookup under RLS (which the user couldn't perform).

**Rationale**: Spec 1's audit triggers reject un-attributed writes and RLS hides rows without an identity, so the context must be set first, every request. One transaction per request keeps a change and its audit row atomic (Constitution IV).

**Batch exception**: an operation that must report **per-member** partial success (batch advance, FR-012) cannot be all-or-nothing within the single request transaction — the `batch_service` advances each member inside a **savepoint** (`conn.begin_nested()`) so one member's conflict/gate failure rolls back only that member while the rest commit. The outer request transaction still commits once at the end.

**Alternatives**: Set context inside each service (repetitive, easy to forget); middleware before routing (can't see the resolved user cleanly) — the dependency is the right seam.

---

## D3 — RBAC model & per-stage role mapping

**Decision**: `require_roles(*slugs)` FastAPI dependencies on routes; `admin` passes every guard. Default stage→role authority (admin always allowed, refinable by config):

| Stage | Advancing role(s) |
|---|---|
| received, consent & documentation | genomics |
| molecular processing | molecular |
| data generation, data conversion & QC | bioinformatics |
| TRF preparation, TRF confirmation | trf |
| report upload/archive/portal push | bioinformatics |

**Rationale**: Constitution III.2. Mapping mirrors the department's roles; keeping it in one config table/constant lets it change without touching route code. RLS remains the second layer beneath these guards.

**Alternatives**: Per-endpoint hardcoded role checks (scattered, hard to audit) — centralizing the map is clearer and testable.

---

## D4 — Stage gates + optimistic concurrency

**Decision**: `workflow_service.advance(sample, from_stage, to_stage)` runs in the request transaction: (1) assert `to_stage = from_stage + 1` (no skips); (2) check the gate for `to_stage` (consent complete before molecular processing; QC passed before report/archive); (3) `UPDATE samples SET current_stage_id=:to WHERE id=:id AND current_stage_id=:from` — **0 rows updated ⇒ 409 Conflict** (someone else advanced it); (4) insert the `sample_stage_events` row (duration auto-filled by the Spec 1 trigger). All audited.

**Rationale**: Clarification (optimistic concurrency, reject stale). The `WHERE current_stage_id=:from` guard is the concurrency check — atomic, no extra locking, no version column needed because `current_stage_id` *is* the version for progression. Gates server-side only (Constitution V.2).

**Alternatives**: `SELECT … FOR UPDATE` row lock (serializes, but the clarification wants the stale attempt *rejected*, not queued); a separate `version` column (redundant with `current_stage_id`).

---

## D5 — Consent checklist, QC, data-generation, batches

**Decision** (migration `0002` tables):
- `consent_items` — per-sample checklist rows (`sample_id`, `item`, `complete`, `completed_at`); the molecular gate requires all required items complete.
- `qc_results` — `sample_id`, `kind` (`data_generation`|`qc`), `passed`, `detail`, `recorded_at`; the report gate requires a `qc` row with `passed = true`.
- `batches` + `batch_members` — grouping; batch operations limited to **stage-advance and assignment** (clarification), applied per member with each member's gate enforced independently and recorded separately.

**Rationale**: FR-011/013/012. Keeping QC/data-gen as their own audited rows (not just a stage event) preserves the outcome detail and lets Spec 4 later drive data generation by writing a `qc_results`/stage event through the same path.

---

## D6 — Report storage & serving

**Decision**: On upload for a QC-passed sample, stream the file to `REPORTS_ROOT/<case_id>/<uuid>-<filename>`, compute a SHA-256, and write a `reports` row (`sample_id`, `path`, `content_type`, `size_bytes`, `sha256`, `uploaded_by`, `uploaded_at`). Serve via a download route guarded by `require_roles` + RLS, streaming from disk. Accept a configurable allowlist (default `application/pdf`) up to a configurable max size (default 50 MB); reject others before writing.

**Report-reader roles**: retrieval (metadata + file) is restricted by a route guard to `admin`, `bioinformatics`, and `genomics` — the roles that produce or act on final results; `trf` and `molecular` handle intermediate steps and do not read reports. This guard sits on top of RLS (operational tier) and is refinable in the same config as the stage→role map (D3).

**Rationale**: Constitution VI.4 (filesystem storage, metadata in DB, served through the backend with RBAC) and FR-016. Checksum supports the restore-check/integrity story. Naming the reader roles resolves the "authorized roles" of FR-016/SC-007 so the tests assert exact allow/deny.

**Alternatives**: Store blobs in Postgres (rejected by constitution II/VI — files on disk); object store/MinIO (unnecessary for this scale).

---

## D7 — Portal push: isolated client + jobs worker

**Decision**: On report completion, create a `portal_pushes` row (`report_id`, `status` queued/success/failed, `attempts`, `last_error`, `next_attempt_at`) **and** enqueue a `jobs` row (`kind='portal_push'`). `app/worker.py` (the Spec 1 jobs worker) leases jobs, sets `app.job_id` + the system actor context, and calls `PortalClient.push(report)` behind a single interface whose default implementation is a **mock** (configurable base URL/token from `.env`). Failure → `status=failed`, backoff `next_attempt_at`, retry up to a configurable cap; success is idempotent (a delivered push is not re-sent). Case-close runs when the push reaches `success`.

**Rationale**: Constitution VI.1–VI.2 (tracked, retryable, isolated) and the clarifications (case closes only on push success; retry without duplicate). Reusing the `jobs` table means pushes survive restarts and are audited as the system actor.

**Alternatives**: In-process `BackgroundTasks` (die on restart — rejected per Spec 1 research); Celery/Redis (needs an Article II.8 decision and a broker — unnecessary).

---

## D8 — Migration 0002 scope & ordering

**Decision**: One migration `0002_backend_auth_workflow`: add auth columns to `users` (`password_hash`, `password_set_at`, `last_login_at`), create `refresh_tokens`, `consent_items`, `qc_results`, `batches`, `batch_members`, `reports`, `portal_pushes`; attach the Spec 1 `fn_audit` trigger to each new table and RLS policies (operational tier via `has_identity()`, except `refresh_tokens` which is admin/self-only); extend `downgrade()`. `0003+` left for Spec 4.

**Rationale**: Keeps schema migration-only (Constitution VIII.1) and consistent with Spec 1's trigger/RLS patterns. New tables get the same audit + RLS treatment automatically.

---

## D9 — OpenAPI contract export

**Decision**: FastAPI auto-generates OpenAPI; a small script/CLI writes `backend/openapi.json` (committed) that the frontend (Spec 3) consumes. A test asserts the generated schema matches the committed file (no drift, SC-008).

**Rationale**: Constitution VIII.4 (OpenAPI as the single source of API truth).

---

## D10 — Testing strategy

**Decision**: Extend the Spec 1 real-Postgres harness. API tests use FastAPI `TestClient` against a disposable DB with migrations applied and the `helixa_app` role; helpers mint sessions for each role. Cover: every auth path (login/refresh/rotate/logout/expiry), every RBAC guard (allowed+denied per role), every stage gate (consent, QC, no-skip), the optimistic-concurrency 409, report RBAC + type/size rejects, and the portal push retry-to-success with the mock. The portal client is always mocked.

**Rationale**: Constitution VIII.2 and SC-001…SC-009; these behaviors are Postgres- and middleware-specific and can only be proven end-to-end.
