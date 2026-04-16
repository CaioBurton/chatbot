from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


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


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
