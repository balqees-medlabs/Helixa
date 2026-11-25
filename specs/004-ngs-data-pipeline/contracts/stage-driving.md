# Contract: Sequencing → Stage Driving (Article V.3)

**Feature**: 004-ngs-data-pipeline · Traces FR-007/013, US2. Governance: ADR `docs/decisions/0002-external-pipeline-reporting.md` (who runs the pipeline changes; the stage-driving outcomes below do not).

## The two mappings (fixed by the constitution)

| Reported milestone | Completes | Stage slug |
|---|---|---|
| Basecalls present for the sample's run (an `ingest`/`ok` pipeline result) | **Stage 4 — data generation** | `data_generation` (position 4) |
| Successful FASTQ `conversion`/`ok` **and** a coverage `pass` | **Stage 7 — data conversion & QC** | `data_conversion_qc` (position 7) |

Stages 5–6 (TRF preparation / confirmation) remain manual lab steps and are **not** driven by this feature.

## Rules

1. **In-order only (hold, don't skip).** A milestone advances the sample only from the immediately-preceding stage. If the sample has not yet reached it, the result is **recorded** but the advance is a no-op (the sample waits) — never an out-of-order jump and never an error (Article V.3).
2. **Server-side gate.** The advance is performed by the backend using the existing optimistic-concurrency update (`UPDATE samples SET current_stage_id=:to WHERE id=:id AND current_stage_id=:from`). A stale/duplicate report finds `rowcount=0` and does **not** double-advance (idempotent; FR-016).
3. **Stage 7 needs both signals.** A coverage `pass` alone does not complete Stage 7 unless a `conversion`/`ok` result exists for the sample; likewise conversion alone is insufficient. The backend checks both before advancing.
4. **BELOW blocks delivery.** When the latest coverage verdict is `below`, Stage 7 is not satisfied and no delivery may open (FR-014/020). A later top-up `pass` (new coverage row) then satisfies it.
5. **Audit + events.** Each advance writes a `sample_stage_events` row (append-only) with its duration and an `audit_log` entry, attributed to the posting service identity.

## Acceptance (mirrors spec US2)

- Sample at Stage 3 + `ingest`/`ok` → now at Stage 4. Same report for a sample at Stage 1 → recorded, still at Stage 1.
- Sample at Stage 6 with `conversion`/`ok` already recorded + coverage `pass` (≥ target) → now at Stage 7.
- Coverage `below` (< target) → verdict `below`, Stage 7 not satisfied, delivery refused.
- Duplicate coverage `pass` (same `idempotency_key`) → no second advance.
