from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import require_admin
from app.db.postgres import get_db
from app.db.rag_config import get_rag_config
from app.schemas.rag_config import RagConfigResponse, RagConfigUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


def _build_rag_response(cfg, settings) -> RagConfigResponse:
    data = RagConfigResponse.model_validate(cfg)
    data.openai_api_key_configured = bool(settings.OPENAI_API_KEY)
    data.anthropic_api_key_configured = bool(settings.ANTHROPIC_API_KEY)
    data.google_api_key_configured = bool(settings.GOOGLE_API_KEY)
    return data


@router.get("/rag-parameters", response_model=RagConfigResponse)
async def get_rag_parameters(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> RagConfigResponse:
    cfg = await get_rag_config(db)
    return _build_rag_response(cfg, get_settings())


@router.put("/rag-parameters", response_model=RagConfigResponse)
async def update_rag_parameters(
    body: RagConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> RagConfigResponse:
    cfg = await get_rag_config(db)
    cfg.parent_chunk_tokens = body.parent_chunk_tokens
    cfg.child_chunk_tokens = body.child_chunk_tokens
    cfg.search_top_k = body.search_top_k
    cfg.search_score_threshold = body.search_score_threshold
    cfg.reranker_top_k = body.reranker_top_k
    cfg.reranker_score_threshold = body.reranker_score_threshold
    cfg.hyde_enabled = body.hyde_enabled
    cfg.multiquery_enabled = body.multiquery_enabled
    cfg.reranker_enabled = body.reranker_enabled
    cfg.contextual_compression_enabled = body.contextual_compression_enabled
    cfg.parent_child_expansion_enabled = body.parent_child_expansion_enabled
    cfg.llm_provider = body.llm_provider
    cfg.llm_model = body.llm_model
    cfg.embedding_provider = body.embedding_provider
    cfg.embedding_model = body.embedding_model
    cfg.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(cfg)
    return _build_rag_response(cfg, get_settings())
