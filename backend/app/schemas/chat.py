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


class ChatSessionSummary(BaseModel):
    session_id: UUID
    created_at: str
    last_activity: str
    preview: Optional[str] = Field(None, max_length=80)


class ChatMessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    sources: Optional[list[SourceCitation]] = None
    created_at: str

    model_config = {"from_attributes": True}
