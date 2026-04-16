-- =============================================================================
-- PROPESQI RAG Chatbot — PostgreSQL 16 Schema Initialisation
-- =============================================================================
-- This script is executed once by the postgres container on first startup
-- (mounted at /docker-entrypoint-initdb.d/01_schema.sql).
-- It is idempotent: all objects use CREATE ... IF NOT EXISTS.
-- =============================================================================

-- uuid_generate_v4() requires the pgcrypto / uuid-ossp extension.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- documents
-- Tracks every file uploaded to the system and its processing lifecycle.
-- =============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename        TEXT        NOT NULL,                    -- storage filename (sanitised)
    original_name   TEXT        NOT NULL,                    -- original upload filename
    file_hash       TEXT        NOT NULL UNIQUE,          -- SHA-256 hex digest for dedup (unique: no duplicate content)
    file_type       TEXT        NOT NULL
                    CHECK (file_type IN (
                        'pdf_native',
                        'pdf_scanned',
                        'docx',
                        'odt',
                        'txt',
                        'md'       -- §6.2: TXT/MD handled natively
                    )),
    ocr_applied     BOOLEAN     NOT NULL DEFAULT FALSE,
    status          TEXT        NOT NULL DEFAULT 'uploaded'
                    CHECK (status IN (
                        'uploaded',    -- initial state after upload API call
                        'pending',     -- §7.1: partial reindexation targets this state
                        'processing',
                        'indexed',
                        'active',
                        'error'
                    )),
    error_message   TEXT,                                    -- populated when status = 'error'
    retry_count     INTEGER     NOT NULL DEFAULT 0           -- max 3 retries (enforced in app)
                    CHECK (retry_count >= 0),
    total_chunks    INTEGER     CHECK (total_chunks >= 0),   -- set after indexing completes
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- chunks
-- Mirrors the Qdrant point metadata so SQL queries can join doc ↔ chunk.
-- The authoritative vector data lives in Qdrant; this table holds references.
-- =============================================================================
CREATE TABLE IF NOT EXISTS chunks (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id   UUID        NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    qdrant_id     UUID        NOT NULL UNIQUE,           -- Qdrant point ID (must be unique UUID)
    page_number   INTEGER     CHECK (page_number > 0),
    chunk_index   INTEGER     NOT NULL CHECK (chunk_index >= 0),
    text_preview  TEXT,                               -- first 200 chars for admin UI
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- chat_sessions
-- One session per conversation thread; user_id is NULL for unauthenticated
-- public users (the chat UI is publicly accessible per §8.1 of the plan).
-- =============================================================================
CREATE TABLE IF NOT EXISTS chat_sessions (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID,                               -- NULL = anonymous public user
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- chat_messages
-- Immutable append-only log of every turn in a session.
-- sources stores the retrieval provenance as a JSON array:
--   [{"doc_id": "...", "page": 3, "score": 0.87}, ...]
-- =============================================================================
CREATE TABLE IF NOT EXISTS chat_messages (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  UUID        NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    role        TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT        NOT NULL,
    sources     JSONB,                               -- NULL for user turns
    feedback    TEXT        CHECK (feedback IN ('up', 'down')),  -- NULL until rated
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- users
-- Admin accounts only.  Public chat access requires no account.
-- Password hashing (bcrypt) is handled in application code; never stored plain.
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT        NOT NULL UNIQUE,
    password_hash   TEXT        NOT NULL,
    role            TEXT        NOT NULL DEFAULT 'admin'
                    CHECK (role IN ('admin', 'superadmin')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- Indexes
-- =============================================================================

-- Fast lookup of documents by processing status (e.g., pending reindexation)
CREATE INDEX IF NOT EXISTS idx_documents_status
    ON documents (status);

-- Deduplication check: look up by content hash before re-processing
CREATE INDEX IF NOT EXISTS idx_documents_file_hash
    ON documents (file_hash);

-- Retrieve all chunks for a given document (e.g., on document deletion)
CREATE INDEX IF NOT EXISTS idx_chunks_document_id
    ON chunks (document_id);

-- Fetch conversation history for a session (most recent first)
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id_created
    ON chat_messages (session_id, created_at DESC);

-- Look up sessions owned by an authenticated admin user
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id
    ON chat_sessions (user_id)
    WHERE user_id IS NOT NULL;

-- =============================================================================
-- Trigger: keep documents.updated_at current on every UPDATE
-- =============================================================================
CREATE OR REPLACE FUNCTION _set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION _set_updated_at();

-- =============================================================================
-- Privilege grants for the limited-privilege application role
-- propesqi_app is created by init/00_roles.sh (runs before this script).
-- The backend service connects as propesqi_app (not the superuser).
-- Grants cover all existing tables/sequences AND future ones (Alembic).
-- =============================================================================

GRANT USAGE ON SCHEMA public TO propesqi_app;

-- DML on all current tables
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO propesqi_app;

-- Allow UUID sequence usage for INSERT
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO propesqi_app;

-- Ensure Alembic-created tables are also accessible (forward-compatible)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO propesqi_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO propesqi_app;
