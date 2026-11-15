# Feature Specification: Database Foundation (Spec 1)

**Feature Branch**: `001-database-foundation`

**Created**: 2026-11-14

**Status**: Draft

**Input**: User description: "read and any setup before spec1 from this /home/labs/Helixa/docs/implementation-plan.md using the best practices for github speckit and create a spec for it"

## Overview

Helixa is Medlabs Genomics' internal system for managing next-generation-sequencing (NGS) samples from receipt to final report. This feature delivers the **data foundation**: the authoritative record of users and their roles, the 8-stage clinical workflow, every sample's progression through it, a tamper-proof audit trail, and the reference data the rest of the system depends on. It is the first of three layers (Database → Backend → Frontend) and the single source of truth for correctness and auditability. No workflow logic lives here — the data store only guarantees integrity; the backend (a later feature) enforces business rules on top of it.

## Clarifications

### Session 2026-11-14

- Q: For the row-level access layer, how much should operational roles read? → A: All operational roles (`genomics`, `trf`, `molecular`, `bioinformatics`) may read every sample; row restriction applies only to administrative data — user accounts, roles, and the audit log.
- Q: What patient-identifying information should a sample record store? → A: Pseudonymous case identifier plus minimal non-identifying workflow metadata; direct identifiers (name/MRN) are kept out of Helixa or confined to a single optional minimal field.
- Q: Which external vendors should the migration seed (4, incl. the one counted from sequencing)? → A: Arcensus (4-day TAT), Reviity (28-day / 4-week TAT), Sefdecode (5-day TAT), and Centogene (30-day TAT counted from sequencing).
- Q: What default SLA per stage should seed? → A: A distribution summing to the 18-day internal target — received 1, consent & documentation 2, molecular processing 4, data generation 4, TRF preparation 2, TRF confirmation 1, data conversion & QC 2, report upload/archive/portal push 2 — all admin-editable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tamper-proof clinical record (Priority: P1)

As the Genomics Department, every change to patient and workflow data must be recorded and impossible to alter or erase after the fact, so the lab can reconstruct exactly who did what and when and withstand clinical audit.

**Why this priority**: Auditability is the core clinical guarantee and a precondition for handling patient data at all. Without an immutable trail, nothing built on top can be trusted. This story alone — a schema that records changes and refuses to let history be rewritten — is the minimum viable foundation.

**Independent Test**: Load the data store, write some records and a few audit/history entries, then attempt to UPDATE and DELETE audit and stage-history rows while connected under each of the five roles (and as the owner/superuser's day-to-day role). Every such attempt is rejected; the rows are unchanged. Confirm a data change and its audit entry either both land or neither does (same transaction).

**Acceptance Scenarios**:

1. **Given** an existing audit entry, **When** any role attempts to modify or delete it, **Then** the operation is rejected and the entry is unchanged.
2. **Given** an existing sample stage-history entry, **When** any role attempts to modify or delete it, **Then** the operation is rejected and the entry is unchanged.
3. **Given** a change to a sample record, **When** the change is committed, **Then** a matching audit entry (actor, action, entity, before/after, timestamp) exists in the same committed transaction.
4. **Given** a change made by an automated process rather than a person, **When** the audit entry is written, **Then** it is attributed to the dedicated `system` actor.

---

### User Story 2 - Workflow model and sample progression (Priority: P2)

As the lab, samples must move through the 8 defined clinical stages, and the system must store each sample's history through those stages with the time spent at each, so turnaround can be measured and reported.

**Why this priority**: The workflow is the heart of the operation. Once history is immutable (P1), the stage model gives that history meaning and enables turnaround-time reporting. Delivered on its own it already lets the lab record and measure sample progress.

**Independent Test**: Confirm the 8 stages exist in the correct order with an editable SLA each; record a sample advancing through several stages; confirm each advance stored an event with its duration; confirm the working-day/holiday calendar used for turnaround is present and editable.

**Acceptance Scenarios**:

1. **Given** a freshly seeded data store, **When** the stages are listed, **Then** exactly the 8 ordered stages are present, each with a configurable SLA in days.
2. **Given** a sample, **When** it advances to a new stage, **Then** a stage-history event is recorded capturing the stage, timestamp, and duration since the prior stage.
3. **Given** an administrator changes a stage's SLA, **When** the change is saved, **Then** new events use the new SLA while previously recorded durations are unchanged.
4. **Given** the turnaround calendar, **When** it is read, **Then** it reflects the configured weekend rule and holiday list used to compute working-day baselines.

---

### User Story 3 - Role-based access as a second line of defense (Priority: P3)

As the department handling patient data, access to records must be bound to a user's role at the data-store level, independently of the application, so a single application bug cannot expose records a user should not see.

**Why this priority**: Defense in depth. The backend is the primary guard, but the constitution requires a second, independent enforcement layer in the data store. It builds on the user/role data this feature already defines.

**Independent Test**: Seed the five roles and assign a test user one operational role; with the acting identity set to that user, confirm reads of permitted rows succeed and reads of administrator-only rows (e.g., user accounts, roles, audit log) return nothing; confirm a user may hold more than one role.

**Acceptance Scenarios**:

1. **Given** the five roles are seeded, **When** roles are listed, **Then** `admin`, `genomics`, `trf`, `molecular`, and `bioinformatics` are all present.
2. **Given** a session whose acting identity is a `genomics` user, **When** it reads administrator-only records (user accounts, roles, audit log), **Then** no rows are returned, while reads of sample and workflow data succeed.
3. **Given** a user assigned two roles, **When** their roles are read, **Then** both roles are returned and the combined permissions apply.
4. **Given** a session acting as an `admin` user, **When** it reads any record, **Then** access is permitted.

---

### User Story 4 - Reference data and a reproducible, recoverable schema (Priority: P4)

As the maintainer, standing up or rebuilding the data store must produce a known-good starting state — roles, stages, vendors, the system actor, and a default calendar — reproducibly from versioned migrations, and a routine backup must be restorable, so the system can be deployed, recovered, and evolved safely.

**Why this priority**: Operational readiness. It turns the schema and rules from the earlier stories into something that can be deployed and recovered on the lab server, and sets up safe evolution of the schema over time.

**Independent Test**: From an empty data store, apply the migrations in one command and confirm the full schema and all seed data appear; confirm the human administrator account is *not* present (created by a later feature); produce a backup and restore it into a fresh copy, confirming the data matches.

**Acceptance Scenarios**:

1. **Given** an empty data store, **When** the migrations are applied, **Then** the complete schema plus seed data (5 roles, 8 stages with SLAs, 4 vendors, the `system` actor, a default calendar) are present.
2. **Given** a freshly seeded data store, **When** user accounts are inspected, **Then** only the `system` actor exists and no human administrator account is present.
3. **Given** a running data store, **When** the nightly backup runs, **Then** it produces an artifact that can be restored into a fresh copy with matching contents.
4. **Given** a later schema change, **When** it is delivered, **Then** it arrives as a new versioned migration rather than a manual edit, and the sequencing-ingestion tables are deferred to a follow-up migration.

### Edge Cases

- An automated job writes data with no human actor → the change is attributed to the `system` actor, never left blank (FR-004).
- An administrator shortens a stage's SLA after samples have progressed → durations already recorded for past events never change; only future measurement uses the new value.
- Two samples are registered with the same external case identifier → the data store rejects the duplicate so case linkage stays unambiguous.
- A role-scoped session queries a table it has no rights to → it receives no rows rather than an error that leaks the table's existence or contents.
- A change and its audit entry cannot both be written (e.g., failure mid-transaction) → neither is persisted; there are no un-audited changes and no orphan audit entries.
- The acting identity is not set on a session → the data store denies access to protected rows rather than defaulting to broad visibility.
- A long-running background task is interrupted and restarts → its queued work record survives so the task can resume (supports the later backend worker).

## Requirements *(mandatory)*

### Functional Requirements

**Audit & immutability**

- **FR-001**: The data store MUST record every create, update, and delete of a tracked entity as an audit entry capturing actor, action, entity, before state, after state, and timestamp.
- **FR-002**: The audit entry MUST be written in the same transaction as the change it describes, so a change and its audit record are never separated.
- **FR-003**: The audit trail and the sample stage-history MUST be append-only: modification and deletion MUST be rejected for every role, including administrators, enforced by the data store itself rather than by application code.
- **FR-004**: Changes not made by a person MUST be attributable to a dedicated non-login `system` actor, and the originating background-task reference MUST be recordable with the entry.

**Workflow model**

- **FR-005**: The data store MUST define the 8 ordered clinical stages: sample received; consent & documentation; molecular processing; data generation; TRF preparation; TRF confirmation; data conversion & QC; report upload/archive/portal push.
- **FR-006**: Each stage MUST carry a target SLA in days that an administrator can change, without altering durations already recorded for past events. The seeded defaults MUST sum to the 18-day internal target: received 1, consent & documentation 2, molecular processing 4, data generation 4, TRF preparation 2, TRF confirmation 1, data conversion & QC 2, report upload/archive/portal push 2.
- **FR-007**: The data store MUST record each sample's progression as stage-history events capturing the stage reached, the timestamp, and the duration since the prior stage.
- **FR-008**: The data store MUST hold a configurable turnaround calendar (weekend rule plus a holiday list) sufficient to compute both the 18-calendar-day internal target and the 45-working-day baseline.

**Samples & reference data**

- **FR-009**: The data store MUST store sample records keyed by a unique, pseudonymous external case identifier, rejecting duplicates so case linkage is unambiguous. Records MUST hold only non-identifying workflow metadata; direct patient identifiers (e.g., name, medical record number) MUST NOT be stored, except optionally in a single clearly marked minimal field, and never as the primary key.
- **FR-010**: The data store MUST store external vendors and track each vendor's turnaround separately from the internal workflow (e.g., a vendor whose turnaround is counted from sequencing rather than from receipt).
- **FR-011**: Seed data applied with the schema MUST include the 5 roles, the 8 stages with default SLAs (FR-006), the `system` actor, a default calendar, and these 4 vendors with their turnaround targets: Arcensus (4 days), Reviity (28 days), Sefdecode (5 days), and Centogene (30 days, counted from sequencing). All vendor records remain administrator-editable afterward.
- **FR-012**: The human administrator account MUST NOT be seeded here; it is created by a later feature. Only the `system` actor is present after seeding.

**Access control**

- **FR-013**: The data store MUST define the five roles — `admin`, `genomics`, `trf`, `molecular`, `bioinformatics` — and MUST allow a user to hold several roles, with `admin` permitted everything.
- **FR-014**: The data store MUST enforce role-based row access as an independent second layer beneath the backend's guards, deciding visibility from an acting user/roles identity supplied by the caller per transaction. The restricted (administrator-only) data is limited to user accounts, role definitions and assignments, and the audit log; all operational roles (`genomics`, `trf`, `molecular`, `bioinformatics`) MUST be able to read every sample and its workflow data.
- **FR-015**: When no acting identity is supplied, or the acting identity lacks rights to a restricted row, the data store MUST return no rows rather than exposing them.

**Durability & evolution**

- **FR-016**: The schema and seed data MUST be reproducible on an empty data store by applying versioned migrations, with no manual edits to a live schema.
- **FR-017**: A routine (nightly) backup MUST be produced and MUST be restorable into a fresh copy with matching contents.
- **FR-018**: The data store MUST provide a durable record of queued background work (so a later worker can process and resume it), and MUST reserve the sequencing-ingestion tables for a follow-up migration rather than this one.

### Key Entities *(include if feature involves data)*

- **User**: A person or the `system` actor who acts in Helixa. Flagged when it is the non-login system actor. Linked to one or more roles.
- **Role**: One of `admin`, `genomics`, `trf`, `molecular`, `bioinformatics`. Grants permissions; `admin` grants all.
- **User–Role assignment**: The many-to-many link letting a user hold several roles.
- **Stage**: One of the 8 ordered workflow steps, with an order position and an editable SLA in days.
- **Sample**: A patient NGS sample tracked through the workflow, identified by a unique, pseudonymous external case identifier. Holds non-identifying workflow metadata only; no direct patient identifiers beyond at most one optional minimal field.
- **Sample stage event**: An append-only record that a sample reached a stage, with timestamp and duration since the prior stage.
- **Audit entry**: An append-only record of a single data change — actor, action, entity, before/after, timestamp, and optional originating-job reference.
- **Vendor**: An external lab/service with its own turnaround tracked separately from the internal workflow.
- **Working calendar**: The weekend rule and holiday list used to compute working-day baselines and turnaround targets.
- **Job**: A durable record of queued background work, used later by the backend worker; survives restarts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of tracked data changes produce a matching audit entry committed in the same transaction; zero un-audited changes and zero orphan audit entries are observed in testing.
- **SC-002**: Across all five roles plus an administrator, zero attempts to modify or delete audit or stage-history records succeed.
- **SC-003**: After seeding, exactly the 8 stages (correctly ordered), 5 roles, the 4 named vendors (Arcensus, Reviity, Sefdecode, Centogene) with their turnaround targets, the `system` actor, and a default calendar are present, and no human administrator account exists.
- **SC-004**: In role-scoped access testing, zero rows outside a session's permitted scope are ever returned, including when no acting identity is set.
- **SC-005**: The complete schema and seed data can be reproduced from migrations on an empty data store in a single command, with no manual steps.
- **SC-006**: A backup taken by the routine job can be restored into a fresh copy whose contents match the source, verified at least once before this feature is accepted.
- **SC-007**: Registering a sample with a duplicate external case identifier is rejected 100% of the time.

## Assumptions

- **Environment (M0) is in place**: the lab server has the container runtime, a running PostgreSQL 16 instance bound to localhost, the `/data/{reports,runs,backups}` directories, and the reverse proxy — all prerequisites delivered before this feature, per the plan's M0 section.
- **The backend is the single writer and sets the acting identity**: role-based row access depends on the backend supplying the acting user and roles on each transaction. That backend is a later feature; this feature provides the access policies and the reference/user data they read, verified by simulating the acting identity.
- **Human administrator is created later**: per the plan, the first admin needs a securely hashed password and is created by a backend command in the next milestone (M2), not seeded here.
- **Vendor seed** (resolved, Clarifications 2026-11-14): the 4 seeded vendors are Arcensus (4-day TAT), Reviity (28-day TAT), Sefdecode (5-day TAT), and Centogene (30-day TAT counted from sequencing); all editable by administrators thereafter.
- **Default stage SLAs** (resolved, Clarifications 2026-11-14): seeded with the distribution in FR-006 that sums to the 18-day internal target; administrators adjust them in operation.
- **Administrator-only data** (resolved, Clarifications 2026-11-14): user accounts, roles/assignments, and the audit log are administrator-only; all operational roles can read every sample and its workflow data (FR-014).
- **Scope boundary**: sequencing-ingestion tables (`sequencing_runs`, `run_samples`) are deliberately out of scope here and arrive as a follow-up migration (Spec 4); report and sequencing *files* live on the filesystem, not in the data store — only their metadata does.
- **Minimal patient data at rest** (resolved, Clarifications 2026-11-14): samples are keyed by a pseudonymous case identifier and hold only non-identifying workflow metadata; direct identifiers are kept out (or confined to a single optional minimal field). Large artifacts (reports, FASTQs) are referenced, not stored inline.

## Dependencies

- Governed by the Helixa Constitution v2.0.0 — Article I (layer boundaries), Article III (security & access, RLS as second layer), Article IV (immutable auditability), Article V (workflow integrity), Article VIII (migrations, backups from the first data-bearing milestone).
- Prerequisite: M0 environment & scaffold (container runtime, PostgreSQL, data directories, backups location).
- Downstream: Spec 2 (Backend) is the single writer and sets the acting identity; Spec 4 (Sequencer ingestion) adds tables in a follow-up migration.
