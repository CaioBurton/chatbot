#!/usr/bin/env bash
# =============================================================================
# init/02_seed_admin.sh — Seed the first admin user (idempotent)
#
# Runs after 01_schema.sql creates the `users` table. Creates one admin
# account from ADMIN_EMAIL / ADMIN_PASSWORD (set in .env), so a fresh
# deployment always has a working login without a manual INSERT.
#
# The bcrypt hash is generated with pgcrypto's crypt()/gen_salt('bf', 12),
# which produces a "$2a$12$..." hash. passlib's bcrypt scheme (used by
# app/api/routes/auth.py) verifies "$2a$" hashes identically to "$2b$", so
# this is fully compatible with the backend's login check.
#
# Skips silently if ADMIN_EMAIL or ADMIN_PASSWORD is not set, or if a user
# with that email already exists.
# =============================================================================
set -euo pipefail

if [ -z "${ADMIN_EMAIL:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
    echo "[02_seed_admin.sh] ADMIN_EMAIL/ADMIN_PASSWORD not set — skipping admin seed."
    exit 0
fi

# Escape single quotes for SQL string literals.
escaped_email="${ADMIN_EMAIL//\'/\'\'}"
escaped_password="${ADMIN_PASSWORD//\'/\'\'}"

psql \
    -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname   "$POSTGRES_DB" \
    <<SQL
CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO users (email, password_hash, role)
VALUES (
    '${escaped_email}',
    crypt('${escaped_password}', gen_salt('bf', 12)),
    'admin'
)
ON CONFLICT (email) DO NOTHING;
SQL

echo "[02_seed_admin.sh] admin user '${ADMIN_EMAIL}' ready."
