import logging
import uuid as _uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.progress import subscribe

router = APIRouter(tags=["websocket"])

settings = get_settings()
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# GET /ws/documents/{doc_id}/progress                                #
# Auth    : JWT passed as ?token= query param (browsers cannot set   #
#           Authorization headers on WebSocket connections)          #
# Role    : admin or superadmin                                      #
# Streams : JSON progress events until terminal step (done/error)   #
# ------------------------------------------------------------------ #
@router.websocket("/ws/documents/{doc_id}/progress")
async def document_progress(
    websocket: WebSocket,
    doc_id: str,
    token: Optional[str] = None,
) -> None:
    # ------------------------------------------------------------------ #
    # 1. Authenticate — validate JWT and check role                       #
    # ------------------------------------------------------------------ #
    if not token:
        await websocket.close(code=4401)
        return

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        role = payload.get("role")
        if role not in ("admin", "superadmin"):
            raise ValueError("Insufficient role")
    except (JWTError, ValueError):
        await websocket.close(code=4403)
        return

    # Validate doc_id is a well-formed UUID to prevent arbitrary keys in the
    # subscriber registry (DoS via unbounded key-space with a valid admin token).
    try:
        _uuid.UUID(doc_id)
    except ValueError:
        await websocket.close(code=4400)
        return

    await websocket.accept()

    # ------------------------------------------------------------------ #
    # 2. Stream progress events until terminal event or disconnect        #
    # ------------------------------------------------------------------ #
    try:
        async for event in subscribe(doc_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected for doc_id=%s", doc_id)
    except Exception:
        logger.exception("WebSocket error for doc_id=%s", doc_id)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
