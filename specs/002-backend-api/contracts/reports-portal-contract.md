# Contract: Reports & Portal Push

**Feature**: 002-backend-api · Traces FR-016..FR-019, SC-006/007/009, research D6/D7.

## Report upload (`POST /samples/{id}/report`, multipart)
- Rejected `409` unless the sample has a passing `qc` result (FR-016).
- Rejected `415` if the content type is not in the allowlist (default `application/pdf`); `413` if over the max size (default 50 MB) — both **before** anything is written to disk.
- On accept: stream to `REPORTS_ROOT/<case_id>/<uuid>-<filename>`, compute SHA-256, write a `reports` row, and create a `portal_pushes` row (`status=queued`) + enqueue a `jobs` row `kind='portal_push'`.

## Report retrieval
- `GET /reports/{id}` (metadata) and `GET /reports/{id}/file` (stream) require one of the reader roles (`admin`, `bioinformatics`, `genomics`) and pass RLS; any other role → `403`. 100% of unauthorized retrievals refused (SC-007).

## Portal push (worker + `portal_pushes`)
- The `jobs` worker leases `portal_push` jobs, sets the system actor + `app.job_id`, and calls `PortalClient.push(report)` behind one interface; the default implementation is a **mock** (configurable base URL/token from `.env`, absent by default).
- Failure → `status=failed`, `last_error`, `attempts++`, `next_attempt_at` backoff; retried up to a configurable cap. `POST /portal-pushes/{id}/retry` re-queues a failed push.
- Idempotent: a push with `delivered_at` set is never re-sent; `UNIQUE(report_id)` ensures one delivery per report (SC-006).
- The rest of the system functions with the portal unavailable — uploads succeed and pushes queue (FR-018).

## Case close
- When a push reaches `status='success'` (`delivered_at` set), the owning sample is marked `status='closed'` and the final state recorded (FR-019). A push still queued/failed/retrying leaves the case open (SC-009).

## Verification hooks
- upload for a non-QC sample → 409; wrong type → 415; oversize → 413; unauthorized file GET → 403/404; mock push fails then retry → success with no duplicate; case closes only after success.
