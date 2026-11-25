# ADR 0002 — External pipeline runs ingestion/conversion/upload; Helixa tracks and drives stages

**Status**: Accepted (ratified 2026-11-25; Article VI.5 amended in constitution v2.1.0)
**Date**: 2026-11-25
**Feature**: 004-ngs-data-pipeline
**Constitution basis**: Article II.8 (written decision); amends Article VI.5; preserves Article V.3 outcomes.

## Context

Article VI.5 (and II.7) describe the backend downloading basecalls to `/data/runs` and converting them to FASTQ with `bases2fastq` behind an isolated, mockable module, with successful download driving Stage 4 and conversion driving Stage 7. In reality the Medlabs lab already operates a mature, resumable, firewall-aware pipeline on an 80-core host with NAS/cloud storage: `bases2fastq` conversion, FASTQ augmentation, coverage QC, and three vendor uploads (Arcensus S3, SelfDecode S3, Revvity sFTP). The `/speckit-clarify` session (2026-11-25) decided Helixa is **track/record only** for both compute and vendor uploads.

## Decision

- The **external lab pipeline performs** ingestion, `bases2fastq` conversion, augmentation, coverage, and all vendor uploads, and **reports results into Helixa** through the `pipeline-reporter` service identity (ADR 0001).
- **Helixa tracks** runs, per-sample pipeline results, coverage verdicts, and deliveries, and **drives the stage gates server-side** from reported milestones, exactly per Article V.3: basecalls present → Stage 4; FASTQ conversion + coverage pass → Stage 7. In-order only; ready results held.
- Helixa stores **references and facts only** (NAS/FASTQ paths, sizes, checksums, markers, verdicts), **no file contents**, and **no vendor credentials** (those stay on the lab host). Helixa needs no NAS mounts, no outbound transfer capability, and no lab-network placement.
- The "isolated, mockable module" requirement of VI.5 is satisfied by isolating the **reporting interface** (the ingestion/result intake) behind one backend module, rather than an in-backend conversion wrapper.

## Required constitution amendment (MINOR)

Amend Article VI.5 to describe the ingestion model as "the external pipeline converts and reports; the backend tracks and drives Stages 4 and 7 from reported results behind an isolated, mockable reporting module," replacing "the backend downloads and converts." Article V.3 stage outcomes are unchanged. To be applied by editing `.specify/memory/constitution.md` and re-running `/speckit-constitution`.

## Alternatives considered

- **Backend runs `bases2fastq` + uploads** (literal VI.5) — duplicates proven lab tooling, forces vendor secrets into Helixa and Helixa onto the lab network (Revvity firewall), and rebuilds resumable S3/sFTP. Rejected in clarify Q1.
- **Hybrid** (Helixa drives S3, scripts do Revvity) — worst of both: secrets + new transfer code *and* still needs the scripts. Rejected.

## Consequences

- Smaller security surface and unconstrained deployment for Helixa; reuse of the lab's battle-tested pipeline.
- A reporting-interface module + the stage-driving logic become the backend's responsibility; conversion/transfer code does not.
- The constitution must be amended for the plan to pass the Article VI gate at implement time.
