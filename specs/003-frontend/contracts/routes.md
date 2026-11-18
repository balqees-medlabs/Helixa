# Contract: Route Map

**Feature**: 003-frontend · The app's URL surface (Next.js App Router). `(auth)` is public; everything under `(app)` requires a session (middleware redirects to `/login` when the access cookie is absent; the layout confirms via `/auth/me`). Nav and in-page actions are shown per the user's roles; the backend still enforces.

| Route | Purpose | Visible to (UI) | Key backend calls |
|---|---|---|---|
| `/login` | sign in | public | `POST /auth/login` |
| `/dashboard` | role work-queue dashboard + switcher | any role (content per role) | `/auth/me`, `/samples`, `/metrics/tat` |
| `/board` | shared TAT Kanban (8 stage columns) | any role | `/samples`, `/metrics/tat`, `POST /samples/{id}/advance` |
| `/samples` | sample list | any role | `GET /samples` |
| `/samples/register` | register a sample | genomics, admin | `POST /samples` |
| `/samples/{id}` | detail + history + advance + consent | any role (actions gated) | `/samples/{id}`, `/events`, `/consent`, `/advance` |
| `/batches` | create, add members, batch advance | batch roles, admin | `/batches*` |
| `/qc` | QC / data-generation entry | bioinformatics, admin | `POST /samples/{id}/qc` |
| `/vendors` | vendor list (+ admin manage) | any (read), admin (write) | `/vendors*` |
| `/reports` | upload, retrieve, portal status + retry | admin/bioinformatics/genomics (read); bioinformatics (upload); admin (retry) | `/samples/{id}/report`, `/reports/{id}*`, `/portal-pushes/{id}*` |
| `/metrics` | turnaround metrics | admin | `/metrics/tat`, `PATCH /stages/{id}/sla` |

Unauthenticated access to any `(app)` route → redirect to `/login`, return after auth (FR-002). An action the user's roles don't permit is not offered; a direct attempt still fails at the backend (403).
