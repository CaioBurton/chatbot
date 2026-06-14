from datetime import datetime
from typing import Literal

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
    hyde_enabled: bool
    multiquery_enabled: bool
    reranker_enabled: bool
    contextual_compression_enabled: bool
    parent_child_expansion_enabled: bool
    llm_provider: Literal["local", "openai", "anthropic", "gemini"]
    llm_model: str
    embedding_provider: Literal["local", "gemini"]
    embedding_model: str
    openai_api_key_configured: bool = False
    anthropic_api_key_configured: bool = False
    google_api_key_configured: bool = False
    updated_at: datetime


class RagConfigUpdate(BaseModel):
    parent_chunk_tokens: int = Field(ge=64, le=2048)
    child_chunk_tokens: int = Field(ge=16, le=512)
    search_top_k: int = Field(ge=1, le=100)
    search_score_threshold: float = Field(ge=0.0, le=1.0)
    reranker_top_k: int = Field(ge=1, le=100)
    reranker_score_threshold: float = Field(ge=0.0, le=1.0)
    hyde_enabled: bool = True
    multiquery_enabled: bool = True
    reranker_enabled: bool = True
    contextual_compression_enabled: bool = True
    parent_child_expansion_enabled: bool = True
    llm_provider: Literal["local", "openai", "anthropic", "gemini"] = "local"
    llm_model: str = Field(default="gemma3:12b", min_length=1, max_length=128)
    embedding_provider: Literal["local", "gemini"] = "local"
    embedding_model: str = Field(default="bge-m3", min_length=1, max_length=128)

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
