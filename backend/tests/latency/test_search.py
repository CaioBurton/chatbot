"""Latency stubs for the internal search path.

Internal pipeline latency targets (PLANEJAMENTO.md §13):
  • Embedding query      : ~50 ms
  • Hybrid Qdrant search : ~20–50 ms
  • Reranking            : ~100–200 ms

These tests drive POST /documents/search (admin-only hybrid search endpoint)
end-to-end via HTTP.  They measure the combined embedding + search (± rerank)
latency from the client's perspective.

All tests skip automatically when Qdrant is unreachable.

All thresholds are multiplied by LATENCY_TOLERANCE_FACTOR = 1.5 in assertions.
"""

import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from app.core.config import get_settings
from app.db.postgres import get_db
from app.main import app as _app
from app.models.user import User

LATENCY_TOLERANCE_FACTOR = 1.5

# PLANEJAMENTO.md §13 targets (milliseconds)
_EMBED_TARGET_MS = 50.0
_SEARCH_TARGET_MS = 50.0
_RERANK_TARGET_MS = 200.0

# Combined budget: embedding + search + rerank, without LLM generation.
_FULL_SEARCH_RERANK_TARGET_MS = _EMBED_TARGET_MS + _SEARCH_TARGET_MS + _RERANK_TARGET_MS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_db_session() -> AsyncMock:
    """
    Mock DB session that returns an admin User when queried by email.
    Used to satisfy the ``require_admin`` dependency on /documents/search.
    """
    user = User()
    user.id = uuid4()
    user.email = "ci-tester@example.test"
    user.password_hash = "unused-in-search-tests"
    user.role = "admin"

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session.execute.return_value = result
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


async def _qdrant_reachable() -> bool:
    cfg = get_settings()
    try:
        async with httpx.AsyncClient(timeout=2.0) as probe:
            resp = await probe.get(f"{cfg.QDRANT_URL}/healthz")
            return resp.status_code < 500
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_search_without_rerank_latency(async_client, test_jwt):
    """POST /documents/search (no rerank) must complete in ≤ 100 ms.

    Expected p95 (PLANEJAMENTO.md §13):
      - Embedding query      : ~50 ms
      - Hybrid Qdrant search : ~20–50 ms
      ─────────────────────────────────
      Total (no rerank)      : ~70–100 ms

    Skipped when Qdrant is unreachable.
    """
    if not await _qdrant_reachable():
        pytest.skip("external services unavailable (Qdrant not reachable)")

    session = _admin_db_session()

    async def override():
        yield session

    _app.dependency_overrides[get_db] = override
    try:
        payload = {
            "query": "PIBIC",
            "top_k": 5,
            "rerank": False,
        }
        t0 = time.perf_counter()
        resp = await async_client.post(
            "/documents/search",
            json=payload,
            headers={"Authorization": f"Bearer {test_jwt}"},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    no_rerank_limit = (_EMBED_TARGET_MS + _SEARCH_TARGET_MS) * LATENCY_TOLERANCE_FACTOR
    assert elapsed_ms <= no_rerank_limit, (
        f"Search (no rerank) took {elapsed_ms:.1f} ms — expected ≤ {no_rerank_limit:.0f} ms"
    )


async def test_search_with_rerank_latency(async_client, test_jwt):
    """POST /documents/search (with rerank) must complete in ≤ 300 ms.

    Expected p95 (PLANEJAMENTO.md §13):
      - Embedding query      : ~50 ms
      - Hybrid Qdrant search : ~20–50 ms
      - Reranking            : ~100–200 ms
      ──────────────────────────────────
      Total (with rerank)    : ~170–300 ms

    Skipped when Qdrant is unreachable.
    """
    if not await _qdrant_reachable():
        pytest.skip("external services unavailable (Qdrant not reachable)")

    session = _admin_db_session()

    async def override():
        yield session

    _app.dependency_overrides[get_db] = override
    try:
        payload = {
            "query": "PIBIC bolsa pesquisa",
            "top_k": 10,
            "rerank": True,
        }
        t0 = time.perf_counter()
        resp = await async_client.post(
            "/documents/search",
            json=payload,
            headers={"Authorization": f"Bearer {test_jwt}"},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    limit = _FULL_SEARCH_RERANK_TARGET_MS * LATENCY_TOLERANCE_FACTOR
    assert elapsed_ms <= limit, (
        f"Search+rerank took {elapsed_ms:.1f} ms — expected ≤ {limit:.0f} ms"
    )


async def test_search_empty_collection_fast(async_client, test_jwt):
    """Search against an empty collection must still return in < 200 ms.

    Expected p95 (PLANEJAMENTO.md §13): < 200 ms (embedding + empty Qdrant
    result set; reranker not invoked with zero results).

    Skipped when Qdrant is unreachable.

    NOTE (stub): This test is a placeholder to be refined once the collection
    is pre-populated with representative documents in the CI environment.
    The assertion uses the combined search budget as a conservative limit.
    """
    if not await _qdrant_reachable():
        pytest.skip("external services unavailable (Qdrant not reachable)")

    session = _admin_db_session()

    async def override():
        yield session

    _app.dependency_overrides[get_db] = override
    try:
        payload = {
            "query": "zzzzzzzzzz_nonexistent_query_stub",
            "top_k": 5,
            "rerank": False,
        }
        t0 = time.perf_counter()
        resp = await async_client.post(
            "/documents/search",
            json=payload,
            headers={"Authorization": f"Bearer {test_jwt}"},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    limit = (_EMBED_TARGET_MS + _SEARCH_TARGET_MS) * LATENCY_TOLERANCE_FACTOR
    assert elapsed_ms <= limit, (
        f"Empty-collection search took {elapsed_ms:.1f} ms — expected ≤ {limit:.0f} ms"
    )
