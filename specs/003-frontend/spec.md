# Feature Specification: Frontend (Spec 3)

**Feature Branch**: `003-frontend`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "Spec 3 — the Helixa frontend: a presentation-only web app that consumes the backend OpenAPI contract with cookie-session auth, role-based routing, the Medlabs theme (RTL-safe), four role dashboards plus a shared TAT Kanban, and screens for the full sample workflow, QC, batches, vendors, reports and portal status."

## Overview

Helixa's frontend is the only interface lab staff use. It presents the backend's data and lets people act on it — nothing more: it holds no business rules, never talks to the database directly, and treats the backend as the single authority. Staff sign in, see exactly what their roles permit, move samples through the clinical workflow with the system's gate reasons shown plainly, and watch turnaround across the department. It is a clean, clinical, Medlabs-branded experience, accessible and ready for Arabic from day one, that stays faithful to the backend's published interface so the two never drift.

This is the third and final foundational layer (Database → Backend → Frontend). It consumes the Spec 2 backend only; it excludes any backend change (Spec 2), email notifications (Spec 3.1), and sequencer ingestion (Spec 4).

## Clarifications

### Session 2026-11-18

- Q: What should each role dashboard primarily show? → A: The role's actionable work queue — the samples/actions waiting on that role — plus summary counts and breach flags (genomics: intake/consent; molecular: molecular processing; bioinformatics: data generation/QC/reporting; admin: everything plus users and vendors).
- Q: When a session expires mid-task, what happens? → A: Silently renew via the backend refresh and let the in-flight action continue; only if renewal fails does the app return to sign in, preserving context where feasible.
- Q: How do the turnaround board and status views stay current? → A: Refresh on user action and auto-refresh on a periodic interval (~30–60s); no live streaming in v1.
- Q: How does a multi-role user land and switch dashboards? → A: Land on the most privileged dashboard they hold (admin if present) with a visible switcher to the other dashboards their roles grant.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sign in and role-bound access (Priority: P1)

As a member of the Genomics Department, I sign in once and the app shows me only the areas my role allows, keeps me signed in across the working day, and sends me back to sign-in if my session ends — so access stays controlled and the interface isn't cluttered with actions I can't take.

**Why this priority**: Nothing else is reachable without it. Authentication and role-aware navigation are the precondition for every other screen and establish the trusted shell (theme, layout, session handling) the rest of the app lives in. Delivered alone it is already useful: people can sign in, land on their home, and sign out securely.

**Independent Test**: Sign in with valid credentials and land on a role-appropriate home; attempt to open a protected area directly while signed out and be redirected to sign in; as a single-role user, confirm navigation and actions outside that role are not offered; let the session lapse and confirm the next action returns the user to sign-in without losing unsaved context silently; sign out and confirm protected areas are no longer reachable.

**Acceptance Scenarios**:

1. **Given** valid credentials, **When** the user signs in, **Then** they reach a home view appropriate to their roles and their name/roles are shown.
2. **Given** no active session, **When** the user opens any protected screen (including by direct link), **Then** they are redirected to sign in and returned to their target after authenticating.
3. **Given** a signed-in user, **When** the app renders navigation and actions, **Then** only those permitted by the user's roles are offered; a user with several roles can reach all of them.
4. **Given** a session that has expired, **When** the user next acts, **Then** the app recovers the session transparently if possible, otherwise returns the user to sign in with a clear message.
5. **Given** a signed-in user, **When** they sign out, **Then** the session ends and protected screens are no longer reachable.
6. **Given** wrong credentials, **When** the user attempts to sign in, **Then** a single clear error is shown without revealing whether the email or the password was wrong.

---

### User Story 2 - Operate the sample workflow (Priority: P2)

As lab staff, I register samples and move them through the 8 clinical stages from the interface, completing the consent checklist and seeing exactly why an action is blocked when a gate isn't met — so the clinical process is followed and the reasons are never a mystery.

**Why this priority**: This is the core daily work and the reason the app exists. Once access is controlled (US1), these screens let people actually run the workflow. It stands alone: staff can register, view, and advance samples with the backend's rules surfaced.

**Independent Test**: Register a sample and see it at the first stage; open its detail and see its stage history; advance it one stage and see the update; attempt an advance that the backend refuses (consent incomplete, QC not passed, skipping a stage, or a stale/already-moved sample) and see the specific reason; complete the consent checklist and then advance successfully.

**Acceptance Scenarios**:

1. **Given** the register-sample screen, **When** a sample is registered, **Then** it appears in the sample list at the first stage with its case identifier and intake details.
2. **Given** a sample's detail view, **When** it is opened, **Then** its current stage, status, and full stage history (with timings) are shown.
3. **Given** a sample whose next-stage gate is unmet, **When** an advance is attempted, **Then** the action is prevented and the backend's specific reason is shown (e.g., consent incomplete, QC not passed, cannot skip a stage).
4. **Given** two people acting on the same sample, **When** one advance has already moved it, **Then** the other sees a clear "already advanced — refresh" message rather than a silent or duplicate change.
5. **Given** the consent checklist, **When** required items are marked complete, **Then** the molecular-processing gate opens and the sample can advance.

---

### User Story 3 - Role dashboards and the shared turnaround board (Priority: P2)

As staff and administrators, I open a dashboard tailored to my role and a shared turnaround (TAT) board that shows every sample arranged across the 8 stages — so I can see my work and the department's progress at a glance and spot anything overdue.

**Why this priority**: Dashboards are the daily landing and the at-a-glance value of the system; the TAT board makes turnaround visible, which is a core departmental goal. They build on the workflow data (US2) but deliver distinct, high-value overview.

**Independent Test**: Sign in as each role and confirm the matching dashboard loads with role-relevant content; open the shared TAT board and confirm samples appear in columns by their current stage, with overdue samples visibly flagged against the targets; move a sample and confirm the board reflects the new stage on refresh.

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they open their dashboard, **Then** they see their role's actionable work queue (the samples/actions awaiting that role) with counts and breach flags; a multi-role user lands on their most privileged dashboard and can switch to the others their roles grant.
2. **Given** the shared TAT board, **When** it is opened, **Then** samples are shown in columns for the 8 stages, each card showing its case and time-in-stage, and samples past their target are visibly flagged.
3. **Given** a sample that advances, **When** the board is next viewed/refreshed, **Then** the sample appears under its new stage.
4. **Given** an administrator, **When** they view turnaround metrics, **Then** per-stage durations and breaches against the per-stage and 18-day targets are shown, including external-vendor turnaround tracked separately.

---

### User Story 4 - Operational data entry: QC, batches, vendors (Priority: P3)

As bioinformatics and admin staff, I record quality-control and data-generation outcomes, group samples into batches and advance them together (seeing a per-member result), and manage the external vendor list — so the workflow is operable at scale and measurable.

**Why this priority**: These make the workflow efficient and complete but aren't the minimum path; the core clinical operation (US2) stands without them.

**Independent Test**: Record a QC pass/fail for a sample and see it reflected (a pass unblocks reporting, a fail blocks it); create a batch, add samples, advance the batch, and see each member's outcome (advanced / blocked-with-reason); view and edit the vendor list within permissions.

**Acceptance Scenarios**:

1. **Given** the QC entry screen, **When** a QC or data-generation outcome is recorded, **Then** it is saved and the sample's state reflects it (a QC pass enables reporting; a fail prevents it).
2. **Given** a batch, **When** it is advanced, **Then** a per-member result list is shown — each sample either advanced or blocked with its specific reason — without one member's failure blocking the others.
3. **Given** the vendor area, **When** an administrator adds or edits a vendor, **Then** the change is saved; non-administrators can view but not change.

---

### User Story 5 - Reports and portal delivery (Priority: P3)

As authorized staff, I upload a sample's report, retrieve stored reports when permitted, and see the status of the push to the external portal with the option to retry — so results are delivered and the hand-off is visible.

**Why this priority**: This is the workflow's output and the external hand-off; it depends on QC (US4) and the workflow (US2) and completes the end-to-end path, so it comes last.

**Independent Test**: For a QC-passed sample, upload a report and confirm it is accepted (and that an unsupported type, an oversize file, or a non-QC sample is refused with a clear reason); retrieve a stored report as an authorized role and confirm an unauthorized role cannot; view a portal push's status and, for a failed one, trigger a retry and see the status change.

**Acceptance Scenarios**:

1. **Given** a QC-passed sample, **When** a report is uploaded, **Then** it is accepted and listed; **When** the file is the wrong type/too large or the sample hasn't passed QC, **Then** the upload is refused with the specific reason.
2. **Given** a stored report, **When** an authorized role opens it, **Then** it is retrievable; **When** an unauthorized role attempts, **Then** access is refused.
3. **Given** a portal push, **When** its status is viewed, **Then** queued/success/failed is shown; **When** a failed push is retried, **Then** the status updates accordingly.

### Edge Cases

- The backend is unreachable or returns an error → a clear, non-technical message is shown and no partial/incorrect state is implied; the user can retry.
- A permitted screen shows no data yet (empty sample list, empty dashboard) → a helpful empty state, not a blank or broken view.
- A long-running action (report upload, batch advance) → progress is indicated and the control can't be double-submitted.
- The access session lapses mid-task → the app recovers transparently if it can, otherwise preserves what the user was doing where feasible and returns them to it after re-authentication.
- A user holds multiple roles → they can reach every area any of their roles permit, without duplication or conflict.
- The interface is viewed in a right-to-left layout → text, navigation, and the stage board mirror correctly.
- A value from the backend is unknown to the UI (e.g., an unexpected status) → it is displayed safely rather than crashing the view.

## Requirements *(mandatory)*

### Functional Requirements

**Shell, auth & access (US1)**

- **FR-001**: The app MUST authenticate users against the backend sign-in and maintain the session without exposing any token to page scripts; the user is never asked to manage tokens.
- **FR-002**: The app MUST protect every non-public screen: an unauthenticated visitor (including via a direct link) is redirected to sign in and returned to their target afterward.
- **FR-003**: The app MUST render navigation and actions according to the signed-in user's roles (`admin`, `genomics`, `trf`, `molecular`, `bioinformatics`), offering only what each permits; a user may hold several roles and reach all of them; `admin` reaches everything.
- **FR-004**: When a session expires mid-task, the app MUST silently renew it via the backend refresh and let the in-flight action continue; only if renewal fails does it return the user to sign in with a clear message, preserving the in-progress context where feasible and never silently discarding it.
- **FR-005**: The app MUST provide sign-out that ends the session so protected screens are no longer reachable, and MUST show a single non-revealing error on failed sign-in.
- **FR-006**: The app MUST present the signed-in user's identity and roles.

**Workflow screens (US2)**

- **FR-007**: The app MUST let authorized users register a sample and list samples, showing each sample's case identifier, current stage, and status.
- **FR-008**: The app MUST show a sample's detail with its full, ordered stage history including time spent per stage.
- **FR-009**: The app MUST let authorized users advance a sample and MUST surface the backend's specific refusal reason when a gate is unmet (consent incomplete, QC not passed, stage-skip, or an already-advanced/stale sample), without attempting to bypass or reinterpret the rule.
- **FR-010**: The app MUST present the per-sample consent checklist and let authorized users mark items complete, reflecting when the molecular gate is open.

**Dashboards & turnaround (US3)**

- **FR-011**: The app MUST provide four role dashboards — Admin, Genomics, Molecular Biology, Bioinformatics — each led by that role's **actionable work queue** (the samples/actions waiting on it) with summary counts and breach flags: genomics → intake/consent; molecular → molecular processing; bioinformatics → data generation/QC/reporting; admin → everything plus users and vendors. A multi-role user lands on the most privileged dashboard they hold (admin if present) and can switch to the others their roles grant.
- **FR-012**: The app MUST provide a shared turnaround board that arranges samples in columns across the 8 stages, each card showing its case and time-in-stage, with samples past target visibly flagged. The board and status views MUST refresh on user action and auto-refresh on a periodic interval (~30–60s); live streaming is not required in v1.
- **FR-013**: The app MUST present turnaround metrics (per-stage durations and breaches against the per-stage targets and the 18-day internal target, plus external-vendor turnaround shown separately) to administrators.

**Operational entry (US4)**

- **FR-014**: The app MUST let authorized users record QC and data-generation outcomes and reflect their effect on the sample (QC pass enables reporting; fail prevents it).
- **FR-015**: The app MUST let authorized users create batches, add samples, and advance a batch, showing a per-member result (advanced, or blocked with its reason) where one member's failure does not block others.
- **FR-016**: The app MUST let administrators manage vendors and let other roles view them read-only.

**Reports & portal (US5)**

- **FR-017**: The app MUST let authorized users upload a sample's report and MUST surface the backend's refusal reasons (unsupported type, too large, QC not passed) clearly; uploads are restricted to the roles the backend permits.
- **FR-018**: The app MUST let the permitted roles (administrators, bioinformatics, genomics) retrieve stored reports and MUST not offer retrieval to roles the backend forbids.
- **FR-019**: The app MUST show portal-push status (queued/success/failed) and let an administrator retry a failed push, reflecting the resulting status.

**Cross-cutting**

- **FR-020**: The app MUST contain no business logic and MUST NOT access the database directly; every action goes through the backend, which remains the single source of truth.
- **FR-021**: The app's calls to the backend MUST be derived from the backend's published interface contract so the two cannot drift; an endpoint the contract doesn't define is not called.
- **FR-022**: The app MUST follow the Medlabs visual identity (red accent, neutral grey text, white surfaces, clean clinical look), use sentence case throughout, meet accessible contrast, and lay out correctly in both left-to-right and right-to-left directions (English first; Arabic later).
- **FR-023**: The app MUST handle backend errors and empty states gracefully with clear, non-technical messaging, and MUST prevent double submission of in-progress actions.

### Key Entities *(include if feature involves data)*

All data is owned by the backend; the frontend only renders and submits it. The user-facing concepts it presents:

- **Session / current user**: the signed-in identity and roles that drive navigation and access.
- **Sample**: case identifier, current stage, status, intake details, and stage history — the central object of the workflow screens and the TAT board.
- **Consent checklist**: the per-sample required items the user completes to open the molecular gate.
- **QC / data-generation outcome**: recorded results that gate reporting.
- **Batch**: a group of samples acted on together, with a per-member outcome view.
- **Vendor**: an external lab with its own turnaround, managed by admins.
- **Report**: an uploaded result file and its metadata, retrievable by permitted roles.
- **Portal push**: the delivery status (queued/success/failed) of results to the external portal, with retry.
- **Turnaround metrics**: per-stage and per-sample durations against targets, shown on dashboards and the TAT board.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of protected screens redirect an unauthenticated visitor to sign in (including direct-link access), and none render protected data before authentication.
- **SC-002**: For every role, the interface offers only the actions that role is permitted; in testing, zero actions outside a user's roles are presented or succeed.
- **SC-003**: Every workflow action the backend refuses shows the backend's specific reason to the user; zero refusals surface as a generic or silent failure.
- **SC-004**: A signed-in user can register a sample and advance it one stage entirely within the app (no page reload) for the common path, and the end-to-end journey completes well under a minute of interaction.
- **SC-005**: The turnaround board places every sample in the column for its current stage and flags 100% of past-target samples; the board reflects a stage change after refresh.
- **SC-006**: Reports are retrievable only by the permitted roles — 100% of unauthorized retrieval attempts are not offered and are refused.
- **SC-007**: The interface renders correctly and usably in both left-to-right and right-to-left layouts, and meets accessible contrast on primary text and controls.
- **SC-008**: The app calls only endpoints defined by the backend's published contract; a contract change that removes or alters an endpoint is caught before release (no drift).

## Assumptions

- **Backend is the authority (constitution Art. I/III)**: the frontend is presentation-only, holds no rules, and never reaches the database; all behavior comes from the Spec 2 backend over its API. The gate/permission logic shown is the backend's, surfaced — not re-implemented.
- **Cookie-session auth**: the backend issues httpOnly `access`/`refresh` cookies and the app runs same-origin behind the reverse proxy, so the browser never reads tokens and cross-site requests don't carry them. Session recovery uses the backend's refresh endpoint; on its failure the user re-authenticates.
- **Contract-driven**: the typed API layer is generated from the backend's published OpenAPI contract, which is the single source of API truth; the drift guarantee (SC-008) is enforced against that contract.
- **Role→dashboard mapping** (resolved, Clarifications 2026-11-18): each dashboard leads with the role's actionable work queue; a multi-role user lands on the most privileged dashboard they hold (`admin` first) and switches to the others their roles grant.
- **Turnaround board freshness** (resolved, Clarifications 2026-11-18): the board and status views refresh on action and auto-refresh on a periodic interval (~30–60s); live push updates are not required for v1.
- **Session recovery** (resolved, Clarifications 2026-11-18): an expired session is renewed silently via the backend refresh so the in-flight action continues; only a failed renewal returns the user to sign in.
- **Report viewing**: the app offers download/open of stored report files to permitted roles; in-browser preview beyond that is a nice-to-have, not required.
- **Localization**: English ships first with an RTL-safe layout; Arabic translation content is a later addition, not part of this feature's delivery.
- **Scale**: a small internal department (~10–20 concurrent users); standard web-app responsiveness is sufficient and no high-concurrency targets are implied.

## Dependencies

- Helixa Constitution v2.0.0 — Article I (frontend is presentation only; no DB access; dependency order), Article III (cookie-session auth, role-based access), Article VII (Medlabs design, sentence case, accessible contrast, RTL-safe, the four dashboards + shared TAT), Article VIII (frontend consumes the exported OpenAPI as the single source of API truth).
- Spec 2 (Backend API) — the running backend and its published `openapi.json` contract (auth, samples/workflow, consent, QC, batches, vendors, metrics, reports, portal).
- Prerequisite infrastructure (M0) — reverse proxy with TLS serving the app and API same-origin on the internal network.
- Out of scope — backend changes (Spec 2), email notifications (Spec 3.1), sequencer ingestion and its UI (Spec 4).
