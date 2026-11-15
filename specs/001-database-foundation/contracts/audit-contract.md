# Contract: Audit & Append-Only Guarantees

**Feature**: 001-database-foundation · Traces: FR-001..FR-004, SC-001, SC-002.

## What is guaranteed

1. **Completeness** — Every INSERT, UPDATE, and DELETE on a *tracked* table writes one `audit_log` row. Tracked tables: `users`, `roles`, `user_roles`, `stages`, `stage_sla`, `samples`, `sample_stage_events` (insert only), `vendors`, `working_calendar`, `holidays`, `jobs`.
2. **Atomicity** — The audit row is written by a trigger inside the same transaction as the change. If the transaction rolls back, the audit row does too. There are never orphan audit rows nor un-audited changes (SC-001).
3. **Attribution** — `actor_id` = `app.user_id`. Automated changes carry the system actor id plus `job_id` = `app.job_id` (FR-004). A write with no `app.user_id` set is rejected.
4. **Content** — `before` = `to_jsonb(OLD)` (null on INSERT); `after` = `to_jsonb(NEW)` (null on DELETE); plus `action`, `entity_table`, `entity_id`, `at`.
5. **Immutability** — `audit_log` and `sample_stage_events` reject UPDATE and DELETE for every role, enforced by `BEFORE UPDATE OR DELETE` triggers. The `helixa_app` role cannot disable these triggers (D3). (SC-002)

## What callers may rely on

- Reading the full history of an entity: `SELECT * FROM audit_log WHERE entity_table=$1 AND entity_id=$2 ORDER BY at`.
- Reconstructing who advanced a sample: `sample_stage_events` is itself immutable and carries `actor_id`.

## What is explicitly NOT in this contract

- Business validation of *whether* a change is allowed (stage gates, QC-before-report) — that is backend logic (Spec 2).
- Retention/rotation of audit rows — audit is append-only and retained; backups are an `/infra` concern.

## Verification hooks (for `quickstart.md` / tests)

- Insert a sample under an identity → exactly one audit row with `action='INSERT'`, matching `after`.
- Attempt `UPDATE audit_log …` and `DELETE FROM sample_stage_events …` as each role → all raise; row counts unchanged.
- Attempt a write with no `app.user_id` → rejected.
