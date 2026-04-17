"""Latency tests for chat endpoints.

Covers:
  c) POST /chat/sessions → 201 in < 200 ms.
  d) POST /chat/stream   → time-to-first-byte (TTFB) ≤ 2 000 ms.

The sessions test uses a mock DB session so PostgreSQL is not required.
The stream TTFB test requires live Qdrant and Ollama; it is automatically
skipped when those services are unreachable.

All thresholds are multiplied by LATENCY_TOLERANCE_FACTOR = 1.5 in assertions.
"""

import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from app.db.postgres import get_db
from app.main import app as _app

LATENCY_TOLERANCE_FACTOR = 1.5

# PLANEJAMENTO.md §13 targets
_SESSIONS_TARGET_MS = 200.0
_TTFB_TARGET_MS = 2_000.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sessions_db() -> AsyncMock:
    """
    Mock AsyncSession suitable for /chat/sessions and /chat/stream.

    The ``add`` side-effect assigns a UUID to new ORM objects at add-time,
    replicating the behaviour of a real SQLAlchemy flush (which applies
    Python-side ``default=uuid.uuid4`` column defaults).
    """
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    def _add(obj):
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid4()

    session.add = MagicMock(side_effect=_add)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


async def _service_reachable(url: str, timeout: float = 2.0) -> bool:
    """Return True if a HEAD/GET to *url* succeeds within *timeout* seconds."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as probe:
            resp = await probe.get(url)
            return resp.status_code < 500
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_create_session_latency(async_client):
    """POST /chat/sessions must return HTTP 201 in < 200 ms.

    Expected p95 (PLANEJAMENTO.md §13): < 200 ms.
    Session creation is a lightweight DB INSERT (UUID generation + one row).
    """
    session = _make_sessions_db()

    async def override():
        yield session

    _app.dependency_overrides[get_db] = override
    try:
        t0 = time.perf_counter()
        resp = await async_client.post("/chat/sessions")
        elapsed_ms = (time.perf_counter() - t0) * 1000
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    limit = _SESSIONS_TARGET_MS * LATENCY_TOLERANCE_FACTOR
    assert elapsed_ms < limit, (
        f"POST /chat/sessions took {elapsed_ms:.1f} ms — expected < {limit:.0f} ms"
    )


async def test_chat_stream_ttfb(async_client):
    """POST /chat/stream TTFB must be ≤ 2 000 ms.

    Expected p95 (PLANEJAMENTO.md §13):
      - Embedding query      : ~50 ms
      - Hybrid Qdrant search : ~20–50 ms
      - Reranking            : ~100–200 ms
      - LLM first token      : ~700–1 500 ms
      ──────────────────────────────────────
      Total TTFB budget      : ≤ 2 000 ms

    Skipped automatically when Qdrant or Ollama is unreachable.
    The DB dependency is mocked so PostgreSQL is not required.
    """
    from app.core.config import get_settings

    cfg = get_settings()
    qdrant_ok = await _service_reachable(f"{cfg.QDRANT_URL}/healthz")
    ollama_ok = await _service_reachable(f"{cfg.OLLAMA_BASE_URL}/api/version")

    if not qdrant_ok or not ollama_ok:
        pytest.skip("external services unavailable (Qdrant or Ollama not reachable)")

    db_session = _make_sessions_db()

    async def db_override():
        yield db_session

    _app.dependency_overrides[get_db] = db_override
    try:
        payload = {"message": "O que é PIBIC?"}
        t0 = time.perf_counter()
        async with async_client.stream("POST", "/chat/stream", json=payload) as resp:
            assert resp.status_code == 200, (
                f"Expected 200, got {resp.status_code}: {await resp.aread()}"
            )
            first_chunk_received = False
            async for chunk in resp.aiter_bytes():
                if chunk.strip():
                    first_chunk_received = True
                    break
        ttfb_ms = (time.perf_counter() - t0) * 1000
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert first_chunk_received, "No SSE data received from POST /chat/stream"
    limit = _TTFB_TARGET_MS * LATENCY_TOLERANCE_FACTOR
    assert ttfb_ms <= limit, (
        f"TTFB = {ttfb_ms:.1f} ms — expected ≤ {limit:.0f} ms"
    )
