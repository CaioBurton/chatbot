import uuid

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.sql import func

from app.models.document import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuid_generate_v4(),
    )
    email = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    role = Column(Text, nullable=False, default="admin", server_default="admin")
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
