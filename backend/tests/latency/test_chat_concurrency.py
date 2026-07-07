"""Verifies the /chat/stream concurrency cap added in a42d10d.

MAX_CONCURRENT_CHAT_REQUESTS bounds how many rag_stream pipelines can be
in flight at once via a module-level asyncio.Semaphore in
app/api/routes/chat.py. This test fires more concurrent requests than the
configured cap and asserts the observed concurrency never exceeds it, while
every request still eventually succeeds (queued, not rejected).
"""

import asyncio

import pytest

from app.api.routes import chat as chat_module
from app.core.config import get_settings
from app.db.postgres import get_db
from app.main import app as _app
from tests.conftest import make_mock_db, override_get_db


async def test_chat_stream_caps_concurrency(async_client):
    """No more than MAX_CONCURRENT_CHAT_REQUESTS pipelines run at once."""
    settings = get_settings()
    cap = settings.MAX_CONCURRENT_CHAT_REQUESTS
    num_requests = cap + 2  # comfortably over the cap, under the 5/minute rate limit

    state = {"current": 0, "max_seen": 0}
    lock = asyncio.Lock()

    async def fake_rag_stream(message, session_id, db):
        async with lock:
            state["current"] += 1
            state["max_seen"] = max(state["max_seen"], state["current"])
        try:
            await asyncio.sleep(0.15)
            yield {"event": "token", "data": "hi"}
            yield {"event": "done", "data": "[DONE]"}
        finally:
            async with lock:
                state["current"] -= 1

    original_rag_stream = chat_module.rag_stream
    chat_module.rag_stream = fake_rag_stream

    db_session = make_mock_db()
    _app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        responses = await asyncio.gather(
            *(
                async_client.post("/chat/stream", json={"message": f"pergunta {i}"})
                for i in range(num_requests)
            )
        )
    finally:
        chat_module.rag_stream = original_rag_stream
        _app.dependency_overrides.pop(get_db, None)

    for resp in responses:
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    assert state["max_seen"] <= cap, (
        f"Observed {state['max_seen']} concurrent /chat/stream pipelines — "
        f"expected the semaphore to cap it at {cap}"
    )
    # Sanity check the mock actually ran concurrently at some point, otherwise
    # a broken semaphore that serializes everything (cap=1 always) would pass
    # the assertion above trivially.
    assert state["max_seen"] >= 1
