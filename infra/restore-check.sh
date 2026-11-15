#!/usr/bin/env bash
# Restore check — the automated equivalent of quickstart.md §7 (SC-006):
# run infra/backup.sh, pg_restore the dump into a scratch database, and diff
# the row counts of every table against the source. Exits non-zero if the
# restore is missing data.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/.env"
  set +a
fi

: "${DATABASE_URL:?DATABASE_URL must be set (admin connection, see infra/.env.example)}"

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
  echo "restore-check.sh: cannot parse DATABASE_URL (expected postgresql://[user[:pass]@]host[:port]/db)" >&2
  exit 1
fi

RESTORE_DB="${RESTORE_DB:-helixa_restore_check}"
if [[ ! "$RESTORE_DB" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "restore-check.sh: RESTORE_DB must be alphanumeric/underscore, got '$RESTORE_DB'" >&2
  exit 1
fi

echo "Taking a backup…" >&2
DUMP="$("${SCRIPT_DIR}/backup.sh" | tail -n1)"
echo "Backup: ${DUMP}" >&2

# Recreate the scratch database from scratch (requires admin connection).
(
  export PGDATABASE=postgres
  psql -v ON_ERROR_STOP=1 -q <<SQL
DROP DATABASE IF EXISTS ${RESTORE_DB} WITH (FORCE);
CREATE DATABASE ${RESTORE_DB};
SQL
)

echo "Restoring into ${RESTORE_DB}…" >&2
pg_restore --no-owner --no-privileges -d "${RESTORE_DB}" "${DUMP}"

ROW_COUNTS_SQL=$(cat <<'SQL'
SELECT 'audit_log', count(*) FROM audit_log
UNION ALL SELECT 'holidays', count(*) FROM holidays
UNION ALL SELECT 'jobs', count(*) FROM jobs
UNION ALL SELECT 'roles', count(*) FROM roles
UNION ALL SELECT 'sample_stage_events', count(*) FROM sample_stage_events
UNION ALL SELECT 'samples', count(*) FROM samples
UNION ALL SELECT 'stage_sla', count(*) FROM stage_sla
UNION ALL SELECT 'stages', count(*) FROM stages
UNION ALL SELECT 'user_roles', count(*) FROM user_roles
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'vendors', count(*) FROM vendors
UNION ALL SELECT 'working_calendar', count(*) FROM working_calendar
ORDER BY 1;
SQL
)

SOURCE_COUNTS="$(psql -At -v ON_ERROR_STOP=1 -c "${ROW_COUNTS_SQL}")"
RESTORED_COUNTS="$(PGDATABASE="${RESTORE_DB}" psql -At -v ON_ERROR_STOP=1 -c "${ROW_COUNTS_SQL}")"

if [[ "${SOURCE_COUNTS}" == "${RESTORED_COUNTS}" ]]; then
  echo "OK: restored row counts match the source (${SOURCE_COUNTS//$'\n'/ })" >&2
  echo "${DUMP}"
else
  echo "FAIL: source and restored row counts differ" >&2
  diff <(echo "${SOURCE_COUNTS}") <(echo "${RESTORED_COUNTS}") >&2 || true
  exit 1
fi
