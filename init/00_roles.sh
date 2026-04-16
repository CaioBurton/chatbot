#!/usr/bin/env bash
# =============================================================================
# init/00_roles.sh — Create limited-privilege PostgreSQL application role
#
# Strategy:
#   Step 1 — Create the role idempotently using a DO $$ block (no password).
#
#   Step 2 — Set the password via ALTER ROLE using shell variable expansion.
#             Single quotes in the password are SQL-escaped by doubling them
#             (PostgreSQL standard_conforming_strings, default since PG 9.1).
#             This avoids relying on psql client-variable (:'var') substitution,
#             which does not work reliably inside Docker Alpine init scripts.
# =============================================================================
set -euo pipefail

# ---- Step 1: create the role (no password needed here) ---------------------
psql \
    -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname   "$POSTGRES_DB" \
    <<'SQL'
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_catalog.pg_roles WHERE rolname = 'propesqi_app'
    ) THEN
        CREATE ROLE propesqi_app
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE;
    END IF;
END
$$;
SQL

# ---- Step 2: set the password (shell-escaped for SQL) ----------------------
# Replace every ' with '' (SQL literal escaping). No other characters need
# escaping in PostgreSQL standard_conforming_strings mode (default since 9.1).
escaped_pw="${PROPESQI_APP_PASSWORD//\'/\'\'}"

psql \
    -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname   "$POSTGRES_DB" \
    -c "ALTER ROLE propesqi_app ENCRYPTED PASSWORD '${escaped_pw}';"

# ---- Step 3: grant connection to the application database ------------------
psql \
    -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname   "$POSTGRES_DB" \
    -c "GRANT CONNECT ON DATABASE \"${POSTGRES_DB}\" TO propesqi_app;"

echo "[00_roles.sh] propesqi_app role ready."
