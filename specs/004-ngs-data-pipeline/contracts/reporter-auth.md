# Contract: Pipeline-Reporter Machine Authentication (D-01)

**Feature**: 004-ngs-data-pipeline · Traces FR-024. Governance: ADR `docs/decisions/0001-service-identity-api-token.md` (Article II.8 written decision). This is a **new auth path for non-human callers only**; human cookie+JWT auth (Article II.4) is unchanged.

## Identity

- A non-human **service user** exists in `users` with no password login, holding only the `pipeline-reporter` role.
- Its role's permissions (backend guard + Postgres RLS) allow **only**: INSERT on `pipeline_results`, `coverage_results`, `vendor_deliveries`; and read of the runs/samples it reports on. No access to other users, reports, admin, or workflow mutation beyond the stage advances those result posts trigger server-side.

## Token

- An admin mints a token via `POST /api-tokens` `{name, role:"pipeline-reporter"}`. The response returns the raw token **once**; Helixa stores only its argon2 hash in `api_tokens` (the raw token never persists — mirrors the password-hash rule, Article III.4).
- The token is long-lived and individually revocable. `DELETE /api-tokens/{id}` sets `revoked_at`; a revoked or unknown token is rejected immediately.

## Presentation & verification

- The lab host presents the token as a bearer credential (`Authorization: Bearer <token>`) on the reporting endpoints only. It is held in the host's own secret store, never in Helixa.
- On each request the backend: hashes/compares against non-revoked `api_tokens`, resolves the service user + `pipeline-reporter` role, and sets the acting identity on the transaction (`SET LOCAL app.user_id / app.role_names`) so RLS and the audit trigger attribute the post to the service identity (Article III.3, IV.2).
- A valid token on a non-reporting route still fails authorization (role scope) → `403`. A missing/invalid/revoked token on a reporting route → `401`.

## Audit

Every result post is written to `audit_log` in the same transaction, attributed to the service user, with the originating `idempotency_key` retained (Article IV.1–2). No token value is ever logged.
