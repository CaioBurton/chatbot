from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: Optional[UUID] = None
    message: str = Field(..., min_length=1, max_length=2000)


class SourceCitation(BaseModel):
    doc_id: UUID
    original_name: str = Field(..., max_length=500)
    page_number: Optional[int] = Field(None, ge=1)
    score: float = Field(..., ge=0.0, le=1.0)


class ChatSessionResponse(BaseModel):
    session_id: UUID


class ChatMessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    sources: Optional[list[SourceCitation]] = None
    created_at: str

    model_config = {"from_attributes": True}
