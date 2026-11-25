# Phase 1 Data Model: NGS Data-Generation & Delivery Pipeline Tracking

**Feature**: 004-ngs-data-pipeline · **Date**: 2026-11-25

All new tables land in the `public` schema via Alembic migration `0003_ngs_pipeline.py` (Article VIII.1). Each gets the standard treatment: an `audit_log` trigger firing in-transaction (Article IV.1), two-tier RLS mirroring the existing tables (Article III.3), and — where the row is a historical fact — an append-only trigger rejecting UPDATE/DELETE for every role (Article IV.3). Helixa stores **references and facts only** — never file contents, never vendor secrets.

Existing tables reused: `samples`, `vendors`, `stages`, `sample_stage_events`, `reports`, `portal_pushes`, `roles`, `users`, `user_roles`, `audit_log`, `jobs`.

## New & extended entities

### `sequencing_runs` (new)

A completed instrument run as reported by the lab.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | `gen_random_uuid()` |
| `run_folder` | text, unique, not null | e.g. `20261118_AV242301_181126_AMJ_A1_WGS` |
| `instrument` | text, not null | e.g. `AV242301` |
| `project` | text | e.g. `AMJ` |
| `run_side` | text | `A1` / `B1` (nullable) |
| `run_date` | date | |
| `storage_location` | text | NAS/mount reference (path only; storage-agnostic) |
| `readiness` | text, not null | `received` \| `ready` \| `incomplete` (check constraint) |
| `cycle_r1`,`cycle_r2`,`cycle_i1`,`cycle_i2` | int | per-read cycle counts from the run parameters |
| `created_by` | uuid FK→users | |
| `created_at` | timestamptz, default now | |

### `pipeline_samples` (new) — 1:1 bridge to a workflow Sample

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `sample_id` | uuid FK→samples, **unique**, not null | the existing workflow Sample (D4: must already exist) |
| `ngs_sample_id` | text, not null | lab NGS id (G-/R-number) |
| `sample_type` | text, not null | `G` (clinical) \| `R` (lifestyle) (check) |
| `coverage_target_x` | int, not null | default by type: 30 (G) / 15 (R); overridable |
| `vendor_id` | uuid FK→vendors | assigned delivery vendor |
| `pipeline_state` | text, not null | derived summary: `intake` \| `ingested` \| `converted` \| `augmented` \| `qc_pass` \| `qc_below` \| `delivered` |
| `created_by` | uuid FK→users | |
| `created_at` | timestamptz | |

Uniqueness: `(sample_id)` one-to-one; `ngs_sample_id` unique within its run context. Validation: refuse creation when no matching registered `samples` row (FR-002/D4).

### `merge_plan_runs` (new) — intended source runs per sample

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `pipeline_sample_id` | uuid FK→pipeline_samples | |
| `run_id` | uuid FK→sequencing_runs | an intended source run |
| `created_by` | uuid FK→users | molecular or bioinformatics (D6) |

Unique `(pipeline_sample_id, run_id)`. The augmentation result (below) is validated against this set.

### `pipeline_results` (new, append-only) — ingest / conversion / augmentation

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `pipeline_sample_id` | uuid FK→pipeline_samples | |
| `kind` | text, not null | `ingest` \| `conversion` \| `augmentation` (check) |
| `status` | text, not null | `ok` \| `failed` |
| `read_length` | int | per-sample/run; may differ (e.g. trimmed 123) |
| `q30` | numeric | conversion only |
| `reads_assigned_pct` | numeric | conversion only |
| `source_run_ids` | uuid[] | augmentation only — actual merged runs |
| `integrity_ok` | boolean | augmentation only — gzip + R1==R2 |
| `plan_match` | boolean | augmentation only — matched `merge_plan_runs` (D6) |
| `detail` | jsonb | free-form extras (FASTQ paths, log refs) |
| `reported_by` | uuid FK→users | the `pipeline-reporter` service identity |
| `reported_at` | timestamptz | |
| `idempotency_key` | text, unique, not null | run+sample+kind+reporter result id (D7) |

Stage driving (D2): an `ingest` `ok` result completes **Stage 4** for a sample at Stage 3; a `conversion` `ok` result **combined with** a coverage `pass` completes **Stage 7**. Advance uses the existing optimistic-concurrency update; a held/out-of-order case is a no-op advance, not an error.

### `coverage_results` (new, append-only)

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `pipeline_sample_id` | uuid FK→pipeline_samples | |
| `read_pairs` | bigint, not null | |
| `yield_gb` | numeric, not null | reported by the lab's coverage model |
| `depth_x` | numeric, not null | reported estimate |
| `target_x` | int, not null | the target measured against |
| `verdict` | text, not null | `pass` \| `below` (check; `pass` when `depth_x >= target_x`) |
| `reported_by` | uuid FK→users | service identity |
| `reported_at` | timestamptz | |
| `idempotency_key` | text, unique, not null | |

History is immutable (FR-015); the **latest** verdict governs the Stage 7 gate and the delivery gate. A post-top-up re-measure is a new row.

### `vendor_deliveries` (new, mutable + audited)

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `pipeline_sample_id` | uuid FK→pipeline_samples | |
| `vendor_id` | uuid FK→vendors | |
| `destination_kind` | text, not null | copied from the vendor profile at send time |
| `status` | text, not null | `pending` \| `uploading` \| `delivered` \| `failed` (check) |
| `verification_state` | text, not null | `unverified` \| `readback_ok` \| `receipt_confirmed` \| `checksum_marker_ok` (check) |
| `completion_marker` | text | e.g. the `Upload complete.txt` reference / receipt id |
| `evidence` | jsonb | sizes / checksums / object keys (no secrets) |
| `reported_by` | uuid FK→users | service identity |
| `reported_at`,`updated_at` | timestamptz | |

Rules: created/advanced only for a sample whose **latest coverage verdict is `pass`** (FR-020); not `delivered` until the profile's verification rule is satisfied (FR-018/019). No credentials stored (FR-021).

### `api_tokens` (new) — machine credentials (D-01)

| Field | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `name` | text, not null | e.g. `pipeline-reporter@lab-host` |
| `user_id` | uuid FK→users | the non-human service user |
| `token_hash` | text, not null | argon2 hash — the token itself is shown once and never stored |
| `created_by` | uuid FK→users | an admin |
| `created_at` | timestamptz | |
| `revoked_at` | timestamptz, null | revoke → immediate auth failure (FR-024) |

### `vendors` (extended) — non-secret delivery profile (D5)

Added columns: `delivery_kind` (`s3` \| `sftp`), `endpoint_ref` jsonb (region/bucket or host — non-secret), `naming_pattern` text, `md5_required` boolean, `verification_method` (`readback` \| `receipt` \| `checksum_marker`). Existing `tat_days`/`tat_anchor`/`is_active` unchanged.

### Seed / roles

- A new role `pipeline-reporter` (in `roles`) whose policies permit INSERT on `pipeline_results`, `coverage_results`, and `vendor_deliveries`; **UPDATE on `vendor_deliveries`** (delivery status transitions — mutable/audited, not append-only); and **SELECT** on the runs/samples/results it reports on (to read a sample's coverage clearance before opening a delivery, FR-022). Nothing else.
- A non-human service **user** holding only that role, used as `reported_by` and audited per Article IV.2.
- The three current vendors seeded/backfilled with their delivery profiles (Arcensus `s3`/`readback`, SelfDecode `s3`/`receipt`, Revvity `sftp`/`checksum_marker`, `md5_required=true`).

## Rules traced to requirements

| Rule | Source |
|---|---|
| Run + samples recorded by molecular, linked to existing Sample, duplicate id rejected | FR-001/002/004, D4 |
| Coverage target defaults by type, overridable | FR-003 |
| Ingest → Stage 4; conversion + QC pass → Stage 7; in-order, held | FR-007/013, Article V.3, D2 |
| Coverage history immutable; latest governs gate | FR-012/015 |
| Idempotent reporting, no double-advance | FR-016, D7 |
| Merge plan recorded before augmentation + validated | FR-009/026, D6 |
| Delivery gated on PASS; per-profile verification; no secrets | FR-017/018/019/020/021, D5/D8 |
| Scoped service identity + revocable token, audited | FR-024, D-01 |
| References/facts only; role-restricted visibility (RLS) | FR-025, D8, Article III.3 |
| Returned report reuses report storage + portal push | FR-023, Article VI.1–4 |
