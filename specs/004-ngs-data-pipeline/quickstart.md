# Quickstart: NGS Data-Generation & Delivery Pipeline Tracking

**Feature**: 004-ngs-data-pipeline · Validation guide proving the feature end-to-end. Scenarios map to the spec's Success Criteria (SC-001…SC-006). Shapes live in [contracts/](./contracts/) and [data-model.md](./data-model.md) — not repeated here.

## Prerequisites

- The Spec 1–3 stack running (Postgres 16, backend API + worker, frontend behind the same-origin proxy), as in `frontend/README.md` and `backend/README.md`.
- Migration `0003_ngs_pipeline.py` applied (`alembic upgrade head`) and the three vendors backfilled with delivery profiles.
- An admin account; a Molecular user and a Bioinformatics user; and a minted **pipeline-reporter** token (admin: `POST /api-tokens`).
- At least one **workflow Sample already registered** and advanced to Stage 3 (via the existing register + consent + advance flow) — run intake links to it (D4).

## Setup

```bash
# backend
cd backend && alembic upgrade head           # applies 0003
# mint a reporter token (admin session), note the one-time token value
#   POST /api/api-tokens {"name":"pipeline-reporter@lab","role":"pipeline-reporter"}
# frontend
cd ../frontend && npm run dev                 # proxy :3000 + Next :3001
```

## Scenario 1 — Run & sample intake replaces the spreadsheet (SC-001, US1)

1. As Molecular, open **Runs → New**, create a run (`run_folder`, instrument, cycle config).
2. Add a sample: pick the **already-registered** workflow Sample, set `ngs_sample_id`, type `G`, a vendor, leave target blank.
3. **Expect**: sample saved with `coverage_target_x=30` (G default); attributed to the Molecular user; visible in the run.
4. Add a sample whose workflow Sample is **not** registered → **expect** a clear "register the sample first" refusal.
5. `GET /api/runs/export` returns the run/sample CSV. **Pass** when no new run needs the spreadsheet.

## Scenario 2 — Sequencing milestones drive Stages 4 and 7 (SC-002/005, US2)

1. For a sample at **Stage 3**, POST an `ingest`/`ok` pipeline result (reporter token). **Expect**: sample now at **Stage 4**; a `sample_stage_events` row recorded.
2. POST the same `ingest` result again (same `idempotency_key`). **Expect**: no duplicate, no second advance (idempotent).
3. Advance the sample through Stages 5–6 (manual TRF steps) via the existing flow.
4. POST a `conversion`/`ok` result, then a coverage result with `depth_x ≥ target_x`. **Expect**: verdict `pass`, sample now at **Stage 7**.
5. For a second sample, POST coverage with `depth_x < target_x`. **Expect**: verdict `below`, Stage 7 **not** satisfied, flagged for top-up.
6. POST a token request to a non-reporting route → **expect** `403`; revoke the token, retry a result post → **expect** `401` (FR-024).

## Scenario 3 — Merge plan validated against augmentation (US3, D6)

1. Set a sample's merge plan: `POST /api/samples/{id}/merge-plan {run_ids:[A,B]}`.
2. POST an `augmentation` result with `source_run_ids=[A,B]`, `integrity_ok=true`. **Expect**: accepted, `plan_match=true`.
3. POST an `augmentation` result with `source_run_ids=[A,C]`. **Expect**: recorded with `plan_match=false`, sample held **not-ready for QC**, mismatch surfaced (not a `422`).

## Scenario 4 — Vendor delivery gated + verified, no secrets (SC-004, US4)

1. Try to open a delivery for a **BELOW** sample → **expect** `409` (PASS-gated).
2. For a PASS sample on a **read-back** vendor: open delivery, PATCH to `delivered` **without** `verification_state=readback_ok` → **expect** `422`; with it → **delivered**.
3. For a **write-only** vendor: `delivered` allowed on `receipt_confirmed` (no read-back).
4. For a **checksum+marker** vendor: `delivered` requires checksums + `completion_marker` present, else `422`.
5. Inspect the DB/audit/API responses/logs → **expect** zero vendor credentials anywhere (SC-004).

## Scenario 5 — Returned report reaches the portal (SC-006, US5)

1. For a delivered sample, attach a returned report via the existing `POST /api/samples/{id}/report`.
2. **Expect**: stored under `/data/reports`, an existing-flow portal push queued, push status visible, sample reflects report-delivered consistent with the existing close behavior.

## Regression guard

- `npm run check:contract` passes (OpenAPI regenerated and committed).
- `pytest tests/db tests/api` green, including the new RLS/append-only, stage-driving, idempotency, merge-plan, delivery-gate, and token-auth tests.
- Existing Spec 1–3 suites still green (no existing gate weakened).
