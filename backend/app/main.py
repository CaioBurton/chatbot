from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.evaluation import router as evaluation_router
from app.api.routes.ws import router as ws_router
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.qdrant import ensure_collection

settings = get_settings()


async def _warmup() -> None:
    """Pre-load all inference models at startup so the first user request is fast."""
    import asyncio
    from app.core.embeddings import generate_dense_embeddings
    from app.db.postgres import AsyncSessionLocal
    from app.db.rag_config import get_rag_config
    from app.db.reranker import rerank
    from app.ingestion.sparse import get_sparse_encoder
    from qdrant_client.models import ScoredPoint

    # Only warm the Ollama dense-embedding model when it's actually the
    # configured provider — avoids a pointless call to a local Ollama service
    # that may not exist (e.g. Gemini-only cloud deployments).
    async def _warm_bge():
        try:
            async with AsyncSessionLocal() as db:
                cfg = await get_rag_config(db)
            if cfg.embedding_provider != "local":
                return
            await generate_dense_embeddings(
                ["warmup"], provider="local", model=cfg.embedding_model, settings=settings
            )
        except Exception:
            pass

    async def _warm_bm42():
        try:
            await get_sparse_encoder()
        except Exception:
            pass

    await asyncio.gather(_warm_bge(), _warm_bm42())

    # CrossEncoder reranker (PyTorch on GPU) — after embeddings are ready
    try:
        dummy = ScoredPoint(id="00000000-0000-0000-0000-000000000000", version=0, score=0.0, payload={"parent_text": "warmup"})
        await rerank("warmup", [dummy], top_k=1, score_threshold=0.0)
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await ensure_collection()
    await _warmup()
    yield


app = FastAPI(
    title="PROPESQI RAG Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(ws_router)
app.include_router(evaluation_router)
app.include_router(admin_router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
