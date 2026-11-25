# Feature Specification: NGS Data-Generation & Delivery Pipeline Tracking

**Feature Branch**: `spec/4-ngs-data-pipeline`

**Created**: 2026-11-24

**Status**: Draft

**Input**: User description: NGS data-generation & delivery pipeline tracking — make Helixa the source of truth for sequencing runs, per-sample pipeline progress (ingest → FASTQ conversion → augmentation → QC/coverage → vendor delivery), drive the two sequencing workflow stages per Article V.3 (basecalls present → Stage 4; FASTQ conversion + QC pass → Stage 7) from reported pipeline milestones, and connect the companies' returned reports to the existing report/portal flow.

## Overview

Today the NGS data-generation pipeline lives entirely in lab shell scripts on a pipeline host with NAS shares, and its outcome enters Helixa only as a manual entry around the sequencing stages (Stage 4 data generation and Stage 7 data conversion & QC) of the 8-stage sample workflow. This feature makes **Helixa the single source of truth** for what is being sequenced and how far each sample has progressed, so lab staff stop tracking it in a shared spreadsheet and the stage advances stop being a manual guess.

Helixa **records and tracks** the pipeline; it does **not** run the heavy compute and does **not** perform the vendor uploads. The existing lab scripts keep performing ingest readiness checks, `bases2fastq` conversion, augmentation, coverage calculation, and the vendor uploads on the pipeline host, and report their results into Helixa. Helixa stores sequencing runs, per-sample results, QC/coverage verdicts, and vendor-delivery status, and uses the reported milestones to drive the two sequencing stage gates per Article V.3 (basecalls present → Stage 4; FASTQ conversion + QC pass → Stage 7) in the workflow built in Specs 1–3.

## Clarifications

### Session 2026-11-25

- Q: Does Helixa itself perform/drive the vendor uploads, or do lab components perform them and report in? → A: **Tracking only.** The lab components perform all three uploads (Arcensus S3, SelfDecode S3, Revvity sFTP — each from wherever it can reach, Revvity from the lab network) and report delivery + verification into Helixa. Helixa holds **no** vendor credentials, drives no transfers, and reads no FASTQ files; its deployment stays unconstrained. Helixa remains the authority on which samples are cleared for delivery (PASS-gated), and the upload component checks that with Helixa before sending. *(Revised 2026-11-25: reversed from an earlier "Helixa drives all uploads" answer — reusing the lab's proven resumable upload scripts and keeping vendor secrets out of the app.)*
- Q: How do the unattended lab scripts authenticate to Helixa to report results? → A: A dedicated non-human service identity ("pipeline-reporter") with a role scoped to posting pipeline results only, authenticating with a long-lived **revocable API token** held in the pipeline host's secret store; every post is audited as that identity. This adds a token-based auth path for machine callers alongside the existing human cookie+JWT login.
- Q: Does run intake create the workflow Sample or link to an existing one? → A: Link to an **existing** workflow Sample (one registered in the 8-stage process); intake attaches sequencing attributes to it and refuses with a clear reason if the sample is not yet registered. Pipeline data is stage-4 activity on an existing sample — it never creates a parallel sample or bypasses earlier gates (consent).
- Q: Where do each vendor's delivery rules live? → A: Extend the existing Vendor with a **delivery profile** (destination kind S3/sFTP, non-secret endpoint references, naming pattern, md5-required flag, verification method). Delivery is data-driven per vendor — a new or retargeted vendor is additive configuration, not code — and the three current destinations are just three configured profiles.
- Q: Must the merge plan be recorded before an augmentation result is accepted? → A: Yes — required and validated. Molecular (at intake) or Bioinformatics records which source runs feed each sample before augmentation; a reported augmentation whose source runs do not match the recorded plan is flagged as a mismatch and not accepted as a clean augmentation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Molecular records a sequencing run and its samples (Priority: P1)

When preparing an experiment run, a Molecular team member records the run and the samples it will produce directly in Helixa — sample identifiers, patient/order reference, sample type (clinical **G** vs lifestyle **R**), the assigned delivery vendor, and the coverage target — instead of filling the shared "NGS Sample Tracking Sheet" spreadsheet. Helixa becomes the authoritative list of what is being sequenced.

**Why this priority**: Nothing downstream (conversion, QC, delivery, the stage-4 advance) can be tracked until Helixa knows the run and its samples exist. This is the foundational slice and an immediate win (the spreadsheet is retired).

**Independent Test**: A Molecular user creates a run with several samples (mixed G and R types, each with a vendor and a target), saves it, and sees the run with its samples listed and attributed to them — with no pipeline results yet. Delivers value on its own as the replacement for the spreadsheet.

**Acceptance Scenarios**:

1. **Given** a signed-in Molecular user, **When** they create a run with its instrument/project identity and add samples (each with type, vendor, and coverage target), **Then** the run and samples are persisted, visible, and attributed to that user with a timestamp.
2. **Given** a sample typed clinical (G), **When** no coverage target is entered, **Then** the system defaults it to the clinical target (30×); a lifestyle (R) sample defaults to 15×.
3. **Given** a run already recorded, **When** a user attempts to add a sample with a duplicate sample identifier within that run, **Then** the system rejects it with a clear reason.
4. **Given** a user without the Molecular (or admin) role, **When** they attempt to create a run or add samples, **Then** the action is refused.

---

### User Story 2 - Sequencing milestones drive the workflow stages (Priority: P2)

Per the constitution's stage mapping (Article V.3), two sequencing milestones drive two workflow stages: **basecalls present** for a sample's run completes **Stage 4 (data generation)**, and **successful FASTQ conversion plus a coverage/QC PASS** completes **Stage 7 (data conversion & QC)**. A coverage result records read-pairs, yield, estimated depth, and the target it was measured against, producing a verdict of **PASS** or **BELOW**. A PASS (with conversion done) satisfies the Stage 7 gate so the sample can advance; a BELOW result flags the sample for top-up or re-sequencing and does **not** let it proceed to delivery. Automation never advances a stage out of order — a ready milestone is held until the sample has reached the preceding stage.

**Why this priority**: This is the core integration payoff — sequencing outcomes stop being manual entries and become the gates that move the sample forward, exactly as the constitution prescribes. It is the reason the feature exists.

**Independent Test**: Report basecalls-present for a sample at Stage 3 and confirm Stage 4 completes; then record conversion done + a coverage result at or above target and confirm the Stage 7 gate is satisfied and the workflow can advance; record one below target for another sample and confirm it is flagged and blocked from delivery.

**Acceptance Scenarios**:

1. **Given** a sample that has reached Stage 3, **When** its run's basecalls are reported present, **Then** Stage 4 (data generation) completes; if the sample has not yet reached Stage 3, the ready result is held, not advanced out of order.
2. **Given** a sample at a target of 30× with FASTQ conversion reported done, **When** a coverage result of 32× is recorded, **Then** the verdict is PASS and the Stage 7 (data conversion & QC) gate is satisfied.
3. **Given** a sample with a target of 30×, **When** a coverage result of 24× is recorded, **Then** the verdict is BELOW, the sample is flagged for top-up/re-sequencing, and it cannot advance to delivery.
4. **Given** a recorded coverage result, **When** anyone views the sample, **Then** read-pairs, yield, estimated depth, target, and verdict are shown and are immutable as a historical record (a correction is a new result, not an edit).
5. **Given** a sample still BELOW target, **When** an additional top-up result raises it to or above target, **Then** a new PASS verdict is recorded and the Stage 7 gate is satisfied.

---

### User Story 3 - Pipeline progress is visible per run and sample (Priority: P3)

Bioinformatics (and anyone with visibility) can see how far each run and sample has progressed through the pipeline — ingest readiness, FASTQ conversion, and augmentation — with the key facts captured at each step, so the team knows what is done, in progress, or stuck without reading host logs.

**Why this priority**: Operational visibility. Valuable but not required for the stage-4 gate (US2) to function; the verdict can be recorded even if intermediate steps are summarized.

**Independent Test**: For a run, record ingest readiness, then a conversion result (per-sample FASTQ present, Q30, reads-assigned%), then an augmentation result (which source runs were merged, integrity checks passed), and confirm each step and its facts are visible in order.

**Acceptance Scenarios**:

1. **Given** a recorded run, **When** ingest readiness is reported (required markers present, basecall/filter/location populated, cycle configuration), **Then** the run shows as ready with its cycle configuration.
2. **Given** a ready run, **When** a conversion result is reported for a sample, **Then** the sample shows FASTQ present with its read length, Q30, and reads-assigned percentage.
3. **Given** converted samples, **When** an augmentation result is reported for a sample (the set of source runs merged and integrity results: archive integrity OK and matching R1/R2 read counts), **Then** the sample shows which runs were merged and that integrity passed.
4. **Given** an augmentation integrity check that failed (mismatched read counts or a bad archive), **When** it is reported, **Then** the sample is marked not-ready for QC and the failure is visible.

---

### User Story 4 - Vendor delivery is tracked to completion (Priority: P3)

Each PASS sample is delivered to the vendor assigned at intake — Arcensus (clinical S3), SelfDecode (lifestyle S3), or Revvity (routine clinical sFTP). Helixa tracks, per sample, the destination, the delivery status, the verification state (read back where the destination allows, receipt-confirmed where it does not), and the completion marker/receipt, so the team can prove a sample was delivered and verified.

**Why this priority**: Closes the outbound loop, but delivery can be tracked after the gate (US2) works. The *execution boundary* for the actual transfer is an open question (see Clarifications).

**Independent Test**: For a PASS sample assigned to each vendor type, record a delivery as completed with its verification state and completion marker, and confirm the sample shows delivered-and-verified; attempt to deliver a BELOW sample and confirm it is refused.

**Acceptance Scenarios**:

1. **Given** a PASS clinical sample assigned to a read-back-capable destination, **When** delivery is recorded, **Then** it is not marked delivered until read-back verification is recorded.
2. **Given** a PASS lifestyle sample assigned to a write-only destination, **When** delivery is recorded, **Then** it is marked delivered on vendor receipt confirmation (no read-back expected).
3. **Given** a PASS routine-clinical sample assigned to the checksum-required destination, **When** delivery is recorded without its required checksums and completion marker, **Then** it is not marked complete.
4. **Given** a sample whose coverage verdict is BELOW, **When** delivery is attempted, **Then** it is refused with a clear reason.
5. **Given** any delivery record, **When** viewed, **Then** no vendor credentials or secrets are stored or shown — only that a verified delivery occurred.

---

### User Story 5 - Returned company reports flow to the genomics portal (Priority: P4)

After a vendor returns a report for a delivered sample, the report is attached to the sample and pushed to the genomics portal, reusing the existing report storage and portal-push mechanism from Spec 2. This closes the end-to-end loop from run intake to a portal-delivered result.

**Why this priority**: The final handoff; depends on delivery (US4) and reuses existing report/portal machinery, so it is the last slice.

**Independent Test**: For a delivered sample, attach a returned report and confirm it is stored and queued to the portal exactly as the existing report flow does, with its push status visible.

**Acceptance Scenarios**:

1. **Given** a delivered sample, **When** a returned report is attached, **Then** it is stored and a portal push is queued using the existing report/portal flow.
2. **Given** a queued portal push, **When** it succeeds, **Then** the sample reflects report-delivered status consistent with the existing workflow close behavior.

---

### Edge Cases

- A run lands on a different NAS share than usual, or a sample's data is spread across multiple runs (side A + side B merges) — the record must represent "which runs fed this sample" without assuming a fixed storage location.
- A run is reported ready but later found incomplete (corrupt-tail run needing trimmed read length) — the recorded cycle/read-length facts must be able to differ per run (e.g., 2×150 vs a trimmed 2×123) and per sample after merging mixed lengths.
- The same coverage result is reported twice by a retrying script — recording must be idempotent (a repeat does not create a conflicting duplicate or a second gate advance).
- A delivery destination's firewall admits only the lab network (not Helixa's host) — Helixa does not perform the transfer, so it must represent a delivery performed by a lab component from a different location and still record its verification; an interrupted upload reported mid-way must not leave the sample marked delivered.
- A sample is re-sequenced after a BELOW verdict — the history must retain both the BELOW and the later PASS.
- A pipeline script loses connectivity mid-report — partial progress must not leave a sample in an inconsistent state.

## Requirements *(mandatory)*

### Functional Requirements

**Run & sample intake (US1)**

- **FR-001**: System MUST let a Molecular (or admin) user create a sequencing run with its identifying attributes (instrument, project, run-side/label, run date, and the run-folder name as reported by the instrument).
- **FR-002**: System MUST let that user record the samples a run will produce, each **linked to a Sample already registered in the 8-stage workflow**, and carrying an NGS sample identifier, an optional patient/order reference, a sample type (clinical **G** or lifestyle **R**), an assigned delivery vendor, and a coverage target. The system MUST refuse to record a run sample that does not correspond to an existing registered workflow Sample, with a clear "register the sample first" reason, and MUST NOT create a workflow Sample from run intake.
- **FR-003**: System MUST default the coverage target by type when not supplied (30× for clinical G, 15× for lifestyle R) and allow an explicit override.
- **FR-004**: System MUST reject a duplicate sample identifier within the same run with a clear reason.
- **FR-005**: System MUST attribute every run and sample record to the acting user with a timestamp, and MUST record all changes in the immutable audit trail.
- **FR-006**: System MUST become the source of truth for this information such that the external tracking spreadsheet is no longer required; an export of the run/sample list MUST be available for staff who still need a sheet.

**Pipeline progress (US3)**

- **FR-007**: System MUST record a run's ingest readiness (required completion markers present, basecall/filter/location populated) and its cycle configuration (per-read cycle counts); for a sample at Stage 3, basecalls-present on its run MUST complete **Stage 4 (data generation)** per Article V.3, holding the result rather than advancing out of order if the sample has not yet reached Stage 3.
- **FR-008**: System MUST record a per-sample FASTQ conversion result including conversion status, FASTQ presence, read length, and run quality statistics (at least Q30 and reads-assigned percentage).
- **FR-009**: System MUST record a per-sample augmentation result capturing the set of source runs merged into that sample and integrity results (archive integrity and matching R1/R2 read counts), and MUST validate those source runs against the sample's recorded merge plan — flagging a mismatch and not accepting it as a clean augmentation.
- **FR-010**: System MUST support per-run and per-sample read-length values that may differ (e.g., a trimmed run) and MUST tolerate samples merged from runs of mixed read length.
- **FR-011**: System MUST mark a sample as not-ready for QC when a required integrity check is reported as failed, and MUST make the failure visible.

**Coverage verdict & workflow gate (US2)**

- **FR-012**: System MUST record a per-sample coverage/QC result with read-pairs, estimated yield, estimated depth, the target it was measured against, and a verdict of PASS or BELOW derived from depth vs target.
- **FR-013**: System MUST treat successful FASTQ conversion **plus** a PASS coverage result as satisfying the existing **Stage 7 (data conversion & QC)** gate per Article V.3, so the sample can advance in the 8-stage workflow, without weakening any other existing gate and without advancing out of order.
- **FR-014**: System MUST prevent a sample whose latest verdict is BELOW from advancing to delivery and MUST flag it for top-up/re-sequencing.
- **FR-015**: System MUST keep every coverage result as an immutable historical record; a correction or a post-top-up re-measure is a new result, and the latest verdict governs the gate.
- **FR-016**: System MUST make coverage reporting idempotent so a retried report does not create a conflicting duplicate or a second stage advance.

**Vendor delivery (US4)**

- **FR-017**: System MUST carry each vendor's delivery rules as a **delivery profile on the vendor record** — destination kind (S3 / sFTP), non-secret endpoint references (region/bucket or host), file-naming pattern, md5-required flag, and verification method — so delivery behavior is data-driven and a new or retargeted vendor is additive configuration, not code. System MUST track, per sample, the assigned vendor, the delivery status, the verification state, and the completion marker/receipt.
- **FR-018**: System MUST apply the correct verification rule per destination: read-back verification where the destination can be read; vendor-receipt confirmation where it cannot (write-only); and required checksums plus a completion marker where the destination requires them.
- **FR-019**: System MUST NOT mark a delivery complete until its destination-appropriate verification is satisfied.
- **FR-020**: System MUST refuse delivery for a sample whose latest coverage verdict is not PASS.
- **FR-021**: System MUST NOT store, display, log, or transmit any vendor credential or secret; the lab components perform the uploads with their own credentials, and Helixa records only that a verified delivery occurred and its evidence (sizes/checksums/markers), never the keys used.
- **FR-022**: System MUST track a delivery that is performed by a lab component from a location other than Helixa (so a destination reachable only from a specific network can still be recorded and verified), and MUST expose a **read** of whether a sample is cleared for delivery (its latest coverage verdict is PASS) so that component can check before sending; opening a delivery is independently refused server-side when the sample is not cleared (the authoritative gate). Helixa itself performs no transfer and needs no outbound transfer capability or network placement.

**Returned reports (US5)**

- **FR-023**: System MUST let a returned company report be attached to a delivered sample and pushed to the genomics portal using the existing report storage and portal-push flow (Spec 2), with push status visible and consistent with existing workflow close behavior.

**Reporting interface & access (cross-cutting)**

- **FR-024**: System MUST accept pipeline results (ingest, conversion, augmentation, coverage, and delivery/verification) from a dedicated non-human **service identity** ("pipeline-reporter") whose role is scoped **only** to posting those results and nothing else. The identity MUST authenticate with a long-lived, individually **revocable API token** (distinct from the human cookie+JWT login), and every post MUST be audited as that identity under the existing immutable audit trail. Revoking the token MUST immediately stop further posts.
- **FR-025**: System MUST store large-file locations (run folders, FASTQ outputs) as references/paths and associated facts only — never the file contents — and MUST restrict run/sample/result visibility to the roles that own or oversee the workflow (molecular, bioinformatics, admin) under the existing row-level access rules.
- **FR-026**: System MUST let Molecular (at intake) or Bioinformatics record a sample's merge plan — the source runs intended to feed it — in Helixa **before** an augmentation result for that sample is accepted, so the reported merge can be validated against the intended plan (FR-009).

### Key Entities *(include if feature involves data)*

- **Sequencing Run**: a completed instrument run. Attributes: instrument, project, run-side/label, run date, run-folder name, storage location reference, ingest-readiness state, and cycle configuration (per-read cycle counts). Relates to the samples it produces and may be a source for augmented samples.
- **Pipeline Sample**: the sequenced sample as tracked by the pipeline; corresponds one-to-one to an existing workflow **Sample** so that the sequencing milestones can drive that sample's Stage 4 and Stage 7 gates. Attributes: NGS sample identifier, patient/order reference, type (G/R), assigned vendor, coverage target, current pipeline state. Relates to its run(s), its results, and its delivery.
- **Merge Plan / Run–Sample Assignment**: which source runs' data are intended to be merged into a given sample (e.g., side A + side B), used to validate augmentation.
- **Conversion Result**: per-sample FASTQ conversion outcome — status, FASTQ presence, read length, Q30, reads-assigned percentage.
- **Augmentation Result**: per-sample merge outcome — the source runs merged and integrity results (archive integrity, R1/R2 read-count match).
- **Coverage Result**: per-sample QC — read-pairs, yield, estimated depth, target, verdict (PASS/BELOW), timestamp; immutable; latest governs the gate.
- **Vendor Delivery**: per-sample delivery — destination type (read-back-capable S3 / write-only S3 / checksum-required sFTP), status, verification state, completion marker/receipt. No secrets.
- **Reuses/extends from Specs 1–2**: **Sample** (linked one-to-one to a pipeline sample), **Vendor** (extended with a non-secret **delivery profile**: destination kind, endpoint references, naming pattern, md5-required flag, verification method), **Report**, **Portal Push**, the **immutable audit trail**, and **row-level access** — extended, not replaced. A new non-human **pipeline-reporter** service identity (scoped role + revocable API token) posts pipeline results.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Molecular can record a full run with its samples (type, vendor, target each) in under 5 minutes, and the shared tracking spreadsheet is no longer the source of truth for any new run.
- **SC-002**: 100% of samples advance through the two sequencing stages (Stage 4 and Stage 7) based on reported pipeline milestones rather than a manual entry, and no sample with a latest BELOW verdict is ever delivered.
- **SC-003**: For any sample, a user can see its complete pipeline history (run(s), conversion, augmentation, every coverage result, delivery, verification) on one view without consulting host logs or the spreadsheet.
- **SC-004**: 100% of completed deliveries show a destination-appropriate verification (read-back, receipt, or checksum+marker) before being marked complete, and zero vendor credentials are present anywhere in Helixa (it holds none — the lab components upload with their own).
- **SC-005**: A retried pipeline report never produces a duplicate coverage result or a second stage advance (idempotent reporting verified).
- **SC-006**: A returned company report for a delivered sample reaches the genomics portal through the existing report/portal flow with visible push status.

## Assumptions

- **Intake is UI-first (decided)**: Molecular enters run/sample metadata directly in Helixa; importing the legacy spreadsheet is **not** required for v1 (an export out of Helixa is provided instead). The spreadsheet is retired as the source of truth.
- **Compute and delivery both stay external (decided)**: Helixa tracks/records; it does not run `bases2fastq`, augmentation, or coverage compute, and does not perform the vendor uploads. The lab pipeline performs all of those (uploads with its own proven resumable scripts, Revvity from the lab network) and reports results in. Helixa holds no vendor credentials, reads no FASTQ, and its deployment is unconstrained.
- **Sample identity bridges to the existing workflow (decided)**: a pipeline sample links one-to-one to an existing registered workflow Sample (Session 2026-11-25) so the sequencing milestones drive that sample's Stage 4 and Stage 7 gates; run intake never creates a workflow Sample and cannot bypass the earlier consent/accessioning gates.
- **Merge plan is entered in Helixa and validated (decided, FR-026/FR-009)**: whoever knows the merge plan (Molecular at intake or Bioinformatics before augmentation) records which runs feed each sample before augmentation is accepted; a reported augmentation that doesn't match is flagged as a mismatch.
- **Coverage model is a lab-provided estimate**: the depth estimate uses the lab's agreed coverage model and fragment/mappability/genome-size constants; Helixa stores the reported numbers and the verdict, and is not the authority on the biological model.
- **Storage-agnostic references**: run/output locations are stored as references that may point at any share; Helixa does not assume a fixed mount and does not access the files itself.
- **Constitution order holds**: delivered as DB migration `0003` → backend endpoints → frontend UI, on the fixed stack, honoring RBAC/RLS/immutable-audit and the existing workflow gates.
- **Roles**: Molecular owns intake; Bioinformatics owns pipeline/coverage/delivery results; Admin oversees. No new human role is introduced; a dedicated non-human **pipeline-reporter** service identity (scoped, token-authenticated — Session 2026-11-25) posts pipeline results.

## Dependencies

- The Spec 1 data foundation (identity, roles, audit trail, RLS, vendors, the 8-stage workflow and its progression history).
- The Spec 2 backend (auth/RBAC, the Stage 4 / Stage 7 stage gates, report storage, and the portal-push flow reused in US5).
- The Spec 3 frontend shell, role-bound navigation, and the existing sample/TAT views that the new run/pipeline screens extend.
