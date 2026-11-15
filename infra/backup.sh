#!/usr/bin/env bash
# Routine (nightly) database backup — M0 deliverable, per SC-006/FR-017.
# Produces a custom-format dump (pg_dump -Fc) that pg_restore can restore
# into a fresh copy; see infra/restore-check.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/.env"
  set +a
fi

: "${DATABASE_URL:?DATABASE_URL must be set (admin connection, see infra/.env.example)}"

# The dump goes to /data/backups per the implementation plan; override with
# BACKUP_DIR for other environments.
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
mkdir -p "${BACKUP_DIR}"

# Parse DATABASE_URL into libpq's PG* environment variables so the password
# never appears in a process argument (constitution III.4, as in
# bootstrap-app-role.sh). Supports user[:password]@host[:port]/db; without
# credentials the OS-level auth (peer/trust) is used.
if [[ "$DATABASE_URL" =~ ^postgresql://([^:@/]+):([^@/]*)@([^:/]+)(:([0-9]+))?/([^?/]+) ]]; then
  export PGUSER="${BASH_REMATCH[1]}" PGPASSWORD="${BASH_REMATCH[2]}"
  export PGHOST="${BASH_REMATCH[3]}" PGDATABASE="${BASH_REMATCH[6]}"
  [[ -n "${BASH_REMATCH[5]:-}" ]] && export PGPORT="${BASH_REMATCH[5]}"
elif [[ "$DATABASE_URL" =~ ^postgresql://(([^:@/]+)@)?([^:@/]+)(:([0-9]+))?/([^?/]+) ]]; then
  # No password in the URL (peer/trust auth); the user is optional.
  [[ -n "${BASH_REMATCH[2]:-}" ]] && export PGUSER="${BASH_REMATCH[2]}"
  export PGHOST="${BASH_REMATCH[3]}" PGDATABASE="${BASH_REMATCH[6]}"
  [[ -n "${BASH_REMATCH[5]:-}" ]] && export PGPORT="${BASH_REMATCH[5]}"
else
  echo "backup.sh: cannot parse DATABASE_URL (expected postgresql://[user[:pass]@]host[:port]/db)" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/helixa-${STAMP}.dump"

pg_dump -Fc --no-owner --no-privileges -f "${OUT}"

# The dump path on the last line of stdout (restore-check.sh consumes it).
echo "${OUT}"
