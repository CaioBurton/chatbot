import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

# Maximum number of session IDs accepted in a single /sessions request.
_MAX_SESSION_IDS = 100
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.core.config import get_settings
from app.core.rag_engine import rag_stream
from app.db.postgres import get_db
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import ChatMessageResponse, ChatRequest, ChatSessionResponse, ChatSessionSummary, MessageFeedbackRequest, SourceCitation

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

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
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

    async def generate():
        async for event_dict in rag_stream(request.message, session_id, db):
            event_type = event_dict.get("event", "message")
            data = str(event_dict.get("data", ""))
            # Per SSE spec, multi-line data needs one "data: " prefix per line
            data_lines = "\n".join(f"data: {line}" for line in data.split("\n"))
            yield f"event: {event_type}\n{data_lines}\n\n".encode("utf-8")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


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

        if msg.sources and sources is None:
            logger.warning("Malformed sources on message %s — dropped.", msg.id)

        response.append(
            ChatMessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                sources=sources,
                created_at=msg.created_at.isoformat() if msg.created_at else "",
            )
        )

    return response


# ---------------------------------------------------------------------------
# GET /chat/sessions — fetch summaries for a list of known session IDs
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=list[ChatSessionSummary])
async def list_sessions(
    session_ids: list[UUID] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
) -> list[ChatSessionSummary]:
    """
    Return summary metadata for the given session IDs.
    Sessions that do not exist are silently omitted.
    Used by the frontend sidebar to display known sessions from localStorage.
    """
    if not session_ids:
        return []

    if len(session_ids) > _MAX_SESSION_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At most {_MAX_SESSION_IDS} session IDs allowed per request.",
        )

    # Correlated subquery — single round-trip to the database (no N+1).
    preview_subq = (
        select(ChatMessage.content)
        .where(
            ChatMessage.session_id == ChatSession.id,
            ChatMessage.role == "user",
        )
        .order_by(ChatMessage.created_at.asc())
        .limit(1)
        .correlate(ChatSession)
        .scalar_subquery()
    )

    result = await db.execute(
        select(ChatSession, preview_subq.label("preview"))
        .where(ChatSession.id.in_(session_ids))
    )
    rows = result.all()

    summaries: list[ChatSessionSummary] = []
    for session, first_content in rows:
        preview = first_content[:80] if first_content else None
        summaries.append(
            ChatSessionSummary(
                session_id=session.id,
                created_at=session.created_at.isoformat() if session.created_at else "",
                last_activity=session.last_activity.isoformat() if session.last_activity else "",
                preview=preview,
            )
        )

    return summaries


# ---------------------------------------------------------------------------
# DELETE /chat/sessions/{session_id} — remove a session and its messages
# ---------------------------------------------------------------------------

@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Permanently delete a chat session and all its messages.
    """
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found.",
        )
    await db.delete(session)
    await db.commit()


# ---------------------------------------------------------------------------
# PATCH /chat/messages/{message_id}/feedback — record thumbs up/down
# ---------------------------------------------------------------------------

@router.patch("/messages/{message_id}/feedback", response_model=dict[str, bool])
async def submit_message_feedback(
    message_id: UUID,
    body: MessageFeedbackRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    message = await db.get(ChatMessage, message_id)
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found.",
        )
    message.feedback = body.feedback
    await db.commit()
    return {"ok": True}
