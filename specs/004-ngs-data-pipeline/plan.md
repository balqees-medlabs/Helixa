# Implementation Plan: NGS Data-Generation & Delivery Pipeline Tracking

**Branch**: `spec/4-ngs-data-pipeline` | **Date**: 2026-11-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-ngs-data-pipeline/spec.md`

## Summary

Make Helixa the source of truth for NGS sequencing runs and per-sample pipeline progress, and drive the two constitution-defined sequencing stage gates (Article V.3: basecalls present → **Stage 4 data generation**; FASTQ conversion + coverage QC pass → **Stage 7 data conversion & QC**) from results reported by the lab's existing pipeline. Helixa **tracks and records only** — the lab scripts keep running `bases2fastq`, augmentation, coverage, and the three vendor uploads (Arcensus S3, SelfDecode S3, Revvity sFTP) on the pipeline host and report status + verification into Helixa through a scoped, token-authenticated **pipeline-reporter** service identity. Molecular records a run and its samples in a new UI screen (linking each to an already-registered workflow Sample), the merge plan is recorded and validated against reported augmentation, and returned company reports reuse the Spec 2 report + portal-push flow. Helixa holds no vendor credentials and reads no FASTQ.

Delivered in constitution order within one cross-layer feature spec (Article VIII.5): **DB migration `0003`** → **backend endpoints/services** → **frontend screens**.

## Technical Context

**Language/Version**: Backend Python 3.13 (FastAPI); Frontend TypeScript / Next.js 14 (App Router).

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, psycopg 3, PyJWT, argon2-cffi (backend); Next 14, TanStack Query, Zod, openapi-typescript, Vitest + MSW + Testing Library, Playwright (frontend). No new runtime framework, DB, or queue introduced.

**Storage**: PostgreSQL 16 (`public` schema, Alembic-owned). New tables for runs, run–sample links / merge plan, per-stage pipeline results, coverage results, and vendor deliveries; the existing `vendors` table extended with a non-secret delivery profile. **File references only** — Helixa stores NAS/FASTQ paths and facts, never file contents, and never vendor secrets.

**Testing**: pytest against real PostgreSQL (schema + RBAC/RLS + the two new stage gates + idempotent reporting + merge-plan validation); Vitest + MSW + Testing Library and Playwright for the new frontend screens; `check:contract` drift guard against the regenerated OpenAPI.

**Target Platform**: Linux lab server, Docker; backend + worker + Postgres on the internal network behind the TLS reverse proxy. Deployment is **unconstrained** by this feature (track-only: Helixa needs no lab-network placement, NAS mounts, or outbound transfer).

**Project Type**: Web — cross-layer feature spec (`backend/` + `frontend/`, migration under `backend/alembic/`).

**Performance Goals**: Tracking-app scale; reporting endpoints respond well under a second. No large-file movement inside Helixa (the lab host owns transfer throughput).

**Constraints**: No vendor secrets anywhere in Helixa (DB/audit/responses/logs); append-only audit (Article IV); RLS as defense-in-depth (Article III.3); stage gates enforced server-side (Article V.2); stages advance in order, holding ready milestones (Article V.3); idempotent pipeline reporting.

**Scale/Scope**: Lab-scale — tens of runs and hundreds of samples per period; a handful of vendors; one pipeline-reporter identity.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Article | Status | Notes |
|---|---|---|
| I — Layer boundaries | ✅ Pass | DB owns new tables/constraints/RLS; backend owns all gate/validation logic and is sole writer; frontend only renders and calls the API. Deliverables split per layer. |
| II — Stack | ✅ Pass | Reuses the fixed stack. The two prior deviations are now ratified: (D-01) machine API-token auth is permitted by amended **Article II.4**; (D-02) external-pipeline reporting is permitted by amended **Article VI.5** (constitution v2.1.0). |
| III — Security & access | ✅ Pass | New endpoints JWT/role-guarded; pipeline-reporter gets a narrowly scoped role; RLS extended to new tables; no vendor secrets stored (exceeds III.4). |
| IV — Auditability | ✅ Pass | All new writes audited in-transaction; reporter posts attributed to the service identity (consistent with IV.2's `system`/automated-actor rule). Coverage/stage-event history append-only. |
| V — Workflow integrity | ✅ Pass | Stage driving follows V.3 exactly (basecalls → Stage 4; conversion + QC pass → Stage 7); in-order only, ready results held; gates server-side. |
| VI — Integrations | ✅ Pass | VI.1–2 portal flow reused as-is for returned reports. **Article VI.5 amended** (constitution v2.1.0) to the external-pipeline-reporting model (D-02), so this now conforms. |
| VII — Design | ✅ Pass | New screens follow Medlabs brand, sentence case, accessible contrast, RTL-safe; surfaced within the existing role dashboards (Molecular intake, Bioinformatics pipeline). |
| VIII — Quality & delivery | ✅ Pass | Alembic `0003`; pytest for the new gates/validation; OpenAPI regenerated and consumed by the typed client; spec/plan/tasks committed with code. Long-running work (portal push) already uses the `jobs` worker; no new queue. |

**Gate result**: PASS (all 8 articles). The two prior deviations were ratified on 2026-11-25: ADR 0001 + 0002 Accepted, and constitution amended to **v2.1.0** (Article II.4 machine auth; Article VI.5 external-pipeline reporting). No open governance items remain before `/speckit-implement`.

## Project Structure

### Documentation (this feature)

```text
specs/004-ngs-data-pipeline/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (endpoint + auth contracts)
├── checklists/
│   └── requirements.md  # from /speckit-specify + /speckit-clarify
└── tasks.md             # /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/
│   └── 0003_ngs_pipeline.py          # runs, run_sample_links, pipeline_results,
│                                     # coverage_results, vendor_deliveries;
│                                     # vendors delivery-profile columns; RLS + audit
│                                     # triggers; pipeline-reporter role + service user;
│                                     # api_tokens table
├── app/
│   ├── db/models.py                  # + SQLAlchemy mirrors for the new tables
│   ├── api/
│   │   ├── runs.py                   # run + sample intake, merge plan (molecular)
│   │   ├── pipeline.py               # ingest/conversion/augmentation/coverage result posts
│   │   ├── deliveries.py             # vendor delivery + verification tracking
│   │   └── (reports.py reused)       # returned-report attach → existing portal push
│   ├── services/
│   │   ├── runs_service.py           # intake + sample linkage + merge-plan rules
│   │   ├── pipeline_service.py       # result recording, idempotency, stage driving (V.3)
│   │   └── delivery_service.py       # PASS gate, per-profile verification rules
│   ├── core/
│   │   └── service_auth.py           # pipeline-reporter API-token verification (D-01)
│   └── schemas/                      # Pydantic request/response models
└── tests/
    ├── db/                           # new-table RLS, append-only, triggers
    └── api/                          # intake RBAC, stage driving, idempotency,
                                      # merge-plan validation, delivery gate, token auth

frontend/
├── app/(app)/
│   ├── runs/                         # run list + intake (molecular), run detail
│   └── samples/[id]/                 # pipeline + coverage + delivery panels (extend)
├── components/                       # RunIntakeForm, PipelineTimeline, CoveragePanel,
│                                     # DeliveryStatus, MergePlanEditor
├── lib/features/{runs,pipeline,deliveries}/   # typed TanStack Query hooks
└── tests/                            # MSW-backed unit tests + e2e journeys

docs/decisions/
├── 0001-service-identity-api-token.md    # D-01 (draft, needs ratification)
└── 0002-external-pipeline-reporting.md   # D-02 + Article VI.5 amendment (draft)
```

**Structure Decision**: Cross-layer feature spec under the existing monorepo layout (Article II.6). Each deliverable lives in its own layer's folder (Article I / VIII.5): schema in `backend/alembic` + `backend/app/db`, all logic in `backend/app`, presentation in `frontend/`. No new top-level projects.

## Complexity Tracking

> Justified deviations, each with an Article II.8 written decision (ADR under `docs/decisions/`). **Both ratified 2026-11-25** via constitution v2.1.0.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| **D-01 — Machine API-token auth** for the `pipeline-reporter` service identity (beyond the human cookie+JWT of Article II.4) | Unattended lab scripts cannot do an interactive cookie login; they need a long-lived, revocable, narrowly-scoped credential that is cleanly audited as a non-human actor. | Reusing a human account's password on the host (clarify Q2 Option B) grants broad permissions, muddies audit attribution, and embeds a human secret on a shared host. mTLS (Option C) is heavier to operate than the lab needs. |
| **D-02 — External pipeline runs ingestion/conversion and reports in** (vs the backend downloading + converting behind a mockable module, Articles II.7 / VI.5) | The lab already runs a battle-tested, resumable, firewall-aware pipeline (bases2fastq, augmentation, uploads) on an 80-core host with NAS/cloud topology. Re-implementing transfer/conversion inside the backend duplicates proven tooling and would force Helixa onto the lab network with vendor secrets and NAS access. | Having the backend run `bases2fastq` + the three uploads (the literal VI.5 model) was evaluated in clarify Q1 and rejected: it enlarges the security surface (vendor secrets in-app), constrains deployment (Revvity firewall), and rebuilds resumable S3/sFTP that already exists. Track-only preserves every constitution outcome (stage driving, status tracking, retryability, audit) while keeping Helixa a pure authority/record system. Implies a MINOR amendment to Article VI.5. |
