import uuid

from sqlalchemy import Boolean, Column, Integer, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    filename = Column(Text, nullable=False)
    original_name = Column(Text, nullable=False)
    display_name = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    file_hash = Column(Text, nullable=False, unique=True)
    file_type = Column(Text, nullable=False)
    ocr_applied = Column(Boolean, nullable=False, default=False, server_default="false")
    status = Column(
        Text, nullable=False, default="uploaded", server_default="uploaded"
    )
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    total_chunks = Column(Integer, nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
