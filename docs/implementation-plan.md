# Helixa — Implementation Plan

How the three layer-specs get built, in what order, with milestones and exit criteria.
Project: Helixa (internal web app) · Repo `balqees-medlabs/Helixa` · Host `labs@192.168.127.125` (Debian Trixie) · v1.2

Read alongside: `.specify/memory/constitution.md` (project law, v2.0.0) and `docs/layer-specs.md` (the Spec 1/2/3 blocks — **add this file; §3 depends on it**).

**v1.2 changes:** Supabase dropped in favor of plain Postgres + backend-native auth + filesystem storage (constitution 2.0.0, no external accounts, three app containers). Sequencer ingestion (Spec 4) corrected to drive Stage 4 and Stage 7, not Stage 4 alone. Reverse proxy and backups moved from M8 to M0/M1. Jobs run on a Postgres-backed worker.

---

## 0. Build principles

- Foundations one layer at a time, each green before the next: Database → Backend → Frontend. Feature specs after that (Spec 4 onward) may span layers but each piece stays in its layer's folder (constitution VIII.5).
- Every slice goes through the full Spec Kit loop: `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`. (Commands are hyphenated in this install.)
- Commit after each milestone. Branch per spec (`spec/1-database`, `spec/2-backend`, …), PR into `main`.
- Review the generated `plan.md` before running `/speckit-implement`.
- No external accounts or hosted services. Everything runs on the lab server in Docker.

---

## 1. Milestone roadmap

| M | Milestone | Spec | Exit criteria |
| --- | --- | --- | --- |
| **M0** | Environment & scaffold | — | Repo at git root with first commit pushed; Docker running; `/infra` compose with Postgres + Caddy (TLS) + Adminer; monorepo folders; constitution 2.0.0 committed |
| **M1** | Database live | Spec 1 | All tables + triggers + RLS migrated via Alembic; seed loaded (roles, stages, vendors, `system` actor); admin account created through backend CLI; append-only triggers verified; nightly `pg_dump` cron running |
| **M2** | Backend core | Spec 2 (part A) | Native auth (login, refresh, logout, admin-create-user, password reset by admin); RBAC guards; audit middleware; `/auth/me`, users/roles endpoints green; pytest passing |
| **M3** | Backend workflow | Spec 2 (part B) | Samples, checklist, batches, data-gen, QC, TRF, vendors, SLA engine with working-day calendar, `jobs` table + worker; stage-gates enforced by pytest; OpenAPI exported |
| **M4** | Sequencer ingestion | Spec 4 (backend) | Run discovery, basecall download, `bases2fastq` conversion as jobs; run/sample matching; Stage 4 and Stage 7 advanced by the `system` actor; verified via API + pytest (UI arrives in M7) |
| **M5** | Reports + portal push | Spec 2 (part C) | Report upload to `/data/reports` with metadata row; served via backend with RBAC; portal push job with retry; case-close rule |
| **M6** | Frontend shell + auth | Spec 3 (part A) | Next.js app; cookie-session sign-in against backend; role-based routing; Medlabs theme; RTL-safe layout |
| **M7** | Dashboards | Spec 3 (part B) | Admin, Genomics, Molecular, Bioinformatics (incl. sequencing runs view) + shared TAT Kanban, all wired to backend |
| **M8** | Notifications + go-live | Spec 3.1 + ops | SMTP SLA alerts + daily digest; monitoring/log rotation; restore drill from backup; go-live checklist |

M4 sits between M3 and M5: sequencing output must exist before QC and reporting are meaningful.
M6 may start in parallel with M3/M4 once the OpenAPI from M2 exists (the shell doesn't need the workflow endpoints).

---

## 2. M0 — Environment & scaffold (do first)

### Already done

- Spec Kit 1.2.5 installed with the Claude integration (`/speckit-*` skills live).
- Constitution ratified and amended to 2.0.0.
- Git repo initialised with remote `https://github.com/balqees-medlabs/Helixa.git` — **zero commits so far**.

### Repo layout — fix before the first commit

Today `.git` is at `/home/labs/Helixa` and `.specify`/`docs` sit one level down in `/home/labs/Helixa/Helixa/`. Constitution II.6 fixes the monorepo folders at the repo root. Move the contents up so `.specify`, `docs`, and the scaffolded folders are siblings of `.git`, then make the first commit:

```bash
cd /home/labs/Helixa
mv Helixa/.specify Helixa/.claude Helixa/docs . && rmdir Helixa
mkdir -p frontend backend infra specs docs/decisions
git add -A && git commit -m "Scaffold Helixa monorepo, Spec Kit, constitution 2.0.0" && git push -u origin main
```

### Server packages

Debian does not ship `docker-compose-plugin`; use Docker's own apt repo so Engine and Compose v2 match:

```bash
sudo apt update && sudo apt install -y ca-certificates curl git python3 python3-venv
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker labs
sudo mkdir -p /data/reports /data/runs /data/backups && sudo chown -R labs:labs /data
```

### `/infra` (M0 deliverable)

- `compose.yml`: `postgres:16` (volume, bound to `127.0.0.1:5432`), `caddy` (ports 80/443, internal CA TLS, reverse-proxies `/api` → backend, `/` → frontend), `adminer` (internal only, admin tooling). Backend and frontend services are added in M2/M6.
- `Caddyfile` with `tls internal`.
- `backup.sh` + cron line: nightly `pg_dump -Fc` to `/data/backups`, 14-day rotation, rsync of `/data/reports`. `/data/runs` excluded.
- `.env.example` listing every secret/setting (DB password, JWT key, SMTP, portal token, sequencer paths, `bases2fastq` path/threads, retention days). Real `.env` is server-only.

Network note: the server is reached via VPN and the Medlabs LAN. Only Caddy listens on the LAN interface; Postgres, backend, frontend, and Adminer bind to localhost/the compose network.

---

## 3. Execution order per spec

### Spec 1 — Database (→ M1)

1. `/speckit-specify` (Spec 1 block) → `/speckit-plan` → review → `/speckit-tasks` → `/speckit-implement`.
2. Alembic owns `public`. Tables include `users` (with `is_system` flag for the `system` actor), `roles`, `user_roles`, `stages`, `stage_sla`, `working_calendar` (weekend rule + holidays), `samples`, `sample_stage_events`, `audit_log`, `vendors`, `jobs`. Spec 4 tables come later as migration 1.1.
3. RLS policies read the acting user/roles from session settings the backend sets with `SET LOCAL` (constitution III.3). Append-only triggers on `audit_log` and `sample_stage_events`.
4. Seed via migration: 5 roles, 8 stages with default SLAs, 4 vendors, the `system` actor, default calendar. **The human admin is not SQL-seeded** — it needs an argon2 hash, so it's created in M2 by `python -m app.cli create-admin`.
5. **Verify**: UPDATE/DELETE on `audit_log` and `sample_stage_events` rejected for every role; RLS denies a `genomics` session reading admin-only rows; nightly backup produced a restorable dump.

### Spec 2 — Backend (→ M2, M3, M5)

Three PRs so review stays tractable:

- **A (M2):** native auth — argon2 hashing, access JWT (15 min) in httpOnly/Secure/SameSite cookie, rotating refresh token, logout, admin-create-user, admin password reset; RBAC dependency guards; audit middleware (same-transaction, before/after); users/roles CRUD; `/auth/me`; `create-admin` CLI. pytest covers every auth path and guard.
- **B (M3):** samples, consent checklist, batches, data-generation, QC, TRF, vendors; SLA engine with the working-day calendar (18 calendar days incl. Fridays vs 45 working days; Centogene counted from sequencing); TAT metrics; `jobs` table + worker process (`python -m app.worker`, same image, polls `jobs`, heartbeat, retry with backoff). Stage-gate matrix in pytest. Export OpenAPI.
- **C (M5):** report upload to `/data/reports/<case_id>/` with metadata row and checksum; download endpoint with RBAC; portal-push job behind the isolated client (mock until the real endpoint is known); case-close rule. Refresh OpenAPI.

### Spec 4 — Sequencer ingestion (→ M4) — see §4

Backend-only feature spec. Its migration (`sequencing_runs`, `run_samples`) ships as Spec 1.1 alongside; its UI ships inside Spec 3B. Runs after 2B (needs samples, stages, jobs) and before/with 2C.

### Spec 3 — Frontend (→ M6, M7)

- **A (M6):** app shell, theme, RTL-safe layout, cookie-session auth (login form → backend; the browser never sees a token), role routing, typed API client generated from OpenAPI.
- **B (M7):** the four dashboards + TAT Kanban; sequencing runs view with live job status, per-run sample table, manual-match and discover/convert actions.

### Spec 3.1 — Notifications + go-live (→ M8)

SMTP SLA alerts and the daily digest as jobs; log rotation and basic monitoring; restore drill; go-live checklist.

---

## 4. Spec 4 — Sequencer basecall ingestion → FASTQ

**What it does:** pull raw basecall output from the sequencer, convert it on the server to FASTQ, link the FASTQs to Helixa samples, and let real sequencing output drive the workflow instead of a manual toggle.

This mirrors the ElemBio flow: the instrument produces a run folder of basecalls; `bases2fastq` demultiplexes them to per-sample FASTQs using the run's `RunManifest.csv`.

### Stage mapping (constitution V.3)

- Run downloaded and basecalls present for a sample → **Stage 4 (data generation)** complete.
- `bases2fastq` complete for that sample and QC passed → **Stage 7 (data conversion & QC)** complete.
- Stages 5–6 (TRF) sit between. The worker records `run_samples.status = fastq_ready` and advances Stage 7 only once the sample has completed Stage 6; a `fastq_ready` sample waiting on TRF is visible in the UI, not silently advanced.

### Tables (migration 1.1)

- `sequencing_runs` — id, run_name, instrument, source_path, status (`discovered` / `downloading` / `downloaded` / `converting` / `complete` / `failed`), downloaded_at, converted_at, created_at, error.
- `run_samples` — id, run_id, sample_id (FK `samples`, nullable until matched), sample_barcode, fastq_r1_path, fastq_r2_path, read_count, status (`unmatched` / `matched` / `fastq_ready` / `advanced` / `failed`).
- Both carry RLS (bioinformatics + admin) and every status change writes `audit_log` as the `system` actor with the job id.

### Backend module (`/backend/app/sequencing/`)

- **Discovery:** poll (job, configurable interval) or manual trigger. A run folder counts as complete only when the instrument's run-complete marker is present (confirm the exact filename — see §5). Registers a `sequencing_runs` row.
- **Download:** `rsync` from the mounted/SSH source to `/data/runs/<run_name>/basecalls`, resumable, verified by size/checksum manifest. On success, mark Stage 4 for each matched sample.
- **Convert:** `bases2fastq --threads N` on the basecall folder → `/data/runs/<run_name>/fastq`. Parse the output's per-sample stats into `run_samples` (paths, read_count). Wrapped in one module with a mockable interface; tests use a fixture run folder, never the real binary.
- **Match:** `RunManifest.csv` SampleName → `samples.case_id`. Unmatched samples are flagged for manual linking.
- **Advance:** when `fastq_ready` and the sample is past Stage 6, write the Stage 7 event with the FASTQ path as the data-location reference, plus audit entry — same code path as a manual advance.
- **Retention:** basecalls deleted after verified conversion; FASTQs kept `RUN_RETENTION_DAYS` (env). `/data/runs` is excluded from backups.
- All long steps are `jobs` rows processed by the worker; the frontend polls job status.
- Config in `.env`: `SEQUENCER_SOURCE_PATH`, `RUNS_ROOT`, `BASES2FASTQ_BIN`, `BASES2FASTQ_THREADS` (server has 80 CPU), `RUN_RETENTION_DAYS`, discovery interval.

### Frontend (Spec 3B, Bioinformatics dashboard)

- **Runs view:** runs list with live status, per-run sample table with read counts and match state, "fastq_ready, waiting on TRF" indicator.
- **Manual match:** resolve an unmatched run sample to a case ID.
- **Triggers:** discover new runs; start/retry conversion. Bioinformatics and admin only.

### `/speckit-specify` prompt — Spec 4

> Add sequencer ingestion to Helixa as a backend feature. The system downloads raw basecall run folders from the sequencer (ElemBio) to `/data/runs` on the server, converts them to demultiplexed FASTQ with `bases2fastq`, and links results to Helixa samples.
>
> Tables (migration 1.1): `sequencing_runs` (run_name, instrument, source_path, status discovered/downloading/downloaded/converting/complete/failed, timestamps, error) and `run_samples` (run_id, sample_id nullable, sample_barcode, fastq_r1_path, fastq_r2_path, read_count, status unmatched/matched/fastq_ready/advanced/failed). Both have RLS for bioinformatics and admin; every status change writes an `audit_log` row attributed to the `system` actor with the job id.
>
> Backend module in FastAPI using the existing `jobs` worker: (1) discover complete run folders at a configured source path (run-complete marker present) and register a run; (2) rsync basecalls to a staging area, resumable, verifying completion; on success complete Stage 4 (data generation) for each matched sample; (3) run bases2fastq to produce per-sample FASTQs, capturing paths and read counts; (4) match run samples by RunManifest SampleName to a Helixa case_id, flagging unmatched ones; (5) mark a sample `fastq_ready`, and when it has completed Stage 6 advance Stage 7 (data conversion & QC) with the FASTQ path as the data-location reference, writing a stage event and audit entry through the same code path as a manual advance — never advance out of order. Delete basecalls after verified conversion; retain FASTQs for a configurable number of days. The bases2fastq wrapper is one module with a mockable interface; source path, staging root, binary path, threads, and retention come from server .env. Only bioinformatics and admin roles may trigger or manage runs.
>
> Deliverables: Alembic migration 1.1, the sequencing module with jobs and the isolated converter wrapper, pytest for discovery, matching, stage-advance ordering, and retention using a fixture run folder (no real binary or data), and OpenAPI updated. UI is out of scope here (Spec 3B).

---

## 5. Risks & dependencies

- **Portal API (Spec 2C):** endpoint/auth still undefined — stays behind the isolated client; implement against a mock, drop in real details when ready.
- **`bases2fastq` on the server (Spec 4):** must be installed and runnable on Debian Trixie; confirm version and that it needs no network. Tests mock it so implementation isn't blocked.
- **Run folder layout:** confirm the instrument's run-complete marker filename, the `RunManifest.csv` location, and the per-sample stats file `bases2fastq` writes. Discovery and matching depend on all three.
- **Sample naming convention (process, not code):** matching works only if the wet lab enters the Helixa `case_id` as SampleName in the run manifest. Agree this with the molecular team before M4 or everything lands in manual match.
- **Disk:** a run is hundreds of GB; FASTQs are large. Size `/data` accordingly and set `RUN_RETENTION_DAYS` deliberately.
- **Sequencer reachability:** the source must be mountable (SMB/NFS) or reachable over SSH from the server for `rsync`. Confirm before M4.
- **Brand hex (Spec 3A):** pull exact values from the MedLabs logo before theming.
- **Molecular user list:** needed for admin to create accounts in M2 (Ghadeer, Mais, + others).
- **Password resets:** admin-performed in v1 (no self-service email flow). Fine for an internal team; revisit if it becomes a burden.

---

## 6. Next three actions

1. **Repo layout + first commit** (§2): move the nested folder up, scaffold folders, commit, push.
2. **M0 `/infra`**: compose with Postgres + Caddy + Adminer, backup script, `.env.example`. Bring Postgres up.
3. **Spec 1** → `/speckit-specify` with the Spec 1 block, review `plan.md`, migrate and seed, run the M1 verification list.
