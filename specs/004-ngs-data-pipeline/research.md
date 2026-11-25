# Phase 0 Research: NGS Data-Generation & Delivery Pipeline Tracking

**Feature**: 004-ngs-data-pipeline · **Date**: 2026-11-25

All five clarifications were resolved in the `/speckit-clarify` session (see spec `## Clarifications`). This document records the resulting design decisions, the stack/integration patterns, and the two governance decisions the Constitution Check flagged.

---

## D1 — Execution boundary: Helixa tracks, the lab pipeline runs everything

**Decision**: Helixa records and drives; the lab's existing scripts perform all compute (`bases2fastq`, augmentation, coverage) **and** all three vendor uploads, reporting status + verification into Helixa. Helixa holds no vendor credentials, reads no FASTQ, and its deployment is unconstrained.

**Rationale**: The lab pipeline is proven, resumable, and firewall-aware; re-implementing transfer/conversion inside the backend duplicates it, enlarges the security surface (vendor secrets in-app), and would force Helixa onto the lab network (the Revvity sFTP firewall admits only `81.21.12.37`). Track-only preserves every constitution outcome — gated stage driving, status tracking, retryability, audit — while Helixa stays a pure authority/record system.

**Alternatives considered**: (a) Backend runs `bases2fastq` + uploads behind a mockable module (literal Article VI.5) — rejected: duplicates proven tooling, holds all vendor secrets, deployment cage. (b) Hybrid — Helixa drives the two S3 uploads, Revvity stays external — rejected: worst of both (secrets + new transfer code *and* still needs the scripts for Revvity). Governance impact captured as **D-02** below.

## D2 — Stage driving follows Article V.3 exactly

**Decision**: Two reported milestones drive two existing stages, in order, holding a ready result until the sample has reached the preceding stage:
- **basecalls present** for a sample's run → completes **Stage 4 (data generation)** (slug `data_generation`).
- **successful FASTQ conversion + coverage QC PASS** → completes **Stage 7 (data conversion & QC)** (slug `data_conversion_qc`).

Advancing reuses the existing optimistic-concurrency advance (`UPDATE … WHERE current_stage_id = :from`) so an out-of-order or stale report yields a 409 and no second advance.

**Rationale**: Article V.3 is explicit about this mapping; the earlier spec draft wrongly attached the coverage verdict to Stage 4. Honoring V.3 keeps the workflow authoritative and the sequencing stages correctly separated (generation vs conversion/QC). Stages 5–6 (TRF preparation/confirmation) remain the lab's manual steps between.

**Alternatives considered**: Driving a single stage from a combined "done" signal — rejected: collapses two distinct, individually-auditable milestones and contradicts V.3.

## D3 — Pipeline reporting: scoped service identity + revocable API token

**Decision**: A dedicated non-human user (`pipeline-reporter`) holds a new role whose only permission is posting pipeline results (ingest/conversion/augmentation/coverage/delivery). It authenticates with a long-lived, individually **revocable API token** presented as a bearer credential on the reporting endpoints; the token's hash (argon2) is stored in a new `api_tokens` table, never the token itself. Every post is audited as that identity (consistent with Article IV.2's automated-actor rule). Human cookie+JWT auth is unchanged for everyone else.

**Rationale**: Unattended scripts cannot do an interactive cookie login; a scoped, revocable machine credential gives least privilege, clean audit attribution, and a kill-switch (revoke → immediate stop). Captured as governance decision **D-01**.

**Alternatives considered**: reuse a bioinformatics human password (broad perms, bad attribution, human secret on a shared host); mTLS (heavier than needed). Both rejected in clarify Q2.

## D4 — Sample linkage: link to an existing workflow Sample (never create)

**Decision**: Run intake links each run sample one-to-one to a Sample already registered in the 8-stage workflow (matched by its identifier/case ref). If no such Sample exists, intake refuses with "register the sample first". Run intake never creates a workflow Sample, so it cannot bypass the earlier consent/accessioning gates.

**Rationale**: The physical sample is accessioned (received → consent → molecular processing) before Molecular prepares its sequencing run, so the Sample already exists; attaching pipeline data to it keeps one source of truth per sample. Matches clarify Q3.

**Alternatives considered**: create-at-intake (risks skipping consent, duplicate identities); hybrid link-or-create (same risk). Rejected.

## D5 — Vendor delivery profile on the existing `vendors` table

**Decision**: Extend `vendors` with a non-secret **delivery profile**: destination kind (`s3` | `sftp`), endpoint references (region/bucket or host — non-secret), object-naming pattern, `md5_required` flag, and verification method (`readback` | `receipt` | `checksum_marker`). The three current destinations become three configured rows; a new/retargeted vendor is additive config, not code. Credentials are never part of the profile.

**Rationale**: Data-driven delivery keeps the differing rules (Arcensus read-back, SelfDecode write-only receipt, Revvity checksum+marker) explicit and extensible. Matches clarify Q4.

**Alternatives considered**: hardcoding three vendors (new vendor needs code); a separate normalized profile table — viable but heavier than the lab's handful of vendors warrants; kept inline on `vendors`, revisit if profiles grow.

## D6 — Merge plan recorded before augmentation, then validated

**Decision**: Molecular (at intake) or Bioinformatics records which source runs feed each sample (the merge plan) before an augmentation result is accepted. A reported augmentation whose source-run set does not match the recorded plan is flagged as a mismatch and not accepted as a clean augmentation.

**Rationale**: Augmentation concatenates multiple runs per clinical WGS sample; validating the actual merge against the intended plan is a cheap integrity gate consistent with the lab's other safety gates (consent, coverage). Matches clarify Q5.

**Alternatives considered**: self-declared sources (no cross-check); optional/validate-when-present (weaker guarantee). Rejected in favor of required+validated.

## D7 — Idempotent reporting

**Decision**: Each reporting post carries a natural idempotency key (e.g., run + sample + result-kind + a reporter-supplied result id). A repeat with the same key returns the existing record without creating a duplicate or triggering a second stage advance. Coverage results are append-only history; the latest verdict governs the gate, and the stage advance is driven by the optimistic-concurrency update (D2) so a retry cannot double-advance.

**Rationale**: Lab scripts retry on disconnect (systemd-run, resumable state); reporting must be safe to repeat (spec FR-016, SC-005).

## D8 — Secrets & file handling

**Decision**: Helixa stores only references (NAS run folders, FASTQ paths) and facts (sizes, checksums, markers, verdicts) — never file contents and never vendor credentials. The pipeline-reporter token hash lives in `api_tokens`; all other secrets (lab-side S3/SSH keys) never reach Helixa. Returned company report files reuse the existing `/data/reports` storage + RBAC-served download (Article VI.4) and the existing portal push (Article VI.1–2).

**Rationale**: Constitution III.4 / VI.4; keeps the clinical data surface minimal.

## D9 — Scope boundary

**Decision**: This feature adds run/pipeline/delivery **tracking** and the two stage-gate drivers. It does **not** run compute or uploads (D1), does not add notifications, and does not change the existing 8-stage model or the portal client. TRF stages 5–6 remain manual lab steps unchanged.

---

## Governance decisions (to ratify before `/speckit-implement`)

- **D-01** — `docs/decisions/0001-service-identity-api-token.md`: adopt a scoped, revocable machine API-token auth path for non-human reporters (Article II.8 written decision; does not alter human auth).
- **D-02** — `docs/decisions/0002-external-pipeline-reporting.md`: ingestion/conversion/upload are performed by the external lab pipeline reporting into Helixa, rather than the backend running them (Article II.8 decision **plus** a MINOR amendment to Article VI.5 to describe the reporting interface instead of in-backend conversion). The stage-driving outcomes of V.3 are unchanged.
