import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.rag_engine import rag_stream
from app.db.postgres import get_db
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import ChatMessageResponse, ChatRequest, ChatSessionResponse, SourceCitation

router = APIRouter(prefix="/chat", tags=["chat"])

logger = logging.getLogger(__name__)

# Optional bearer — returns None when no token is supplied instead of 401.
_oauth2_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def _optional_user_id(
    token: str | None = Depends(_oauth2_optional),
    db: AsyncSession = Depends(get_db),
) -> UUID | None:
    """
    Resolve the authenticated user's UUID from an optional JWT token.
    Returns None for anonymous (unauthenticated) requests.
    FastAPI injects the same DB session as other route dependencies (no second connection).
    """
    if not token:
        return None
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub: str | None = payload.get("sub")
        if not sub:
            return None
        # Import here to avoid circular imports at module load time
        from app.models.user import User

        result = await db.execute(select(User).where(User.email == sub))
        user = result.scalar_one_or_none()
        if user is None:
            return None
        return user.id
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# POST /chat/sessions — create a session (anonymous or authenticated)
# ---------------------------------------------------------------------------

@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatSessionResponse,
)
async def create_session(
    db: AsyncSession = Depends(get_db),
    user_id: UUID | None = Depends(_optional_user_id),
) -> ChatSessionResponse:
    session = ChatSession(user_id=user_id)
    db.add(session)
    await db.flush()
    await db.commit()
    return ChatSessionResponse(session_id=session.id)


# ---------------------------------------------------------------------------
# POST /chat/stream — RAG streaming endpoint (public)
# ---------------------------------------------------------------------------

@router.post("/stream", response_class=EventSourceResponse)
async def chat_stream(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """
    Stream a RAG-grounded response as Server-Sent Events.

    Event types emitted:
      event: token  — incremental text tokens from the LLM
      event: sources — JSON array of SourceCitation objects
      event: done   — always "[DONE]", signals stream end
    """
    if request.session_id is None:
        session = ChatSession(user_id=None)
        db.add(session)
        await db.flush()
        session_id: UUID = session.id
        await db.commit()
    else:
        existing = await db.get(ChatSession, request.session_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found.",
            )
        session_id = request.session_id

    return EventSourceResponse(rag_stream(request.message, session_id, db))


# ---------------------------------------------------------------------------
# GET /chat/sessions/{id}/history — list messages for a session
# ---------------------------------------------------------------------------

@router.get(
    "/sessions/{session_id}/history",
    response_model=list[ChatMessageResponse],
)
async def get_session_history(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessageResponse]:
    """
    Return all messages for the given session in chronological order.
    Anyone who knows the session UUID can retrieve its history (public).
    """
    existing = await db.get(ChatSession, session_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found.",
        )

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()

    response: list[ChatMessageResponse] = []
    for msg in messages:
        sources = None
        if msg.sources:
            try:
                sources = [SourceCitation(**s) for s in msg.sources]
            except Exception:
                sources = None

        response.append(
            ChatMessageResponse(
                id=msg.id,
                role=msg.role,
                sources=sources,
                created_at=msg.created_at.isoformat() if msg.created_at else "",
            )
        )

    return response
