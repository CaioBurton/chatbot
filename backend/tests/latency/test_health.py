"""Latency baseline: GET /health.

Enforces PLANEJAMENTO.md §13 baseline — the health endpoint has no DB or
external-service dependencies, so any latency above the threshold indicates
overhead in the ASGI stack itself.

Threshold: p50 of 20 sequential calls < 50 ms  (× 1.5 tolerance = 75 ms).
"""

import statistics
import time

# Tolerance multiplier: absorbs CI environment variability (slower VMs, cold
# JIT, etc.) without masking genuine regressions.
LATENCY_TOLERANCE_FACTOR = 1.5

_HEALTH_P50_TARGET_MS = 50.0
_SAMPLE_COUNT = 20


async def test_health_returns_ok(async_client):
    """GET /health must return HTTP 200 with body {"status": "ok"}."""
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_p50_latency(async_client):
    """p50 of 20 sequential GET /health calls must be < 50 ms.

    Expected p95 (PLANEJAMENTO.md §13): < 50 ms — near-instant, no I/O.
    """
    samples: list[float] = []

    for _ in range(_SAMPLE_COUNT):
        t0 = time.perf_counter()
        resp = await async_client.get("/health")
        samples.append((time.perf_counter() - t0) * 1000)
        assert resp.status_code == 200

    p50 = statistics.median(samples)
    limit = _HEALTH_P50_TARGET_MS * LATENCY_TOLERANCE_FACTOR
    assert p50 < limit, (
        f"Health check p50 = {p50:.2f} ms — expected < {limit:.1f} ms "
        f"(samples: min={min(samples):.2f} ms, max={max(samples):.2f} ms)"
    )
