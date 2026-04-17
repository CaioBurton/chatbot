from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.postgres import get_db
from app.db.rag_config import get_rag_config
from app.schemas.rag_config import RagConfigResponse, RagConfigUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/rag-parameters", response_model=RagConfigResponse)
async def get_rag_parameters(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> RagConfigResponse:
    cfg = await get_rag_config(db)
    return RagConfigResponse.model_validate(cfg)


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
    cfg.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(cfg)
    return RagConfigResponse.model_validate(cfg)
