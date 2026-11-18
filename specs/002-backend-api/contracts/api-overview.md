# Contract: API Overview

**Feature**: 002-backend-api · The HTTP surface the frontend (Spec 3) consumes. The authoritative machine-readable form is the exported `backend/openapi.json` (D9); this is the human map. All routes except `POST /auth/login` and `POST /auth/refresh` require a valid access-token cookie; all are internal-network only (Constitution III.5).

## Conventions

- **Auth**: access JWT in an `HttpOnly; Secure; SameSite=Lax` cookie; refresh token in a second HttpOnly cookie scoped to `/auth`. No tokens in response bodies.
- **Errors**: JSON `{ "detail": "<reason>" }`. `401` unauthenticated/expired, `403` role denied, `404` not found/hidden by RLS, `409` concurrency conflict or gate violation surfaced as conflict, `422` validation, `413` file too large, `415` unsupported media type.
- **Audit/identity**: every request sets `app.user_id`/`app.role_names` before touching data (D2); writes are audited by Spec 1 triggers.

## Routes by user story

### US1 — auth, users, roles
| Method & path | Roles | Purpose |
|---|---|---|
| `POST /auth/login` | public | credentials → set session cookies |
| `POST /auth/refresh` | valid refresh | rotate refresh, reissue access |
| `POST /auth/logout` | any | revoke refresh family, clear cookies |
| `GET /auth/me` | any | current user + roles |
| `GET/POST /users`, `PATCH /users/{id}` | admin | list/create/update accounts |
| `POST /users/{id}/roles`, `DELETE /users/{id}/roles/{slug}` | admin | assign/revoke roles |
| `GET /roles` | any | list the 5 roles |

### US2 — samples & workflow
| Method & path | Roles | Purpose |
|---|---|---|
| `POST /samples` | genomics, admin | register a sample at stage 1 |
| `GET /samples`, `GET /samples/{id}` | any role | list/read (RLS-scoped) |
| `GET /samples/{id}/events` | any role | stage history |
| `POST /samples/{id}/consent` | genomics, admin | set consent-item completeness |
| `POST /samples/{id}/advance` | stage-role (D3) | advance one stage; body carries `from_stage` for the optimistic-concurrency guard; `409` on stale/gate |

### US3 — batches, QC, vendors, metrics
| Method & path | Roles | Purpose |
|---|---|---|
| `POST /batches`, `POST /batches/{id}/members` | relevant roles | group samples |
| `POST /batches/{id}/advance` | stage-role | advance members one stage; per-member result list |
| `POST /samples/{id}/qc` | bioinformatics, admin | record data_generation / qc outcome |
| `GET/POST /vendors`, `PATCH /vendors/{id}` | admin (write), any (read) | manage vendors |
| `GET /metrics/tat` | admin | turnaround vs targets (internal + per-vendor) |
| `PATCH /stages/{id}/sla` | admin | change a stage SLA (future only) |

### US4 — reports & portal
| Method & path | Roles | Purpose |
|---|---|---|
| `POST /samples/{id}/report` | bioinformatics, admin | upload report (QC-gated, type/size checked) → creates push |
| `GET /reports/{id}` / `GET /reports/{id}/file` | admin, bioinformatics, genomics | metadata / stream file |
| `GET /portal-pushes/{id}` | admin | push status |
| `POST /portal-pushes/{id}/retry` | admin | re-queue a failed push |

See `auth-contract.md`, `workflow-contract.md`, `reports-portal-contract.md` for the detailed behaviors.
