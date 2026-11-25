# Contract: API Endpoints

**Feature**: 004-ngs-data-pipeline · Traces FR-001..FR-023. All paths are backend routes (served under `/api` same-origin). Human endpoints use the existing cookie+JWT; reporting endpoints use the `pipeline-reporter` token (see [reporter-auth.md](./reporter-auth.md)). Every mutation is audited; RBAC `403`, validation `422`, optimistic-concurrency `409`, not-found `404`, unauth `401`. The OpenAPI export is the source of truth (Article VIII.4); shapes below are the intent.

## Run & sample intake (role: molecular, admin)

- `POST /runs` — create a sequencing run `{run_folder, instrument, project?, run_side?, run_date?, storage_location?, cycle_r1?, cycle_r2?, cycle_i1?, cycle_i2?}` → `201 Run`. Duplicate `run_folder` → `409`.
- `GET /runs` — list runs (filter by instrument/readiness) → `200 Run[]`.
- `GET /runs/{run_id}` — run detail incl. readiness + cycle config → `200 Run`.
- `POST /runs/{run_id}/samples` — record a sample this run produces `{sample_id | case_ref, ngs_sample_id, sample_type, vendor_id, coverage_target_x?}` → `201 PipelineSample`. Refused `422` if no matching registered workflow Sample (D4); duplicate `ngs_sample_id` in run → `409`. `coverage_target_x` defaults 30 (G) / 15 (R) when omitted.
- `GET /samples/{sample_id}/pipeline` — full pipeline view for a sample: linked run(s), results (ingest/conversion/augmentation), coverage history, delivery → `200 PipelineSampleDetail`.
- `POST /samples/{sample_id}/merge-plan` — set intended source runs `{run_ids: uuid[]}` → `200` (role: molecular/bioinformatics/admin). Must be set before an augmentation result is accepted (D6).
- `GET /runs/export` — CSV export of the run/sample list (replaces the spreadsheet; FR-006).

## Pipeline results (identity: pipeline-reporter; admin may read)

- `POST /samples/{sample_id}/pipeline-results` — `{kind: "ingest"|"conversion"|"augmentation", status, read_length?, q30?, reads_assigned_pct?, source_run_ids?, integrity_ok?, detail?, idempotency_key}` → `201 PipelineResult` (or `200` on idempotent repeat, D7).
  - `ingest`/`ok` drives **Stage 4** for a sample at Stage 3 (held otherwise — see [stage-driving.md](./stage-driving.md)).
  - `augmentation` is validated against the merge plan and **always recorded** (append-only). A set matching the plan → `plan_match=true`; a mismatch → `plan_match=false`, the sample is held **not-ready for QC**, and the mismatch is surfaced on the result (still `201`, not a `422` — the record is kept for audit; a corrected run is a new result row). A reporter-side validation error (malformed body, unknown sample) is still `422`.
- `POST /samples/{sample_id}/coverage` — `{read_pairs, yield_gb, depth_x, target_x, idempotency_key}` → `201 CoverageResult`; `verdict` is derived (`pass` iff `depth_x >= target_x`). A `pass` **with** a prior `conversion`/`ok` drives **Stage 7**. Append-only; latest governs the gate.

## Vendor delivery (identity: pipeline-reporter; molecular/bioinformatics/admin read)

- `GET /samples/{sample_id}/delivery-clearance` — the reporter's pre-send check: `200 {cleared: boolean, latest_verdict, vendor_id}` (readable by the reporter under its scoped SELECT). The hard gate is still enforced on the POST below; this read just lets the uploader avoid sending a not-yet-cleared sample (FR-022).
- `POST /samples/{sample_id}/deliveries` — open/record a delivery `{vendor_id, destination_kind?}` → `201 Delivery`. Refused `409` if latest coverage verdict ≠ `pass` (FR-020) — the authoritative gate regardless of the clearance read.
- `PATCH /deliveries/{delivery_id}` — update status/verification `{status?, verification_state?, completion_marker?, evidence?}` → `200 Delivery`. Cannot be set `delivered` until the vendor profile's verification rule is satisfied (FR-018/019) → `422` otherwise.
- `GET /samples/{sample_id}/deliveries` → `200 Delivery[]`.

## Vendor delivery profile (role: admin)

- `PATCH /vendors/{vendor_id}` — extend existing endpoint to also set `{delivery_kind, endpoint_ref, naming_pattern, md5_required, verification_method}` (non-secret). No credentials accepted or stored (FR-021).

## Returned company report (role: bioinformatics, admin) — reuses Spec 2

- `POST /samples/{sample_id}/report` — existing endpoint; attaching a returned report stores it under `/data/reports` and queues the existing portal push (FR-023, Article VI.1–4). No new contract — reused as-is, available once the sample is delivered.

## Machine token admin (role: admin)

- `POST /api-tokens` `{name, role: "pipeline-reporter"}` → `201 {id, token}` (token shown **once**). `GET /api-tokens` → metadata only. `DELETE /api-tokens/{id}` → revoke (immediate; FR-024).
