from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag_config import RagConfig


async def get_rag_config(db: AsyncSession) -> RagConfig:
    result = await db.execute(select(RagConfig).where(RagConfig.id == 1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = RagConfig(
            id=1,
            parent_chunk_tokens=512,
            child_chunk_tokens=128,
            search_top_k=20,
            search_score_threshold=0.0,
            reranker_top_k=5,
            reranker_score_threshold=0.5,
            context_top_k=5,
            hyde_enabled=True,
            multiquery_enabled=True,
            reranker_enabled=True,
            contextual_compression_enabled=True,
            parent_child_expansion_enabled=True,
            llm_provider="local",
            llm_model="gemma3:12b",
            embedding_provider="local",
            embedding_model="bge-m3",
            updated_at=datetime.now(timezone.utc),
        )
        db.add(cfg)
        try:
            await db.commit()
            await db.refresh(cfg)
        except IntegrityError:
            # Another request already inserted the row concurrently.
            await db.rollback()
            result = await db.execute(select(RagConfig).where(RagConfig.id == 1))
            cfg = result.scalar_one()
    return cfg
