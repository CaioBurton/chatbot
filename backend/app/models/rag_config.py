from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, Float, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP

from app.models.document import Base


class RagConfig(Base):
    __tablename__ = "rag_config"
    __table_args__ = (CheckConstraint("id = 1", name="rag_config_single_row"),)

    id = Column(Integer, primary_key=True, default=1)
    parent_chunk_tokens = Column(Integer, nullable=False, default=512)
    child_chunk_tokens = Column(Integer, nullable=False, default=128)
    search_top_k = Column(Integer, nullable=False, default=20)
    search_score_threshold = Column(Float, nullable=False, default=0.0)
    reranker_top_k = Column(Integer, nullable=False, default=5)
    reranker_score_threshold = Column(Float, nullable=False, default=0.5)
    context_top_k = Column(Integer, nullable=False, default=5)
    hyde_enabled = Column(Boolean, nullable=False, default=True)
    multiquery_enabled = Column(Boolean, nullable=False, default=True)
    reranker_enabled = Column(Boolean, nullable=False, default=True)
    contextual_compression_enabled = Column(Boolean, nullable=False, default=True)
    parent_child_expansion_enabled = Column(Boolean, nullable=False, default=True)
    llm_provider = Column(String(32), nullable=False, default="local")
    llm_model = Column(String(128), nullable=False, default="gemma3:12b")
    embedding_provider = Column(String(32), nullable=False, default="local")
    embedding_model = Column(String(128), nullable=False, default="bge-m3")
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
