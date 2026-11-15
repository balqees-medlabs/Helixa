# Quickstart & Validation: Database Foundation

**Feature**: 001-database-foundation · Proves Spec 1 works end-to-end against real PostgreSQL 16.

This is a run/verify guide, not implementation. It maps each check to a success criterion. Commands are illustrative; exact paths come from the implementation.

## Prerequisites (from M0)

- Docker + Compose on the lab server; `/infra/compose.yml` with `postgres:16` bound to `127.0.0.1:5432`.
- `/data/{reports,runs,backups}` exist; `/infra/backup.sh` present.
- `backend/` Python env with Alembic, SQLAlchemy, psycopg (see `backend/pyproject.toml`).
- Env: `DATABASE_URL` (admin, for migrations) and the `helixa_app` role credentials.

## 1. Bring up the database

```bash
cd infra && docker compose up -d postgres
# wait for healthy, then from backend/:
cd ../backend && alembic upgrade head
```

**Expect**: migration `0001_database_foundation` applies with no error. → **SC-005** (one command reproduces schema + seed).

## 2. Verify seed  → SC-003

```bash
psql "$DATABASE_URL" -c "SELECT slug FROM roles ORDER BY slug;"                 # 5 rows
psql "$DATABASE_URL" -c "SELECT position, slug, sla_days FROM stages JOIN stage_sla USING ... ORDER BY position;"  # 8 rows, Σ sla_days = 18
psql "$DATABASE_URL" -c "SELECT name, tat_days, tat_anchor FROM vendors ORDER BY name;"   # Arcensus/Reviity/Sefdecode/Centogene
psql "$DATABASE_URL" -c "SELECT count(*) FROM users WHERE is_system;"           # 1
psql "$DATABASE_URL" -c "SELECT count(*) FROM users WHERE NOT is_system;"       # 0  (no human admin yet)
```

**Expect**: exactly the seeded sets; Centogene anchor = `sequencing`; zero human users.

## 3. Verify append-only immutability  → SC-002 (run as the `helixa_app` role)

For each role in {admin, genomics, trf, molecular, bioinformatics}, set the session context (see `contracts/session-context.md`) and attempt mutation:

```sql
BEGIN;
SET LOCAL app.user_id = '<system actor id>';
SET LOCAL app.role_names = 'admin';
UPDATE audit_log SET action='INSERT' WHERE id = (SELECT id FROM audit_log LIMIT 1);   -- must RAISE
ROLLBACK;
-- likewise: DELETE FROM sample_stage_events … -- must RAISE
```

**Expect**: every UPDATE/DELETE on `audit_log` and `sample_stage_events` raises; row counts unchanged for all five roles **and** admin.

## 4. Verify audit completeness & attribution  → SC-001, FR-004

```sql
BEGIN;
SET LOCAL app.user_id = '<system actor id>';
SET LOCAL app.role_names = 'genomics';
INSERT INTO samples (case_id, current_stage_id, received_at)
  VALUES ('CASE-TEST-1', (SELECT id FROM stages WHERE position=1), now());
COMMIT;
-- then:
SELECT action, entity_table, actor_id FROM audit_log WHERE entity_id =
  (SELECT id FROM samples WHERE case_id='CASE-TEST-1');   -- exactly one INSERT row, actor = system actor
```

Also confirm a write with **no** `app.user_id` set is rejected.

**Expect**: one audit row per change, correct actor; un-attributed write refused.

## 5. Verify RLS visibility  → SC-004, FR-014/FR-015

```sql
-- operational role sees samples but not admin tables:
BEGIN; SET LOCAL app.user_id='<any user>'; SET LOCAL app.role_names='genomics';
SELECT count(*) FROM samples;      -- > 0
SELECT count(*) FROM users;        -- 0 (restricted)
SELECT count(*) FROM audit_log;    -- 0 (restricted)
ROLLBACK;
-- admin sees everything:
BEGIN; SET LOCAL app.user_id='<admin user>'; SET LOCAL app.role_names='admin';
SELECT count(*) FROM users;        -- > 0
ROLLBACK;
-- no identity → deny by default:
BEGIN; SELECT count(*) FROM samples; -- 0
ROLLBACK;
```

**Expect**: operational role reads samples, zero rows from restricted tables; admin reads all; no-identity session reads nothing.

## 6. Verify uniqueness  → SC-007

Insert a second `samples` row with `case_id='CASE-TEST-1'` → rejected by the unique constraint.

## 7. Verify backup restores  → SC-006

```bash
/infra/backup.sh                                   # produces /data/backups/helixa-<ts>.dump
createdb helixa_restore_check
pg_restore -d helixa_restore_check /data/backups/helixa-<ts>.dump
# compare row counts of key tables between source and restore
```

**Expect**: restore succeeds; seed + test rows match the source.

## 8. Verify clean rebuild  → SC-005, FR-016

```bash
alembic downgrade base && alembic upgrade head      # no errors, schema identical
```

## Automated equivalent

The checks above are mirrored by `backend/tests/db/` (see plan.md structure): `test_seed.py`, `test_append_only.py`, `test_audit_trigger.py`, `test_rls_visibility.py`, `test_migration_rebuild.py` — all run against a disposable Postgres (D9). Green suite = feature acceptance.
