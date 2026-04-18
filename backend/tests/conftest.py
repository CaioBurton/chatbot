"""
PROPESQI RAG Chatbot — Test Suite
==================================

Purpose
-------
Latency and load tests for the FastAPI backend of the PROPESQI RAG Chatbot.

  • Latency tests (pytest + httpx.AsyncClient) run against the FastAPI ASGI
    app **in-process** — no live HTTP server required.  External-service
    tests (Qdrant, Ollama) skip themselves automatically when those services
    are unreachable.

  • Load tests (Locust) run against a **live, fully-deployed stack** and are
    not part of the pytest suite.  See the Locust section below.

How to run pytest latency tests
--------------------------------
From the ``backend/`` directory (with the virtualenv active):

    pytest tests/latency/ -v

Or with timing output:

    pytest tests/latency/ -v --tb=short

The tests expect the following environment variables.  If running against the
Docker Compose stack they are already set inside the container:

    DATABASE_URL      postgresql+asyncpg://user:pass@postgres:5432/propesqi
    QDRANT_URL        http://qdrant:6333
    QDRANT_API_KEY    <your-key>
    OLLAMA_BASE_URL   http://ollama:11434
    SECRET_KEY        <>=32-char secret>

Fallback test values are applied automatically via ``os.environ.setdefault``
so the test collection succeeds even without a ``.env`` file.

How to run Locust load tests
-----------------------------
Requires a fully-running Docker Compose stack.  From project root:

    pip install locust>=2.24,<3.0  # if not already installed
    locust -f backend/tests/load/locustfile.py \\
           --host http://localhost:8000 \\
           --users 20 --spawn-rate 5 \\
           --run-time 2m --headless

Or set the base URL via environment variable:

    LOCUST_BASE_URL=http://localhost:8000 \\
        locust -f backend/tests/load/locustfile.py --headless -u 20 -r 5 -t 2m

Environment variables required by Locust
-----------------------------------------
    LOCUST_BASE_URL   Base URL of the running backend  [default: http://localhost:8000]
    ADMIN_EMAIL       Admin user e-mail for AdminUser tasks
    ADMIN_PASSWORD    Admin user password  for AdminUser tasks

Latency thresholds enforced by pytest
--------------------------------------
All thresholds are multiplied by ``LATENCY_TOLERANCE_FACTOR = 1.5`` in the
actual assertions to absorb CI environment variability.

    Endpoint                    Spec target        Test limit (×1.5)
    ──────────────────────────────────────────────────────────────────
    GET  /health (p50/20)       < 50 ms            < 75 ms
    POST /auth/login (valid)    < 500 ms           < 750 ms
    POST /auth/login (invalid)  < 600 ms           < 900 ms
    |valid − invalid| timing    < 100 ms           < 150 ms  (CWE-208)
    POST /chat/sessions         < 200 ms           < 300 ms
    POST /chat/stream TTFB      ≤ 2 000 ms         ≤ 3 000 ms
    POST /documents/search      ≤ 300 ms           ≤ 450 ms
"""

import os

# ---------------------------------------------------------------------------
# Set required env vars BEFORE any app module is imported.
# setdefault leaves existing values (real .env via docker-compose) intact.
# ---------------------------------------------------------------------------
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/testdb"
)
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test-key")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault(
    "SECRET_KEY", "test-secret-key-for-ci-testing-at-least-32chars!"
)

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from jose import jwt as _jose_jwt

from app.core.config import get_settings
from app.db.postgres import get_db
from app.main import app as _app

# ---------------------------------------------------------------------------
# Patch the app lifespan so Qdrant failures at startup do not abort the
# test session.  Individual tests that need live services skip explicitly.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _safe_lifespan(application):
    """Startup wrapper: tolerates Qdrant being unreachable."""
    try:
        from app.db.qdrant import ensure_collection

        await ensure_collection()
    except Exception:
        pass  # external service unavailable — per-test skips handle this
    yield


_app.router.lifespan_context = _safe_lifespan

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def settings():
    """Return the cached Settings singleton."""
    return get_settings()


@pytest.fixture
def test_jwt(settings) -> str:
    """
    Generate a valid HS256 JWT directly via python-jose, using the same
    SECRET_KEY and ALGORITHM as the running app.

    Generating the token here (rather than calling POST /auth/login) keeps
    shared fixtures free of network round-trips and isolates auth latency
    measurement to test_auth.py.

    The token carries role='admin' so admin-gated routes can be exercised.
    """
    payload = {
        "sub": "ci-tester@example.test",
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return _jose_jwt.encode(
        payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    AsyncClient wired directly to the FastAPI ASGI app.
    No live HTTP server is required for latency tests.
    """
    transport = httpx.ASGITransport(app=_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# DB session factory helpers (used by individual test files)
# ---------------------------------------------------------------------------


def make_mock_db(return_user=None) -> AsyncMock:
    """
    Return an AsyncMock SQLAlchemy session suitable for endpoints that
    call ``db.execute(select(...))`` and ``db.add / flush / commit``.

    ``return_user`` is the value returned by ``result.scalar_one_or_none()``.
    Pass ``None`` to simulate a user-not-found response.
    """
    session = AsyncMock()

    result = MagicMock()
    result.scalar_one_or_none.return_value = return_user
    session.execute.return_value = result

    def _add(obj):
        # Apply Python-side SQLAlchemy primary-key defaults that would
        # normally be set during the ORM flush step.
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid4()

    session.add = MagicMock(side_effect=_add)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


def override_get_db(session: AsyncMock):
    """
    Return an async dependency-override callable suitable for use as
    ``app.dependency_overrides[get_db] = override_get_db(session)``.
    """

    async def _override() -> AsyncGenerator:
        yield session

    return _override
