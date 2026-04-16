from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


class SearchResultItem(BaseModel):
    chunk_id: str
    score: float
    doc_id: str
    source: str
    page_number: int
    text_preview: str
    chunk_index: int
