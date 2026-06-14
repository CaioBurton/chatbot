# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**PROPESQI RAG Chatbot** — an on-premise institutional Q&A system for UFPI (Universidade Federal do Piauí). Runs entirely on local hardware (NVIDIA RTX 5060 Ti 16 GB) with no external API calls. Uses retrieval-augmented generation (RAG) over institutional documents.

See `AGENTS.md` for architecture conventions and `DOCUMENTATION.md` for full technical reference.

---

## Commands

### Backend
```bash
# From backend/
pip install -r requirements.txt

# Latency tests (in-process ASGI, no running server required)
pytest tests/latency/ -v

# Load tests (requires full Docker stack running)
locust -f tests/load/locustfile.py --host http://localhost:8000 \
       --users 20 --spawn-rate 5 --run-time 2m --headless
```

### Frontend
```bash
# From frontend/
npm install
npm run dev      # dev server with hot reload
npm run build    # production build (tsc + vite build → dist/)
```

### Docker (full stack)
```bash
# With GPU support (NVIDIA)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# CPU-only
docker compose up -d
```

Generate `SECRET_KEY`:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Architecture

```
Frontend (React/Vite/TS) → Nginx :3000 → /api proxy → Backend (FastAPI) :8000
                                                              ↓
                                              PostgreSQL 16 (relational)
                                              Qdrant (vector DB)
                                              Ollama (LLM + embeddings)
```

**RAG Pipeline** (`backend/app/core/rag_engine.py`):
`Query normalization → HyDE → Multi-query expansion → Hybrid Search (RRF) → Rerank → Contextual compression → LLM streaming (SSE)`

| Layer            | Technology                                          |
|------------------|-----------------------------------------------------|
| Frontend         | React 18 + Vite + TypeScript + Tailwind CSS         |
| Backend          | FastAPI (Python 3.11+) + SQLAlchemy 2.0 async       |
| Relational DB    | PostgreSQL 16 (schema: `init/01_schema.sql`)        |
| Vector DB        | Qdrant (named vectors: `dense` + `sparse`)          |
| LLM / Embeddings | Ollama → `gemma3:12b` / `bge-m3`                   |
| Reranker         | `BAAI/bge-reranker-v2-m3` (sentence-transformers, CPU) |
| Sparse encoder   | fastembed BM42                                      |
| Infrastructure   | Docker Compose + GPU overlay                        |

### Key Files

- `backend/app/main.py` — FastAPI app entry point, lifespan setup
- `backend/app/core/config.py` — Settings (singleton via `@lru_cache`)
- `backend/app/core/rag_engine.py` — Full RAG pipeline with SSE streaming
- `backend/app/core/security.py` — JWT auth (access 60 min / refresh 7 days)
- `backend/app/core/progress.py` — SSE indexing progress publisher
- `backend/app/db/qdrant.py` — Qdrant collection management + named vector constants
- `backend/app/db/postgres.py` — `AsyncSessionLocal` factory
- `backend/app/db/rag_config.py` — Runtime-adjustable RAG parameters (from DB)
- `backend/app/api/routes/` — `auth`, `chat`, `documents`, `admin`, `evaluation`
- `frontend/nginx.conf` — Nginx reverse proxy (`/api` → backend:8000)
- `init/01_schema.sql` — Database schema init

### API Routes

- `/api/auth/*` — Login, token refresh (public)
- `/api/chat/*` — Q&A streaming (public, no auth)
- `/api/documents/*` — Upload, manage, reindex documents (JWT required)
- `/api/admin/*` — RAG config and stats panel (JWT required)
- `/api/evaluation/*` — RAGAS evaluation metrics (JWT required)
- `/ws` — WebSocket for indexing progress events
- `/health` — Health check

---

## Critical Conventions

### Qdrant — Named Vectors
Always use the constants; never pass unnamed (legacy) vectors — it silently breaks hybrid search:
```python
from app.db.qdrant import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME  # "dense" / "sparse"
```
If the collection exists with an old single-vector config, `ensure_collection()` **drops and recreates it** — all indexed data is lost. Back up before migrating.

### Settings Singleton
Always call `get_settings()`. Never instantiate `Settings()` directly. `SECRET_KEY` must be ≥ 32 characters — validation raises at startup.

### SQLAlchemy — Async Only
All DB interactions must use `AsyncSession` + `asyncpg`. Never mix in synchronous `psycopg2` calls.

### RAG Config — Runtime-Adjustable
Reranker threshold, HyDE temperature, and other RAG parameters are stored in PostgreSQL and read via `app/db/rag_config.py`. The admin panel modifies them without restarting the service.

### Indexing Progress
Publish progress events via `app/core/progress.py` (SSE). The frontend consumes them over `/ws`. Do not use `print()` or logging to report indexing progress to the client.

### pytest — Automatic Asyncio
`pyproject.toml` sets `asyncio_mode = "auto"`. All `async def` tests run automatically. `conftest.py` sets `os.environ.setdefault` before any app module is imported.

### Dependencies
- `bcrypt` is pinned to `>=3.0,<4.0` in `requirements.txt`. bcrypt 4+ has a different API that breaks `passlib`. Do not upgrade without testing.
- fastembed BM42 downloads ~100 MB on first run. In offline environments, pre-download or mount the cache as a Docker volume.
- RAGAS evaluation (`/api/evaluation/*`) calls Ollama internally. Do not run evaluations when Ollama is unavailable.
- Ollama runs with `OLLAMA_NUM_PARALLEL=1` to prevent concurrent inference OOM on the 16 GB VRAM GPU.

### OCR
PDFs with scanned images go through OpenCV + Tesseract. Upload timeouts should be set well above 5 minutes for large scanned PDFs.
