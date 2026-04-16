import asyncio
import logging
from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# In-process pub/sub bus keyed by document UUID string               #
# Each subscriber gets its own asyncio.Queue; events are broadcast   #
# to all active subscribers for a given doc_id.                      #
# ------------------------------------------------------------------ #

_subscribers: dict[str, list[asyncio.Queue]] = {}


def publish(doc_id: str, event: dict) -> None:
    """Broadcast event to all current subscribers for doc_id. Non-blocking."""
    for q in _subscribers.get(doc_id, []):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "Progress queue full for doc_id=%s; event dropped", doc_id
            )


async def subscribe(doc_id: str) -> AsyncGenerator[dict, None]:
    """
    Yield progress events for doc_id until a terminal event
    (step 'done' or 'error').  Cleans up the queue on exit.
    """
    q: asyncio.Queue[dict] = asyncio.Queue(maxsize=128)
    _subscribers.setdefault(doc_id, []).append(q)
    try:
        while True:
            event = await q.get()
            yield event
            if event.get("step") in ("done", "error"):
                break
    finally:
        try:
            _subscribers[doc_id].remove(q)
            if not _subscribers[doc_id]:
                del _subscribers[doc_id]
        except (KeyError, ValueError):
            pass
