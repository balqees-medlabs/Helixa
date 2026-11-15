# Contract: Schema Overview & Seed

**Feature**: 001-database-foundation · Traces: FR-005..FR-013, FR-016..FR-018, SC-003, SC-005.

The authoritative column-level definitions live in [../data-model.md](../data-model.md). This contract fixes the parts downstream specs and operators depend on.

## Tables delivered by migration `0001`

Restricted (admin-only reads): `users`, `roles`, `user_roles`, `audit_log`.
Operational (all roles read): `samples`, `sample_stage_events`, `stages`, `stage_sla`, `vendors`, `working_calendar`, `holidays`, `jobs`.

Reserved for later migrations (NOT created here): `sequencing_runs`, `run_samples` → migration `0002` (Spec 4). Auth/credential columns on `users` → Spec 2 / M2.

## Seed delivered by migration `0001`

| Set | Values |
|---|---|
| Roles (5) | `admin`, `genomics`, `trf`, `molecular`, `bioinformatics` |
| Stages (8, ordered) + default SLA days | 1 received `1` · 2 consent & documentation `2` · 3 molecular processing `4` · 4 data generation `4` · 5 TRF preparation `2` · 6 TRF confirmation `1` · 7 data conversion & QC `2` · 8 report upload/archive/portal push `2` (Σ=18) |
| Vendors (4) | Arcensus `4d`/receipt · Reviity `28d`/receipt · Sefdecode `5d`/receipt · Centogene `30d`/**sequencing** |
| System actor | one `users` row, `is_system=true`, no credentials |
| Working calendar | one row, `weekend_days = {5}` (Friday), no holidays |
| Human admin | **none** — created in M2 |

## Stable identifiers downstream code may rely on

- Role slugs and stage slugs are stable natural keys (don't rename without a migration).
- Vendor `tat_anchor` ∈ {`receipt`,`sequencing`} is how the backend picks each vendor's TAT clock.
- Exactly one `users` row with `is_system = true`.

## Reproducibility

- `alembic upgrade head` on an empty database yields the full schema + seed in one command (SC-005), no manual steps.
- `alembic downgrade base` cleanly removes everything this feature added.
