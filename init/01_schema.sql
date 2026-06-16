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
    display_name    TEXT,                                    -- admin-provided name shown in the UI (defaults to original_name)
    source_url      TEXT,                                    -- optional external link to the source document
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

-- Migration: add display_name/source_url to existing deployments (idempotent)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_url   TEXT;
UPDATE documents SET display_name = original_name WHERE display_name IS NULL;

-- Migration: add doc_type to existing deployments (idempotent)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_type TEXT NOT NULL DEFAULT 'edital';

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
-- rag_evaluations
-- Persists RAGAS metric scores from admin-triggered evaluation runs.
-- metadata stores raw per-sample scores and any per-run errors as JSONB.
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_evaluations (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_name        TEXT        NOT NULL,
    faithfulness        FLOAT,
    answer_relevancy    FLOAT,
    context_precision   FLOAT,
    context_recall      FLOAT,
    answer_correctness  FLOAT,
    num_samples         INTEGER     NOT NULL CHECK (num_samples >= 1),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata            JSONB
);

CREATE INDEX IF NOT EXISTS idx_rag_evaluations_created_at
    ON rag_evaluations (created_at DESC);

-- =============================================================================
-- rag_config
-- Single-row table (id must always equal 1) for runtime-adjustable RAG params.
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_config (
    id                              INT         PRIMARY KEY DEFAULT 1,
    parent_chunk_tokens             INT         NOT NULL DEFAULT 512,
    child_chunk_tokens              INT         NOT NULL DEFAULT 128,
    search_top_k                    INT         NOT NULL DEFAULT 20,
    search_score_threshold          FLOAT       NOT NULL DEFAULT 0.0,
    reranker_top_k                  INT         NOT NULL DEFAULT 5,
    reranker_score_threshold        FLOAT       NOT NULL DEFAULT 0.5,
    hyde_enabled                    BOOLEAN     NOT NULL DEFAULT TRUE,
    multiquery_enabled              BOOLEAN     NOT NULL DEFAULT TRUE,
    reranker_enabled                BOOLEAN     NOT NULL DEFAULT TRUE,
    contextual_compression_enabled  BOOLEAN     NOT NULL DEFAULT TRUE,
    parent_child_expansion_enabled  BOOLEAN     NOT NULL DEFAULT TRUE,
    llm_provider                    VARCHAR(32) NOT NULL DEFAULT 'local'
                    CHECK (llm_provider IN ('local', 'openai', 'anthropic', 'gemini')),
    llm_model                       VARCHAR(128) NOT NULL DEFAULT 'gemma3:12b',
    embedding_provider              VARCHAR(32) NOT NULL DEFAULT 'local'
                    CHECK (embedding_provider IN ('local', 'gemini')),
    embedding_model                 VARCHAR(128) NOT NULL DEFAULT 'bge-m3',
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT rag_config_single_row CHECK (id = 1)
);

-- Migration: add toggle columns to existing deployments (idempotent)
ALTER TABLE rag_config ADD COLUMN IF NOT EXISTS hyde_enabled                   BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE rag_config ADD COLUMN IF NOT EXISTS multiquery_enabled             BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE rag_config ADD COLUMN IF NOT EXISTS reranker_enabled               BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE rag_config ADD COLUMN IF NOT EXISTS contextual_compression_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE rag_config ADD COLUMN IF NOT EXISTS parent_child_expansion_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE rag_config ADD COLUMN IF NOT EXISTS llm_provider                   VARCHAR(32) NOT NULL DEFAULT 'local'
    CONSTRAINT rag_config_llm_provider_check CHECK (llm_provider IN ('local', 'openai', 'anthropic', 'gemini'));
ALTER TABLE rag_config ADD COLUMN IF NOT EXISTS llm_model                      VARCHAR(128) NOT NULL DEFAULT 'gemma3:12b';
ALTER TABLE rag_config ADD COLUMN IF NOT EXISTS embedding_provider             VARCHAR(32) NOT NULL DEFAULT 'local'
    CONSTRAINT rag_config_embedding_provider_check CHECK (embedding_provider IN ('local', 'gemini'));
ALTER TABLE rag_config ADD COLUMN IF NOT EXISTS embedding_model                VARCHAR(128) NOT NULL DEFAULT 'bge-m3';
ALTER TABLE rag_config ADD COLUMN IF NOT EXISTS context_top_k                  INTEGER NOT NULL DEFAULT 5;

INSERT INTO rag_config (id, parent_chunk_tokens, child_chunk_tokens, search_top_k,
                        search_score_threshold, reranker_top_k, reranker_score_threshold,
                        hyde_enabled, multiquery_enabled, reranker_enabled,
                        contextual_compression_enabled, parent_child_expansion_enabled,
                        llm_provider, llm_model, embedding_provider, embedding_model, updated_at)
VALUES (1, 512, 128, 20, 0.0, 5, 0.5, TRUE, TRUE, TRUE, TRUE, TRUE, 'local', 'gemma3:12b', 'local', 'bge-m3', NOW())
ON CONFLICT (id) DO NOTHING;

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
