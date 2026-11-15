# Contract: Session Context (backend ↔ database)

**Feature**: 001-database-foundation · Stability: this is the interface Spec 2 (backend) MUST honor.

The database decides audit attribution and RLS visibility from three transaction-scoped settings the backend sets with `SET LOCAL` at the start of every transaction, **before** any read or write.

## Settings

| Key | Type (as text) | Required | Meaning |
|---|---|---|---|
| `app.user_id` | uuid | Yes for any write; yes for restricted reads | The acting user's `users.id`. For automated work, set to the seeded **system actor** id. |
| `app.role_names` | comma-separated slugs | Yes for reads | The acting user's roles, e.g. `genomics,bioinformatics`. `admin` grants all. |
| `app.job_id` | uuid | Optional | Set by the worker when the change originates from a `jobs` row (recorded on audit rows, FR-004). |

## Rules the backend MUST follow

1. Use `SET LOCAL` (not `SET`) so values are scoped to the transaction and never leak across pooled connections.
2. Set `app.user_id` and `app.role_names` before issuing statements. A write with no `app.user_id` is rejected by the audit trigger (no un-attributed changes).
3. For automated/background changes, set `app.user_id` = system actor id and `app.job_id` = the job's id.
4. Connect as the non-superuser `helixa_app` role (no `BYPASSRLS`). The backend never connects as superuser for request handling.

## Guarantees the database gives in return

- Every tracked-table change produces exactly one `audit_log` row in the same transaction (commit-or-neither).
- With no identity set, reads return zero rows (deny by default); restricted tables return rows only when `admin` is among the roles.
- `audit_log` and `sample_stage_events` cannot be updated or deleted by anyone connecting as `helixa_app`, regardless of roles.

## Example (illustrative, not implementation)

```sql
BEGIN;
SET LOCAL app.user_id = '…uuid of acting user…';
SET LOCAL app.role_names = 'genomics';
-- optional for jobs:  SET LOCAL app.job_id = '…uuid…';
INSERT INTO samples (case_id, current_stage_id, received_at) VALUES ('CASE-00123', …, now());
COMMIT;   -- audit_log row for this INSERT is committed atomically
```
