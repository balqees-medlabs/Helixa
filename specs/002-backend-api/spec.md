# Feature Specification: Backend API (Spec 2)

**Feature Branch**: `002-backend-api`

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "Spec 2 — the full backend layer (M2 auth/RBAC/audit, M3 workflow engine, M5 reports & portal push)."

## Overview

Helixa's backend is the single authority for every rule in the system: who may act, how samples move through the clinical workflow, what gets recorded, and when results leave the building. It is the only writer to the data store built in Spec 1, and the only source of truth the frontend (Spec 3) will consume. This feature delivers the whole backend layer — authenticated, role-bound access; the gated 8-stage sample workflow with turnaround tracking; and report delivery with push to the external Genomic Data Portal. It holds patient data, so it MUST be correct and auditable before it is fast: every state change is attributed and recorded, and no workflow step may be skipped.

This builds directly on Spec 1 (the schema, audit triggers, append-only history, and row-level security) and sets the per-transaction acting identity that those guarantees depend on. It excludes the user interface (Spec 3), email notifications (Spec 3.1), and sequencer ingestion (Spec 4).

## Clarifications

### Session 2026-11-15

- Q: What condition marks a case as closed? → A: Report stored **and** the portal push confirmed successful; the push is retryable, so a case stays open until delivery succeeds.
- Q: How should concurrent advances of the same sample be handled? → A: Optimistic concurrency — the stale second advance is rejected with a conflict telling the user to refresh; both attempts are audited.
- Q: Which operations apply to a whole batch? → A: Stage advance and assignment only; per-sample gates are still enforced individually and each sample's change is recorded separately.
- Q: How long is a signed-in session valid? → A: Short-lived access (~15 min) silently renewed by a rotating refresh token, with re-authentication required after extended inactivity (~12 h idle / 7 d absolute).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Authenticated, role-bound access (Priority: P1)

As the Genomics Department, staff sign in and every action they take is checked against their role and recorded, so patient data is reachable only by authorized people and the system can always say who did what.

**Why this priority**: Nothing else may exist without it. Authentication, role enforcement, and attribution are the preconditions for touching patient data at all, and they establish the acting identity that the audit trail and row-level security require. Delivered alone, this is a usable, secure foundation: accounts exist, people sign in, roles gate access, and the trail is complete.

**Independent Test**: Create an administrator, sign in to obtain a session, call an identity endpoint and get the correct user and roles; call a protected endpoint without a valid session and be refused; perform an action as one role that another role is not permitted and confirm it is allowed/denied correctly; confirm every create/update/delete produced an attributed audit record.

**Acceptance Scenarios**:

1. **Given** a valid account, **When** the user signs in with correct credentials, **Then** they receive an authenticated session and subsequent protected requests succeed.
2. **Given** no session or an invalid/expired one, **When** a protected endpoint is called, **Then** the request is refused and no data is returned or changed.
3. **Given** a signed-in user, **When** they request their own identity, **Then** the system returns their account and the roles they hold.
4. **Given** an action permitted only to administrators, **When** a non-administrator attempts it, **Then** it is denied; **When** an administrator attempts it, **Then** it succeeds.
5. **Given** any action that changes data, **When** it completes, **Then** an audit record attributes the change to the acting user in the same unit of work.
6. **Given** a first-run system with no people, **When** the administrator account is provisioned, **Then** an administrator can sign in and create further accounts and role assignments.

---

### User Story 2 - Gated sample workflow (Priority: P2)

As the lab, a sample is registered and moves through the 8 clinical stages in order, with the system refusing to skip required gates, so the clinical process is followed correctly regardless of what any client tries to do.

**Why this priority**: The gated workflow is the core clinical guarantee and the system's reason to exist. Once access is controlled (US1), this makes sample progression authoritative and correct. It delivers value on its own: samples can be registered and advanced with the rules enforced and the history recorded.

**Independent Test**: Register a sample; attempt to advance it past a gate whose precondition is unmet (e.g., advance to molecular processing before the consent checklist is complete) and be refused; satisfy the precondition and advance successfully; confirm each advance recorded a stage event with its duration and an audit record; confirm an advance that skips a stage is refused.

**Acceptance Scenarios**:

1. **Given** a new sample, **When** it is registered, **Then** it exists at the first stage with its intake details recorded.
2. **Given** a sample whose consent checklist is incomplete, **When** an advance to molecular processing is attempted, **Then** it is refused with a reason; **When** the checklist is complete, **Then** the advance succeeds.
3. **Given** a sample at a stage, **When** an advance that skips an intermediate stage is attempted, **Then** it is refused.
4. **Given** a successful stage advance, **When** it completes, **Then** a stage-progression record is written with the time spent, and the turnaround clock reflects it.
5. **Given** a sample that has not passed quality control, **When** report/archive is attempted, **Then** it is refused until QC is passed.

---

### User Story 3 - Operational workflow support and turnaround visibility (Priority: P3)

As lab staff and administrators, the backend supports the day-to-day workflow around the stages — grouping samples into batches, recording data generation and quality-control outcomes, managing external vendors and their separate turnaround, and reporting turnaround performance — so the department can run and measure its work.

**Why this priority**: These capabilities make the gated workflow (US2) operable at scale and measurable, but the core clinical guarantee stands without them. They are high-value operational support rather than the minimum viable process.

**Independent Test**: Group several samples into a batch and act on them together; record a data-generation outcome and a QC pass/fail for a sample; assign a sample to an external vendor and confirm that vendor's turnaround is tracked separately; retrieve turnaround metrics and confirm they reflect the recorded stage durations against the configured targets.

**Acceptance Scenarios**:

1. **Given** several samples, **When** they are grouped into a batch, **Then** an action on the batch applies to its members and is recorded per sample.
2. **Given** a sample in data generation, **When** a data-generation outcome is recorded, **Then** its stage reflects completion and the result is auditable.
3. **Given** a sample undergoing quality control, **When** a QC result is recorded, **Then** a pass permits progression toward reporting and a fail blocks it.
4. **Given** a sample sent to an external vendor, **When** its turnaround is measured, **Then** it is counted by that vendor's rule (e.g., from sequencing for the sequencing-anchored vendor) separately from the internal turnaround.
5. **Given** samples in progress, **When** an administrator views turnaround metrics, **Then** the metrics show durations and breaches against the per-stage targets and the 18-day internal target.
6. **Given** a stage's turnaround target, **When** an administrator changes it, **Then** future measurement uses the new value while recorded histories are unchanged.

---

### User Story 4 - Report delivery and portal push (Priority: P3)

As the department, once a case passes quality control its report is stored and automatically pushed to the external Genomic Data Portal, with the push tracked and retryable, so results reach the portal reliably and the case can be closed.

**Why this priority**: This is the workflow's output and the external hand-off, depending on the gated workflow (US2) and QC (US3) being in place. It completes the end-to-end path but is the last link, so it follows the core.

**Independent Test**: With a QC-passed sample, upload its report and confirm it is stored and retrievable only by authorized roles; confirm a push to the portal is attempted and its status tracked; simulate a portal failure and confirm the push is marked failed and can be retried to success; confirm the case closes only after the report is stored and the push has succeeded.

**Acceptance Scenarios**:

1. **Given** a QC-passed sample, **When** its report is uploaded, **Then** the report is stored with its metadata and is retrievable only by authorized roles.
2. **Given** a stored report, **When** reporting completes, **Then** a push to the Genomic Data Portal is created and its status is recorded as queued, then success or failure.
3. **Given** a push that failed, **When** it is retried, **Then** it is re-attempted and, on success, marked delivered without creating a duplicate.
4. **Given** the external portal's details are not yet available, **When** the system runs, **Then** report storage and the rest of the workflow are unaffected and pushes queue against a replaceable portal connection.
5. **Given** a sample whose report is stored and whose portal push has succeeded, **When** the case-close rule is evaluated, **Then** the case is marked closed and its final state is recorded; **Given** the push is still queued/failed/retrying, **Then** the case remains open.

### Edge Cases

- A session expires mid-task → the next protected request is refused and the user must re-authenticate; no partial change is left un-attributed.
- An acting identity is somehow absent on a write path → the write is refused (the data store rejects un-attributed changes), surfaced as a clear server-side error, not a silent success.
- Two users act on the same sample concurrently → the first advance wins; the second is rejected with a conflict (optimistic concurrency, FR-010a) and the user is prompted to refresh, with both attempts auditable.
- A report upload is attempted for a sample that has not passed QC → refused with a reason.
- A portal push partially succeeds or times out → it is recorded as failed/uncertain and is safely retryable without duplicating the delivery.
- An administrator lowers a stage's turnaround target after samples have progressed → past durations are unchanged; only future measurement uses the new target.
- A non-administrator calls an administrator-only management endpoint → denied, with the attempt recorded.
- A report file exceeds the accepted size or type → rejected with a clear reason before storage.

## Requirements *(mandatory)*

### Functional Requirements

**Authentication, authorization, audit (US1)**

- **FR-001**: The backend MUST authenticate users and issue a session on correct credentials, and MUST validate that session on every protected request; an unauthenticated or invalid request is refused. Sessions use a short-lived access credential (~15 minutes) silently renewed by a rotating refresh credential, with re-authentication required after extended inactivity (~12 hours idle, ~7 days absolute); these durations are configurable.
- **FR-002**: The backend MUST enforce role-based authorization for the five roles (`admin`, `genomics`, `trf`, `molecular`, `bioinformatics`), allowing a user to hold several roles and granting administrators all permissions.
- **FR-003**: The backend MUST be the only writer to the data store and MUST set the acting user and roles for each unit of work so the audit trail and row-level security apply (the data-layer guarantees from Spec 1).
- **FR-004**: The backend MUST record every create, update, and delete with attribution to the acting user, in the same unit of work as the change, with no un-attributed changes.
- **FR-005**: The backend MUST let administrators create and manage user accounts and role assignments, and MUST expose the signed-in user's own identity and roles.
- **FR-006**: The backend MUST provide a first-run way to create the initial administrator account (not present in the seed), after which further accounts are created through the backend.
- **FR-007**: Secrets and credentials MUST come from server configuration only and never be exposed to clients or stored in the repository.

**Gated workflow (US2)**

- **FR-008**: The backend MUST register samples at the first stage with their intake details and a unique case identifier, rejecting duplicates.
- **FR-009**: The backend MUST advance samples through the 8 ordered stages and MUST enforce stage gates server-side: the consent checklist complete before molecular processing, and quality control passed before report/archive. Gates MUST NOT be bypassable by any client.
- **FR-010**: The backend MUST refuse an advance that skips a stage or whose preconditions are unmet, returning a clear reason, and MUST record each successful advance as a stage-progression event with its duration.
- **FR-010a**: The backend MUST handle concurrent advances of the same sample with optimistic concurrency: it MUST detect that the sample has already moved and reject the stale advance with a conflict (prompting the user to refresh), so progression stays ordered and is never duplicated; both attempts remain auditable.
- **FR-011**: The backend MUST maintain the per-sample consent/documentation checklist and expose its completeness as the gate for molecular processing.

**Operational support & turnaround (US3)**

- **FR-012**: The backend MUST support grouping samples into batches and performing **stage-advance and assignment** operations on a batch, such that the operation applies to and is recorded for each member individually, with each sample's own stage gates still enforced (a member failing its gate does not block the others). Other stage actions (QC, reporting) remain per-sample.
- **FR-013**: The backend MUST record data-generation and quality-control outcomes for a sample, with QC pass/fail controlling progression toward reporting.
- **FR-014**: The backend MUST manage external vendors and track each vendor's turnaround separately from the internal turnaround, using the vendor's configured anchor (e.g., counted from sequencing for the sequencing-anchored vendor).
- **FR-015**: The backend MUST compute turnaround metrics from recorded stage durations against the per-stage targets and the 18-day internal target, and MUST let administrators change per-stage targets without altering recorded histories.

**Reports & portal push (US4)**

- **FR-016**: The backend MUST accept report files for QC-passed samples, store them with their metadata, and serve them only to authorized roles; it MUST reject reports for samples that have not passed QC, and reject files that exceed the accepted size or type.
- **FR-017**: On report completion the backend MUST create a push to the Genomic Data Portal and track its status (queued, success, failed), and MUST make a failed push retryable without duplicating a delivery.
- **FR-018**: The portal connection MUST be isolated behind a single replaceable interface so its endpoint and credentials can be supplied later without affecting the rest of the system; long-running pushes run as background work with pollable status.
- **FR-019**: The backend MUST close a case only once its report is stored **and** its portal push is confirmed successful, recording the case's final state; a case whose push is still queued, failed, or retrying stays open until delivery succeeds.

**Cross-cutting**

- **FR-020**: The backend MUST publish a machine-readable description of its interface (the contract the frontend consumes) and keep it current as the single source of API truth.
- **FR-021**: All protected traffic MUST be served over the internal network behind the reverse proxy; the backend binds to the internal interface only.
- **FR-022**: Every stage-gate rule, authorization guard, and authentication path MUST be covered by automated tests.

### Key Entities *(include if feature involves data)*

Most persistent entities are owned by the Spec 1 data layer (users, roles, stages, samples, stage events, audit log, vendors, calendar, jobs). This feature adds behavior and these additional concepts:

- **Session / credential**: the authenticated identity a signed-in user carries; backed by account credentials the backend verifies (added to the existing account records; no credentials were seeded in Spec 1).
- **Consent checklist**: the per-sample documentation state that gates molecular processing.
- **Batch**: a grouping of samples acted on together.
- **QC result / data-generation outcome**: recorded stage outcomes that control progression.
- **Report**: a stored result file plus metadata, linked to a sample, served under authorization.
- **Portal push**: a tracked, retryable delivery of results to the external portal, behind a replaceable connection.
- **API contract**: the published, current description of the backend's interface consumed by the frontend.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of protected endpoints refuse unauthenticated or invalid-session requests, returning no data and making no change.
- **SC-002**: 100% of role-restricted actions are permitted for authorized roles and denied for unauthorized ones, verified across all five roles.
- **SC-003**: 100% of data-changing operations produce an attributed audit record in the same unit of work; zero un-attributed changes observed in testing.
- **SC-004**: Zero stage-gate bypasses: every attempt to skip a stage or an unmet gate (consent-before-molecular, QC-before-report) is refused in testing.
- **SC-005**: Turnaround metrics match the recorded stage durations and configured targets exactly, and changing a target never alters a previously recorded duration.
- **SC-006**: A failed portal push can be retried to success with no duplicate delivery, and report storage/workflow continue to function while the portal connection is unavailable (mock).
- **SC-007**: Reports are retrievable only by authorized roles; 100% of unauthorized retrieval attempts are refused.
- **SC-008**: The published interface contract stays consistent with the implemented endpoints (no drift) and every stage-gate rule, authorization guard, and auth path has a passing automated test.
- **SC-009**: Concurrent advances of one sample never produce a skipped or duplicated stage: the stale attempt is rejected with a conflict in 100% of tested races, and a case is marked closed only after its portal push has succeeded (never while queued/failed/retrying).

## Assumptions

- **Governed by the constitution v2.0.0**: backend-native authentication (admin-created accounts, short-lived session token delivered as a secure cookie, password hashing), FastAPI as the single writer, filesystem report storage under the configured data root, and the portal client isolated behind one module. These are fixed by project law and treated as given, not re-decided here.
- **Builds on Spec 1**: the schema, audit triggers, append-only history, and row-level security exist; this feature sets the acting identity each transaction and adds auth credentials to the existing account records via a new versioned migration (schema changes remain migration-only).
- **Reports are uploaded, not generated**: report files are produced outside Helixa (e.g., by bioinformatics) and uploaded to the backend, which stores and delivers them; the backend does not author report content.
- **Portal API is not yet defined**: its endpoint and auth are unknown, so the push is implemented against a replaceable/mocked connection and wired to real details later; this does not block the rest of the backend.
- **Notifications are out of scope**: email/SMTP alerts and the daily digest are Spec 3.1 (M8), not this feature.
- **Frontend and sequencer ingestion are out of scope**: the UI is Spec 3; sequencer basecall ingestion and its tables are Spec 4. Data generation here is recorded as a stage outcome rather than driven by real sequencing output.
- **Scale**: a small internal department (~10–20 users, thousands of samples/year); standard web-service responsiveness is sufficient and no high-concurrency targets are implied.
- **Defaults** (session lifetime resolved in Clarifications: ~15 min access, rotating refresh, ~12 h idle / 7 d absolute): accepted report file types/sizes and portal retry/backoff limits use sensible, configurable defaults documented at planning time; administrators adjust operational values (e.g., per-stage targets) in use.

## Dependencies

- Helixa Constitution v2.0.0 — Articles I (single writer, layer boundaries), III (auth, RBAC, RLS, secrets), IV (same-transaction audit), V (workflow gates, SLA/TAT), VI (portal push isolated & retryable, filesystem report storage), VIII (migrations, pytest coverage, OpenAPI export, jobs worker).
- Spec 1 (Database Foundation) — schema, audit/append-only triggers, RLS, session-context contract, jobs table.
- Prerequisite infrastructure (M0) — running database, reverse proxy with TLS, data directories, backups.
- Downstream — Spec 3 (Frontend) consumes the published interface contract; Spec 4 (Sequencer ingestion) later drives the data-generation stage.
