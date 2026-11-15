# Phase 1 Data Model: Database Foundation

**Feature**: 001-database-foundation · **Date**: 2026-11-14 · Target: PostgreSQL 16, schema `public`

Conventions: every table has `id uuid PRIMARY KEY DEFAULT gen_random_uuid()` (via `pgcrypto`/`gen_random_uuid`) unless noted, `created_at timestamptz NOT NULL DEFAULT now()`. Monetary/duration in explicit units. Slugs are lowercase. "Tracked" = has audit triggers (D1). "Append-only" = has reject-mutation triggers (D4).

---

## Entity overview & relationships

```text
roles ─<user_roles>─ users          vendors        working_calendar   jobs
                        │ (actor)
stages ─1:1─ stage_sla  │
   │                    │
samples ─1:N─ sample_stage_events (append-only)
   │
audit_log (append-only, references actor = users.id)
```

- `users` N:M `roles` through `user_roles`.
- `stages` 1:1 `stage_sla` (SLA split out so SLA edits are audited distinctly from stage definition).
- `samples` 1:N `sample_stage_events`.
- `audit_log.actor_id` → `users.id` (the acting user or the `system` actor).
- `sample_stage_events.stage_id` → `stages.id`; `samples` optionally references a `vendors.id` when sent externally.

---

## Tables

### `roles`  (restricted; tracked)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | uuid | PK | |
| slug | text | UNIQUE NOT NULL, CHECK in the 5 known slugs | `admin`/`genomics`/`trf`/`molecular`/`bioinformatics` |
| description | text | | |

### `users`  (restricted; tracked)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | uuid | PK | |
| email | citext | UNIQUE, NULL for system actor | Login identity (credential columns added in M2) |
| display_name | text | NOT NULL | |
| is_system | boolean | NOT NULL DEFAULT false | Exactly one system actor seeded |
| is_active | boolean | NOT NULL DEFAULT true | |
| Partial unique index | | `UNIQUE (is_system) WHERE is_system` | Guarantees at most one system actor |

Note: password hash / auth columns are **out of scope** here (Spec 2 / M2). No human admin row is seeded (FR-012).

### `user_roles`  (restricted; tracked)
| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| user_id | uuid | FK→users(id) ON DELETE CASCADE, NOT NULL |
| role_id | uuid | FK→roles(id), NOT NULL |
| UNIQUE (user_id, role_id) | | prevents duplicate assignment |

### `stages`  (operational; tracked)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | uuid | PK | |
| position | smallint | UNIQUE NOT NULL, CHECK 1..8 | Fixed order (FR-005) |
| slug | text | UNIQUE NOT NULL | e.g. `data_generation` |
| name | text | NOT NULL | Human label |

### `stage_sla`  (operational; tracked)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | uuid | PK | |
| stage_id | uuid | FK→stages(id) UNIQUE NOT NULL | 1:1 with stage |
| sla_days | integer | NOT NULL CHECK >= 0 | Admin-editable (FR-006) |
| updated_at | timestamptz | NOT NULL DEFAULT now() | |

Seed defaults sum to 18 (D7). Editing `sla_days` does not alter historical `sample_stage_events.duration_hours` (FR-006).

### `samples`  (operational; tracked)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | uuid | PK | |
| case_id | text | UNIQUE NOT NULL | Pseudonymous external case identifier (FR-009); duplicates rejected |
| external_ref | text | NULL | Single optional minimal field; no name/MRN (D6) |
| current_stage_id | uuid | FK→stages(id) NOT NULL | Convenience pointer; history is authoritative |
| vendor_id | uuid | FK→vendors(id) NULL | Set when sent to an external lab |
| received_at | timestamptz | NOT NULL DEFAULT now() | Start of internal TAT clock |
| status | text | NOT NULL DEFAULT 'active', CHECK in (active, on_hold, closed) | Lifecycle flag; gate logic is Spec 2 |

### `sample_stage_events`  (operational; **append-only**; tracked-on-insert)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | uuid | PK | |
| sample_id | uuid | FK→samples(id) NOT NULL | |
| stage_id | uuid | FK→stages(id) NOT NULL | Stage reached |
| entered_at | timestamptz | NOT NULL DEFAULT now() | |
| duration_hours | numeric(10,2) | NULL | Time since prior event; set at insert, never updated |
| actor_id | uuid | FK→users(id) NOT NULL | Who advanced it (or system actor) |
| note | text | NULL | |

UPDATE/DELETE rejected by trigger (FR-003). Insert is audited; the row itself is immutable.

### `audit_log`  (restricted; **append-only**; self-written by triggers)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | uuid | PK | |
| actor_id | uuid | FK→users(id) NOT NULL | From `app.user_id`; the system actor for jobs |
| job_id | uuid | FK→jobs(id) NULL | From `app.job_id` when an automated job (FR-004) |
| action | text | NOT NULL CHECK in (INSERT, UPDATE, DELETE) | |
| entity_table | text | NOT NULL | Source table name |
| entity_id | uuid | NOT NULL | Changed row's id |
| before | jsonb | NULL | Null on INSERT |
| after | jsonb | NULL | Null on DELETE |
| at | timestamptz | NOT NULL DEFAULT now() | |

UPDATE/DELETE rejected by trigger (FR-003). Index on `(entity_table, entity_id)` and `(at)`.

### `vendors`  (operational; tracked)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | uuid | PK | |
| name | text | UNIQUE NOT NULL | |
| tat_days | integer | NOT NULL CHECK >= 0 | |
| tat_anchor | text | NOT NULL CHECK in (receipt, sequencing) | Centogene = sequencing (D8) |
| is_active | boolean | NOT NULL DEFAULT true | |

### `working_calendar`  (operational; tracked)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | uuid | PK | |
| weekend_days | smallint[] | NOT NULL | ISO weekday numbers treated as non-working (default `{5}` = Friday, the Medlabs work week; admin-editable) |
| singleton guard | | `UNIQUE ((true))` or a fixed id | Exactly one active calendar config |

### `holidays`  (operational; tracked)  — companion to the calendar
| Column | Type | Constraints |
|---|---|---|
| id | uuid | PK |
| day | date | UNIQUE NOT NULL |
| label | text | NULL |

Seeded empty (D7); admin adds entries. (Split from `working_calendar` so individual holiday changes audit cleanly.)

### `jobs`  (operational; tracked)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | uuid | PK | |
| kind | text | NOT NULL | e.g. `portal_push` (used by Spec 2+ workers) |
| status | text | NOT NULL DEFAULT 'queued', CHECK in (queued, running, succeeded, failed) | |
| payload | jsonb | NOT NULL DEFAULT '{}' | |
| attempts | integer | NOT NULL DEFAULT 0 | |
| last_error | text | NULL | |
| run_after | timestamptz | NOT NULL DEFAULT now() | Backoff/scheduling |
| locked_at | timestamptz | NULL | Worker lease; survives restart (Article VIII.6) |
| updated_at | timestamptz | NOT NULL DEFAULT now() | |

---

## Triggers (summary — full DDL in implementation)

1. **Generic audit** (`fn_audit()`): `AFTER INSERT/UPDATE/DELETE FOR EACH ROW` on every tracked table → inserts an `audit_log` row with `actor_id = current_setting('app.user_id')::uuid`, `job_id = nullif(current_setting('app.job_id', true),'')::uuid`, `before = to_jsonb(OLD)`, `after = to_jsonb(NEW)`. Raises if `app.user_id` is unset on a write (no un-attributed changes). Declared `SECURITY DEFINER` with a fixed `search_path`, owned by the migration/superuser (BYPASSRLS) role so its insert into `audit_log` succeeds under `FORCE ROW LEVEL SECURITY` while `helixa_app` holds no INSERT right on that table.
2. **Append-only guards** (`fn_reject_mutation()`): `BEFORE UPDATE OR DELETE` on `audit_log` and `sample_stage_events` → `RAISE EXCEPTION`.
3. **Stage-event duration** (optional helper): on insert, compute `duration_hours` from the sample's prior event; may also be set by the backend. Does not mutate past rows.

## Row-Level Security (summary — full policies in implementation)

- `ENABLE` + `FORCE ROW LEVEL SECURITY` on all tables listed below.
- Helper: `app_roles()` = `string_to_array(current_setting('app.role_names', true), ',')`; `is_admin()` = `'admin' = ANY(app_roles())`; `has_identity()` = `current_setting('app.user_id', true) IS NOT NULL AND <> ''`.
- **Restricted tables** (`users`, `roles`, `user_roles`, `audit_log`): `USING (is_admin())` for SELECT; writes to `users`/`roles`/`user_roles` require `is_admin()`; `audit_log` has no INSERT policy for `helixa_app` and `helixa_app` is not granted INSERT on it. Rows reach `audit_log` only via the `fn_audit()` trigger, which is `SECURITY DEFINER` owned by the migration/superuser (BYPASSRLS) role — that ownership is what lets the insert succeed under `FORCE ROW LEVEL SECURITY`. UPDATE/DELETE are trigger-blocked for everyone.
- **Operational tables** (`samples`, `sample_stage_events`, `stages`, `stage_sla`, `vendors`, `working_calendar`, `holidays`, `jobs`): SELECT `USING (has_identity())` (any of the five roles); write policies `WITH CHECK (has_identity())` — fine-grained write gating is Spec 2's backend logic.
- **Deny by default**: with no `app.user_id` set, `has_identity()` and `is_admin()` are false → zero rows (FR-015).

## Validation rules traced to requirements

| Rule | Source |
|---|---|
| `samples.case_id` UNIQUE, pseudonymous, no PII columns | FR-009, SC-007, D6 |
| 8 stages, `position` 1..8 UNIQUE, ordered | FR-005 |
| `stage_sla.sla_days` editable; history durations immutable | FR-006 |
| `audit_log` written same-tx for every tracked change; actor required | FR-001, FR-002 |
| `audit_log` / `sample_stage_events` UPDATE/DELETE rejected for all roles | FR-003, SC-002 |
| `job_id`/system actor on automated changes | FR-004 |
| Restricted vs operational RLS tiers | FR-014, FR-015 |
| Seed: 5 roles, 8 stages+SLA, 4 named vendors, system actor, calendar; no human admin | FR-011, FR-012, SC-003 |
| Reproducible from migrations; jobs present; sequencing tables deferred | FR-016, FR-018, SC-005 |
