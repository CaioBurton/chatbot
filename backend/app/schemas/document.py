from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    original_name: str


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_name: str
    status: str
    file_type: str
    total_chunks: int | None
    created_at: datetime


class DocumentDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_name: str
    status: str
    file_type: str
    ocr_applied: bool
    total_chunks: int | None
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ------------------------------------------------------------------ #
# Hybrid search — added to support POST /documents/search             #
# All validations enforced server-side by Pydantic / FastAPI,        #
# independent of any frontend.                                        #
# ------------------------------------------------------------------ #

class HybridSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(20, ge=1, le=100)
    score_threshold: float = Field(0.0, ge=0.0, le=1.0)
    rerank: bool = False
    reranker_top_k: int = Field(5, ge=1, le=100)
    reranker_score_threshold: float = Field(0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _reranker_top_k_within_candidate_pool(self) -> "HybridSearchRequest":
        if self.rerank and self.reranker_top_k > self.top_k:
            raise ValueError(
                f"reranker_top_k ({self.reranker_top_k}) cannot exceed top_k "
                f"({self.top_k}): the reranker cannot return more results than "
                "the candidate pool fetched from Qdrant."
            )
        return self


class SearchResultItem(BaseModel):
    chunk_id: str
    score: float
    doc_id: str
    source: str
    page_number: int
    text_preview: str
    chunk_index: int
    rerank_score: float | None = None
