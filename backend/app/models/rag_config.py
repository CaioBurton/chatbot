from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Float, Integer
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
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
