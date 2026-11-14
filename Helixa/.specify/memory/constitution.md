# Helixa Constitution

Governing principles for the Helixa genomics workflow platform. These rules bind every spec, plan,
and implementation. A plan that violates an article is rejected, not merged.

Project: Helixa (repo `balqees-medlabs/Helixa`) · Medlabs Genomics Department · internal web app

## Preamble

Helixa manages NGS samples from receipt to final report for the Medlabs Genomics Department. It
holds patient data and MUST be auditable, role-bound, and correct before it is fast. The system is
built in three layers — **Database**, **Backend**, **Frontend** — and no layer may take on
another's responsibility. It runs entirely on the lab server; it depends on no external account or
hosted service.

## Core Principles

### Article I — Layer boundaries (non-negotiable)

1. **Database** owns schema, constraints, Row-Level Security, triggers, and seed data. It MUST
   contain no application logic beyond integrity rules.
2. **Backend** (FastAPI) owns ALL business logic and is the single writer to the database. Every
   rule — stage gates, SLA, audit, RBAC, authentication — MUST live here.
3. **Frontend** (Next.js) owns presentation and interaction only. It MUST NOT contain business
   logic and MUST NOT talk to Postgres or the filesystem directly; it calls the backend.
4. A spec for one layer MUST NOT implement another layer's responsibility. The dependency order is
   fixed: Database → Backend → Frontend.

Rationale: Clear ownership keeps patient-data correctness and auditability enforceable in exactly
one place (the backend) and prevents the business rules from being duplicated or bypassed.

### Article II — Stack (fixed for v1)

1. Frontend: Next.js 14.x (App Router), TypeScript, Tailwind, shadcn/ui.
2. Backend: Python FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic.
3. Database: PostgreSQL 16 in Docker on the lab server. Alembic owns the `public` schema; no other
   service writes schema.
4. Authentication is implemented in the backend: argon2 password hashes, short-lived access JWT
   delivered as an httpOnly, Secure, SameSite cookie, rotating refresh token, admin-created
   accounts only (no self-signup, no third-party identity provider in v1).
5. File storage: report files and sequencing data live on the server filesystem under a configured
   data root (`/data` by default) with metadata rows in Postgres. Files are read and written only
   by the backend.
6. Monorepo: `/frontend`, `/backend`, `/infra` (compose, reverse proxy, backup scripts), `/specs`,
   `/docs`, `/.specify`.
7. External command-line tools (e.g. `bases2fastq`) are permitted when wrapped behind one backend
   module with a mockable interface and configured via server `.env`.
8. No additional framework, database, message queue, or auth system is introduced without a
   written decision recorded in `/docs/decisions/`.

Rationale: A fixed, minimal stack removes per-feature technology debate, needs no external account,
and keeps the deployment to a handful of containers a single maintainer can run and upgrade.

### Article III — Security & access

1. The backend issues and validates the JWT. Every protected route MUST validate it; an
   unvalidated request is rejected. Tokens are never exposed to frontend JavaScript.
2. Access is role-based: `admin`, `genomics`, `trf`, `molecular`, `bioinformatics`. A user may hold
   several roles. `admin` may do everything.
3. Postgres Row-Level Security MUST be enforced as a second layer beneath the backend guards —
   defense in depth, not either/or. The backend sets the acting user and roles on each transaction
   (`SET LOCAL`) so policies can evaluate them.
4. Secrets (JWT signing key, database password, SMTP credentials, Portal API token) live only in
   server `.env`, never in the repo or the frontend bundle.
5. All traffic runs over the internal network / VPN behind a reverse proxy with TLS. Postgres and
   the backend bind to the internal interface only.

Rationale: Patient data requires authenticated, role-bound access with two independent enforcement
layers so a single bug does not expose records.

### Article IV — Auditability (immutable)

1. Every create, update, and delete MUST write an `audit_log` entry — actor, action, entity,
   before/after, timestamp — in the same transaction as the change.
2. Changes made by automated jobs are attributed to a dedicated `system` actor recorded in `users`
   with no login; the originating job id is stored with the entry.
3. `audit_log` and `sample_stage_events` are append-only: UPDATE and DELETE MUST be rejected at the
   database level by trigger, for every role.
4. No action that changes state may bypass the audit path.

Rationale: A clinical system must be able to reconstruct who did what and when; same-transaction,
trigger-protected logging makes the trail complete and tamper-resistant.

### Article V — Workflow integrity

1. Samples move through 8 ordered stages: sample received → consent & documentation → molecular
   processing → data generation → TRF preparation → TRF confirmation → data conversion & QC →
   report upload/archive/portal push.
2. Stage gates MUST be enforced server-side, not merely in the UI: consent checklist complete
   before molecular processing; QC pass before report/archive. The frontend may reflect a gate, but
   the backend is the authority.
3. Stages advance in order only. Sequencing output maps to stages as follows: a completed
   sequencing run with basecalls present for a sample completes **Stage 4 (data generation)**;
   successful FASTQ conversion plus QC pass completes **Stage 7 (data conversion & QC)**. Automation
   MUST hold a ready result until the sample has reached the preceding stage rather than advance
   out of order.
4. Each stage has a configurable SLA (in days), editable by admin. Advancing a stage records an
   event with its duration.
5. The internal turnaround target is 18 calendar days (Fridays included) against a 45-working-day
   baseline computed from a configurable working-day and holiday calendar. External vendor TAT is
   tracked separately; Centogene's 30-day TAT is counted from sequencing, not from receipt.

Rationale: Correct, gated progression is the core clinical guarantee; enforcing it server-side keeps
the workflow authoritative regardless of the client.

## Integrations

### Article VI — Integrations

1. On a successful report upload, Helixa pushes results to the Genomic Data Portal via its API so
   they surface there. Push status (queued / success / failed) MUST be tracked and retryable.
2. The portal client MUST be isolated behind one backend module with a stable interface, so its
   endpoint and auth can be supplied later without touching the rest of the system.
3. Notifications are email only (v1), sent via the Medlabs SMTP server.
4. Report files are uploaded live and stored under `/data/reports` on the server, with a metadata
   row in Postgres; they are served only through the backend with RBAC applied.
5. Sequencing ingestion downloads basecall files from the sequencer to `/data/runs` on the server
   and converts them to FASTQ with `bases2fastq` behind an isolated, mockable module; successful
   download drives Stage 4 and successful conversion drives Stage 7 (Article V.3). Binary path,
   source path, staging root, thread count, and retention come from server `.env`.

Rationale: External dependencies change on their own schedule; isolating and status-tracking them
keeps the rest of the system stable and operations recoverable.

## Design & Delivery

### Article VII — Design

1. Follow the Medlabs brand: red accent (from the logo electropherogram waveform), neutral grey
   text, white surfaces, clean clinical look.
2. Sentence case throughout; accessible contrast.
3. Layout is kept RTL-safe from day one for future Arabic support (English ships first).
4. Four dashboards — Admin, Genomics, Molecular Biology, Bioinformatics — plus a shared TAT
   dashboard, each rendered by the user's roles.

### Article VIII — Quality & delivery

1. Database changes MUST go through Alembic migrations — never manual edits to a live schema.
2. Backend ships with pytest coverage for auth, RBAC guards, and every stage-gate rule.
3. Each feature is delivered with its spec, plan, and tasks committed alongside the code.
4. The backend exports an OpenAPI spec; the frontend consumes it as the single source of API truth.
5. **Foundation specs** (Specs 1–3: database, backend core, frontend shell) are per-layer and
   proceed one at a time, each reviewed before the next begins. **Feature specs** written after the
   foundations exist may span layers, provided each deliverable lives in its own layer's folder and
   respects Article I.
6. Long-running work (file transfer, conversion, portal push) runs as jobs in a Postgres `jobs`
   table processed by a dedicated worker process shipped in the backend image. Jobs survive
   restarts and expose pollable status. No external queue or broker without an Article II.8
   decision.
7. Backups (nightly `pg_dump` of Postgres, plus `/data/reports`) are in place from the first
   milestone that stores data, not deferred to go-live. `/data/runs` is excluded from backups and
   governed by the retention setting.

## Governance

This constitution supersedes other practices for Helixa. Every spec, plan, and implementation is
checked against it; a plan that violates an article is rejected, not merged.

Amendment procedure: this constitution changes only by editing `.specify/memory/constitution.md`
and re-running `/speckit-constitution`. Specs written under an older version are re-checked against
the current one.

Versioning policy (semantic):

- MAJOR: backward-incompatible governance changes — an article removed or redefined.
- MINOR: a new article/section added, or materially expanded guidance.
- PATCH: clarifications, wording, and non-semantic refinements.

Compliance review: reviewers MUST verify article compliance before merge; foundation work proceeds
one layer-spec at a time (Database → Backend → Frontend), each reviewed before the next begins.

**Version**: 2.0.0 | **Ratified**: 2026-10-31 | **Last Amended**: 2026-11-13
