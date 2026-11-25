# ADR 0001 — Machine authentication via a scoped, revocable API token

**Status**: Accepted (ratified 2026-11-25 via constitution v2.1.0, Article II.4)
**Date**: 2026-11-25
**Feature**: 004-ngs-data-pipeline
**Constitution basis**: Article II.8 (a new auth mechanism requires a written decision); supports Articles III (security), IV (audit).

## Context

The NGS pipeline runs unattended on the lab host and must report results (ingest, conversion, augmentation, coverage, delivery) into Helixa. The constitution's human auth model (Article II.4: argon2 password → short-lived access JWT in an httpOnly cookie, admin-created accounts, no third-party IdP) assumes an interactive human. A headless script cannot perform a cookie login, and reusing a human's password on a shared host grants broad permissions and muddies audit attribution.

## Decision

Introduce a **machine auth path for non-human callers only**:

- A non-human **service user** (`pipeline-reporter`) with no password login, holding a single narrowly-scoped role permitted only to post pipeline results (and read the runs/samples it reports on).
- A long-lived, individually **revocable API token**, minted by an admin, returned once, stored only as an argon2 hash in an `api_tokens` table. Presented as `Authorization: Bearer <token>` on the reporting endpoints; held in the lab host's secret store, never in Helixa.
- On each request the backend verifies the token, resolves the service identity + role, and sets the acting identity on the transaction so RLS and the audit trigger attribute every post to the service user (Articles III.3, IV.2). Revocation takes effect immediately.

Human cookie+JWT auth is unchanged.

## Alternatives considered

- **Reuse a Bioinformatics human account** — broad permissions, human secret on a shared host, poor attribution. Rejected.
- **mTLS / client certificate** — strong, but heavier to operate than a single lab host needs. Rejected for v1.

## Consequences

- One new table (`api_tokens`), one new role, one service user; a small token-verification module in the backend.
- Least privilege + clean audit + a kill-switch (revoke). No change to human auth or the frontend.
- If machine callers proliferate later, revisit per-token scopes.
