#!/usr/bin/env bash
# Provision the non-superuser application role (helixa_app) for the backend.
# Credentials come from infra/.env — never from a migration (constitution III.4).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/.env"
  set +a
fi

: "${DATABASE_URL:?DATABASE_URL must be set (admin connection, see infra/.env.example)}"
: "${APP_DB_USER:?APP_DB_USER must be set (see infra/.env.example)}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set (see infra/.env.example)}"

# Idempotent, non-superuser, no BYPASSRLS. The credentials are read by psql from
# the environment via \getenv, so they never appear in the process list (argv);
# log_statement is silenced for this session so the DDL (with the password) is not
# written to the Postgres server log (constitution III.4). format() with %I/%L
# quotes the identifier and password safely regardless of their contents.
# psql needs a plain libpq URL — DATABASE_URL is kept as postgresql:// for exactly
# this reason (SQLAlchemy adds the +psycopg driver itself).
export APP_DB_USER APP_DB_PASSWORD
psql -v ON_ERROR_STOP=1 -q "$DATABASE_URL" <<'SQL'
SET log_statement = 'none';
SET client_min_messages = 'warning';
\getenv role APP_DB_USER
\getenv pw APP_DB_PASSWORD
SELECT format(
  '%s ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS',
  CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role')
       THEN 'ALTER' ELSE 'CREATE' END,
  :'role', :'pw'
) AS stmt \gset
:stmt ;
SQL

echo "role '$APP_DB_USER' provisioned"
