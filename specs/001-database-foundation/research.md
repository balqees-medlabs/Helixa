# Phase 0 Research: Database Foundation

**Feature**: 001-database-foundation · **Date**: 2026-11-14

All Technical Context items were resolved by the constitution (fixed stack) and the spec's Clarifications session, so there were no open `NEEDS CLARIFICATION` markers. The decisions below record *how* to realize the fixed stack for this layer and why.

---

## D1 — Auditability mechanism: database triggers vs application writes

**Decision**: Enforce audit with **generic PL/pgSQL triggers** on every tracked table. An `AFTER INSERT/UPDATE/DELETE` trigger inserts one `audit_log` row capturing actor, action, entity, before/after (JSONB), and timestamp, reading the actor from the per-transaction session context (`app.user_id`) and an optional `app.job_id`.

**Rationale**: FR-001/002/003 require that *every* change is audited in the *same transaction* and that no change bypasses the trail (Constitution IV). A trigger guarantees this at the data store — it cannot be forgotten by a caller and runs inside the writing transaction by construction. It also satisfies "DB owns triggers" (Article I.1) and defense-in-depth (Article III.3): even a backend bug that writes directly still produces an audit row. The backend's job narrows to *setting who* (session context); the DB guarantees *that it is recorded*.

**Alternatives considered**:
- *Application-level audit writes* (backend inserts audit rows): matches a literal reading of IV.1 ("backend writes") but is bypassable and easy to miss on a code path; rejected in favor of the stronger guarantee. The backend still owns *setting the actor*, so the spirit of IV.1 holds.
- *Logical decoding / WAL audit (e.g., pgaudit)*: captures statements, not business before/after with actor attribution; heavier to operate; rejected for v1.

---

## D2 — Acting identity: how the backend tells the database who is acting

**Decision**: A **session-context contract** using `SET LOCAL`. On each transaction the backend sets `app.user_id` (the acting user UUID), `app.role_names` (comma-separated role slugs), and optionally `app.job_id`. Triggers and RLS policies read them via `current_setting('app.user_id', true)` etc. `SET LOCAL` scopes them to the transaction so they never leak across pooled connections.

**Rationale**: Postgres RLS evaluates per-row using session state; `SET LOCAL` is the standard, pooler-safe way to pass request identity into policies and triggers (Constitution III.3). Keeping it to three well-known keys makes the backend↔DB contract explicit and testable (see `contracts/session-context.md`).

**Alternatives considered**:
- *One database role per application user*: strongest native RLS, but unmanageable for GoTrue-less, admin-created accounts and breaks connection pooling; rejected.
- *Session-level `SET` (not `LOCAL`)*: leaks identity across a pooled connection's next checkout; rejected as unsafe.

---

## D3 — Application database role & privilege model

**Decision**: Migrations run as the owner/superuser (via the `/infra` admin connection). The **backend connects as a dedicated non-superuser role** (`helixa_app`) that has DML on the `public` tables but **no** `BYPASSRLS` and **cannot disable triggers**. The `helixa_app` role is **created in `infra/bootstrap-app-role.sh` from `.env`, not in a migration** (constitution III.4: no credentials in version-controlled migrations); the migration only `GRANT`s to it. RLS is `ENABLE`d and `FORCE`d on restricted tables so even the table owner is subject to policy when acting as the app. The `fn_audit()` trigger is `SECURITY DEFINER` owned by the migration/superuser role, so it (and only it) can insert into `audit_log` under `FORCE RLS`.

**Rationale**: FR-003 requires append-only "for every role, including administrators." Administrative *application* users (role slug `admin`) are still the `helixa_app` database role under the hood, so they cannot `ALTER TABLE ... DISABLE TRIGGER` or delete audit rows. This is what makes the immutability real rather than cooperative.

**Alternatives considered**:
- *Backend connects as superuser*: would let a bug or an `admin` user bypass triggers/RLS; defeats the guarantee; rejected.

---

## D4 — Append-only enforcement

**Decision**: `BEFORE UPDATE OR DELETE` triggers on `audit_log` and `sample_stage_events` that `RAISE EXCEPTION`. Applied unconditionally (no role check) so they fire for everyone.

**Rationale**: Simple, total, and independent of RLS. Combined with D3 (app role can't disable triggers), this makes the two histories genuinely append-only (FR-003, SC-002).

**Alternatives considered**:
- *Revoke UPDATE/DELETE grants only*: a privileged role could still mutate; triggers are the backstop. We do both (revoke grants **and** trigger) for belt-and-suspenders.
- *Rules / `REVOKE` only*: weaker; rejected as sole mechanism.

---

## D5 — RLS visibility model

**Decision**: Two tiers (from Clarifications):
- **Restricted (admin-only)**: `users`, `roles`, `user_roles`, `audit_log` — visible only when `'admin'` ∈ `app.role_names`.
- **Operational (all roles)**: `samples`, `sample_stage_events`, `stages`, `stage_sla`, `vendors`, `working_calendar`, `jobs` — readable by any of the five roles when an acting identity is set.
Writes are additionally gated by the backend; RLS denies all access when no acting identity is present (FR-015).

**Rationale**: Matches the shared-pipeline/TAT-dashboard reality (operational roles need cross-stage visibility) while protecting accounts and the audit trail as the independent second layer (FR-014). Deny-by-default on missing context prevents accidental broad exposure.

---

## D6 — Patient data minimization

**Decision**: `samples` is keyed by a **pseudonymous** `case_id` (unique, not a patient identifier) plus non-identifying workflow metadata. No name/MRN columns; at most one optional, clearly-named free field (`external_ref`) left null by default. Reports/FASTQs are referenced by path, never stored inline.

**Rationale**: FR-009 and the privacy clarification. Minimizing identifiers at rest shrinks the blast radius and keeps the audit before/after snapshots free of direct identifiers.

---

## D7 — Seed strategy & values

**Decision**: Seed inside the same migration (idempotent inserts keyed by natural keys), containing:
- **Roles** (5): `admin`, `genomics`, `trf`, `molecular`, `bioinformatics`.
- **Stages** (8, ordered) with default SLA days: received 1 · consent & documentation 2 · molecular processing 4 · data generation 4 · TRF preparation 2 · TRF confirmation 1 · data conversion & QC 2 · report upload/archive/portal push 2 (sum = 18, the internal target).
- **Vendors** (4): Arcensus (4d, anchor=receipt), Reviity (28d, anchor=receipt), Sefdecode (5d, anchor=receipt), Centogene (30d, anchor=sequencing).
- **System actor**: one `users` row, `is_system = true`, no credentials, used as the actor for automated changes.
- **Working calendar**: default weekend rule `weekend_days = {5}` (Friday, the Medlabs work week) for the 45-working-day baseline, plus an empty holiday list, editable by admin. (The 18-day internal target counts calendar days including Fridays and does not use `weekend_days`.)
**No human admin** is seeded (created in M2 by `python -m app.cli create-admin`).

**Rationale**: FR-011/FR-012, SC-003. Seeding in-migration keeps "one command to reproduce" (SC-005) true and versioned.

---

## D8 — Vendor TAT anchor modeling

**Decision**: `vendors` carries `tat_days` and `tat_anchor` (`'receipt'` | `'sequencing'`). Centogene uses `'sequencing'`; the rest `'receipt'`.

**Rationale**: FR-010 and Article V.5 — external TAT is tracked separately and Centogene is counted from sequencing, not receipt. Modeling the anchor explicitly lets the backend compute each vendor's clock correctly without special-casing a name.

---

## D9 — Testing against real Postgres

**Decision**: pytest fixtures spin up a disposable PostgreSQL 16 (Docker/testcontainer or a dedicated test database), apply `alembic upgrade head`, and run as the `helixa_app` role. No SQLite.

**Rationale**: Triggers, RLS, `FORCE ROW LEVEL SECURITY`, and `current_setting` are Postgres-specific; SQLite cannot validate SC-002/SC-004. Tests must exercise the real engine to be meaningful.

---

## D10 — Scope boundary for migration 1.1

**Decision**: `sequencing_runs` and `run_samples` are **not** created here; they are reserved for migration `0002` (Spec 4). The `jobs` table **is** created now (Article VIII.6) so Spec 2's worker has a durable store.

**Rationale**: FR-018 and the spec's scope boundary; keeps this layer a clean single slice (Article VIII.5).
