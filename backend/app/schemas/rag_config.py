from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RagConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_chunk_tokens: int
    child_chunk_tokens: int
    search_top_k: int
    search_score_threshold: float
    reranker_top_k: int
    reranker_score_threshold: float
    updated_at: datetime


class RagConfigUpdate(BaseModel):
    parent_chunk_tokens: int = Field(ge=64, le=2048)
    child_chunk_tokens: int = Field(ge=16, le=512)
    search_top_k: int = Field(ge=1, le=100)
    search_score_threshold: float = Field(ge=0.0, le=1.0)
    reranker_top_k: int = Field(ge=1, le=100)
    reranker_score_threshold: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _cross_field_rules(self) -> "RagConfigUpdate":
        if self.child_chunk_tokens >= self.parent_chunk_tokens:
            raise ValueError(
                "child_chunk_tokens must be strictly less than parent_chunk_tokens"
            )
        if self.reranker_top_k > self.search_top_k:
            raise ValueError(
                "reranker_top_k must be less than or equal to search_top_k"
            )
        return self
