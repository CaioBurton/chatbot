"""Latency tests for POST /auth/login.

Covers:
  a) Valid credentials → 200 response < 500 ms.
  b) Invalid credentials → 401 response < 600 ms.
  c) |valid_time − invalid_time| < 100 ms (anti-enumeration timing check,
     verifies CWE-208 mitigation in auth.py).

The DB dependency is overridden with a mock session so PostgreSQL is not
required.  bcrypt verification (work factor 12) dominates the response time
and is exercised in full — this is intentional.

All thresholds are multiplied by LATENCY_TOLERANCE_FACTOR = 1.5 in assertions.
"""

import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from passlib.context import CryptContext

from app.db.postgres import get_db
from app.main import app as _app
from app.models.user import User

LATENCY_TOLERANCE_FACTOR = 1.5

# Thresholds (milliseconds) — from PLANEJAMENTO.md §13 and security budget.
_VALID_LOGIN_TARGET_MS = 500.0
_INVALID_LOGIN_TARGET_MS = 600.0
_TIMING_DELTA_TARGET_MS = 100.0

# ---------------------------------------------------------------------------
# Test user fixtures — no real credentials; clearly fake values.
# ---------------------------------------------------------------------------

TEST_EMAIL = "testadmin@example.test"
TEST_PASSWORD = "TestPassword123!"  # noqa: S105 — fake value for testing only

# Pre-compute the bcrypt hash once at module load.
# This takes ~200 ms (work factor 12) but ensures timing measurements are
# authentic — the same bcrypt path runs in production.
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_TEST_HASH: str = _pwd_ctx.hash(TEST_PASSWORD)


# ---------------------------------------------------------------------------
# DB session factories
# ---------------------------------------------------------------------------


def _user_session() -> AsyncMock:
    """Mock DB session that returns the test User (email found, hash matches)."""
    user = User()
    user.id = uuid4()
    user.email = TEST_EMAIL
    user.password_hash = _TEST_HASH
    user.role = "admin"

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session.execute.return_value = result
    return session


def _empty_session() -> AsyncMock:
    """Mock DB session that returns None (email not found → dummy hash run)."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_login_valid_latency(async_client):
    """Valid credentials must produce HTTP 200 in < 500 ms.

    Expected p95 (PLANEJAMENTO.md §13): < 500 ms.
    bcrypt verification (work factor 12) is typically ~200 ms; the budget
    includes 300 ms for DB round-trip and ASGI overhead.
    """
    session = _user_session()

    async def override():
        yield session

    _app.dependency_overrides[get_db] = override
    try:
        t0 = time.perf_counter()
        resp = await async_client.post(
            "/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    limit = _VALID_LOGIN_TARGET_MS * LATENCY_TOLERANCE_FACTOR
    assert elapsed_ms < limit, (
        f"Valid login took {elapsed_ms:.1f} ms — expected < {limit:.1f} ms"
    )


async def test_login_invalid_latency(async_client):
    """Invalid credentials must return HTTP 401 in < 600 ms.

    Expected p95 (PLANEJAMENTO.md §13): < 600 ms.
    The auth route runs bcrypt against a dummy hash even when the user is not
    found, ensuring timing is constant regardless of whether the email exists
    (CWE-208 timing side-channel mitigation).
    """
    session = _empty_session()

    async def override():
        yield session

    _app.dependency_overrides[get_db] = override
    try:
        t0 = time.perf_counter()
        resp = await async_client.post(
            "/auth/login",
            json={"email": "nobody@example.test", "password": "wrongpassword"},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    limit = _INVALID_LOGIN_TARGET_MS * LATENCY_TOLERANCE_FACTOR
    assert elapsed_ms < limit, (
        f"Invalid login took {elapsed_ms:.1f} ms — expected < {limit:.1f} ms"
    )


async def test_login_timing_anti_enumeration(async_client):
    """Timing delta between valid and invalid login must be < 100 ms.

    Verifies that the CWE-208 timing side-channel mitigation in auth.py is
    effective: both paths run a full bcrypt verification, so their wall-clock
    times should be nearly identical.

    Expected p95 delta (PLANEJAMENTO.md §13): < 100 ms.
    """
    valid_session = _user_session()
    invalid_session = _empty_session()

    async def valid_override():
        yield valid_session

    async def invalid_override():
        yield invalid_session

    # --- valid credentials ---
    _app.dependency_overrides[get_db] = valid_override
    try:
        t0 = time.perf_counter()
        await async_client.post(
            "/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        valid_ms = (time.perf_counter() - t0) * 1000
    finally:
        _app.dependency_overrides.pop(get_db, None)

    # --- invalid credentials ---
    _app.dependency_overrides[get_db] = invalid_override
    try:
        t0 = time.perf_counter()
        await async_client.post(
            "/auth/login",
            json={"email": "nobody@example.test", "password": "wrongpassword"},
        )
        invalid_ms = (time.perf_counter() - t0) * 1000
    finally:
        _app.dependency_overrides.pop(get_db, None)

    delta = abs(valid_ms - invalid_ms)
    limit = _TIMING_DELTA_TARGET_MS * LATENCY_TOLERANCE_FACTOR
    assert delta < limit, (
        f"Login timing delta {delta:.1f} ms exceeds anti-enumeration limit "
        f"{limit:.1f} ms (valid={valid_ms:.1f} ms, invalid={invalid_ms:.1f} ms)"
    )
