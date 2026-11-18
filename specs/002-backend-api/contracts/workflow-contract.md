# Contract: Gated Workflow & Turnaround

**Feature**: 002-backend-api · Traces FR-008..FR-015, SC-004/005/009, research D4/D5.

## Advance (`POST /samples/{id}/advance`)
Request carries the client's observed `from_stage` (position). The service:
1. `404` if the sample is not visible (RLS) or not found.
2. `409` if `to = from + 1` does not hold for the requested target (no skips, FR-010).
3. `409` with a gate reason if the target's precondition is unmet:
   - → molecular processing: all required `consent_items` complete (FR-011).
   - → report/archive: a `qc_results(kind='qc', passed=true)` exists (FR-013).
4. Atomic guarded update `UPDATE samples SET current_stage_id=:to WHERE id=:id AND current_stage_id=:from`; **0 rows ⇒ `409` conflict** (someone advanced it first, FR-010a) — the client should refetch.
5. On success, a `sample_stage_events` row is written (duration auto-filled by the Spec 1 trigger) and audited.

## Registration & consent
- `POST /samples` → sample at stage 1 with a unique `case_id` (duplicate → `409`/`422`), pseudonymous (no PII beyond the optional `external_ref`).
- `POST /samples/{id}/consent` → set required/optional item completeness; completeness is the molecular gate.

## Batches
- `POST /batches/{id}/advance` applies the same single-step advance to each member independently; response is a per-member list of `{sample_id, result|conflict|gate_reason}`. One member's gate failure never blocks the others (FR-012).

## Turnaround (`GET /metrics/tat`)
- Internal TAT per sample = elapsed against the per-stage SLAs and the 18-day target, using the Spec 1 working calendar; vendor TAT counted by each vendor's `tat_anchor` (receipt vs sequencing), reported separately (FR-014/015).
- Changing a stage SLA (`PATCH /stages/{id}/sla`) affects only future measurement; recorded `sample_stage_events.duration_hours` are never altered (SC-005).

## Verification hooks
- advance past an unmet consent gate → 409 with reason; complete consent → advance succeeds; skip-a-stage → 409; two concurrent advances → exactly one 200, one 409, one event row; SLA edit leaves past durations unchanged.
