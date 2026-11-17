# Phase 1 Data Model: Backend API

**Feature**: 002-backend-api · **Date**: 2026-11-15 · Target: PostgreSQL 16, migration `0002`

Additive to the Spec 1 schema. Conventions as in Spec 1: `id uuid PK DEFAULT gen_random_uuid()`, `created_at timestamptz DEFAULT now()`. Every new table is **tracked** (Spec 1 `fn_audit` trigger: INSERT/UPDATE/DELETE → `audit_log`) and carries RLS (operational tier `USING(has_identity())`, unless noted). Nothing here is append-only except where stated.

---

## Columns added to existing tables

### `users` (+ auth)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| password_hash | text | NULL | argon2id; NULL for the system actor and until an admin sets it |
| password_set_at | timestamptz | NULL | |
| last_login_at | timestamptz | NULL | |

No credentials for `is_system`; the first human admin is created by `app.cli create-admin` (not seeded).

---

## New tables

### `refresh_tokens`  (restricted: admin or owner)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| user_id | uuid | FK→users ON DELETE CASCADE, NOT NULL | |
| token_hash | text | UNIQUE NOT NULL | SHA-256 of the opaque token; raw value never stored |
| family_id | uuid | NOT NULL | rotation family; reuse of a rotated token revokes the family |
| issued_at | timestamptz | NOT NULL DEFAULT now() | |
| expires_at | timestamptz | NOT NULL | absolute (~7 d) / idle (~12 h) enforced in service |
| revoked_at | timestamptz | NULL | set on rotation or logout |
| Index | | `(user_id)`, `(token_hash)` | |

RLS: visible only when `is_admin()` or `user_id = current_setting('app.user_id')::uuid`.

### `consent_items`  (operational)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| sample_id | uuid | FK→samples ON DELETE CASCADE, NOT NULL | |
| item | text | NOT NULL | checklist item key |
| required | boolean | NOT NULL DEFAULT true | |
| complete | boolean | NOT NULL DEFAULT false | |
| completed_by | uuid | FK→users NULL | |
| completed_at | timestamptz | NULL | |
| UNIQUE (sample_id, item) | | | |

Gate: molecular processing requires every `required` item for the sample `complete = true`.

### `qc_results`  (operational)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| sample_id | uuid | FK→samples NOT NULL | |
| kind | text | NOT NULL CHECK in ('data_generation','qc') | |
| passed | boolean | NOT NULL | |
| detail | jsonb | NOT NULL DEFAULT '{}' | metrics/notes; data-location ref for data_generation |
| recorded_by | uuid | FK→users NOT NULL | |
| recorded_at | timestamptz | NOT NULL DEFAULT now() | |
| Index | | `(sample_id, kind)` | |

Gate: report/archive requires a `kind='qc'` row with `passed=true` for the sample.

### `batches`  (operational)
| Column | Type | Constraints |
|---|---|---|
| name | text | NOT NULL |
| created_by | uuid | FK→users NOT NULL |

### `batch_members`  (operational)
| Column | Type | Constraints |
|---|---|---|
| batch_id | uuid | FK→batches ON DELETE CASCADE, NOT NULL |
| sample_id | uuid | FK→samples ON DELETE CASCADE, NOT NULL |
| UNIQUE (batch_id, sample_id) | | |

Batch operations: **stage-advance and assignment only** (each member advanced through the same single-step transition, its own gate enforced; failures reported per member, do not block others).

### `reports`  (operational)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| sample_id | uuid | FK→samples NOT NULL | |
| path | text | NOT NULL | `REPORTS_ROOT/<case_id>/<uuid>-<filename>` |
| content_type | text | NOT NULL | allowlist (default `application/pdf`) |
| size_bytes | bigint | NOT NULL CHECK (size_bytes > 0) | ≤ configurable max (default 50 MB) |
| sha256 | text | NOT NULL | integrity |
| uploaded_by | uuid | FK→users NOT NULL | |
| uploaded_at | timestamptz | NOT NULL DEFAULT now() | |

Upload rejected unless the sample has a passing `qc` result (FR-016).

### `portal_pushes`  (operational)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| report_id | uuid | FK→reports NOT NULL UNIQUE | one delivery per report (idempotent) |
| status | text | NOT NULL DEFAULT 'queued' CHECK in ('queued','success','failed') | |
| attempts | integer | NOT NULL DEFAULT 0 | |
| last_error | text | NULL | |
| next_attempt_at | timestamptz | NOT NULL DEFAULT now() | backoff |
| delivered_at | timestamptz | NULL | set once on success |
| Index | | `(status, next_attempt_at)` | worker poll |

Processed by the `jobs` worker (`kind='portal_push'`). `UNIQUE(report_id)` + `delivered_at` guard make retries non-duplicating. Case-close fires when `status='success'`.

---

## Sample lifecycle (state machine — enforced in `workflow_service`)

```text
received →1 consent & documentation →2 molecular processing →3 data generation
   →4 TRF preparation →5 TRF confirmation →6 data conversion & QC →7 report/archive/portal
```

Transition rules (server-side, optimistic-concurrency guarded by `WHERE current_stage_id = :from`):

| Transition | Gate |
|---|---|
| → molecular processing | all required `consent_items` complete (FR-009/011) |
| → report/archive | a `qc_results` row `kind='qc', passed=true` (FR-009/013) |
| any | target = current + 1 (no skips, FR-010); stale `from` ⇒ 409 (FR-010a) |

Sample `status`: `active` → `closed` only when its report's `portal_pushes.status='success'` (FR-019); `on_hold` is an admin action.

## Validation rules traced to requirements

| Rule | Source |
|---|---|
| argon2 password hash; no creds for system actor; admin via CLI | FR-005/006, D1 |
| refresh token stored as hash, rotating, revocable | FR-001, D1 |
| consent gate before molecular; QC gate before report | FR-009/011/013, V.2 |
| no stage skip; stale advance ⇒ conflict | FR-010/010a, SC-004/009 |
| batch = advance + assignment, per-member gates | FR-012 |
| report requires QC pass; type/size allowlist; served by RBAC | FR-016, SC-007 |
| portal push tracked/retryable/idempotent; case-close on success | FR-017/019, SC-006/009 |
| every new table audited + RLS | IV, III.3 |
