"""Locust load-test scenarios for the PROPESQI RAG Chatbot backend.

Run against a fully-deployed Docker Compose stack:

    locust -f backend/tests/load/locustfile.py \\
           --host http://localhost:8000 \\
           --users 20 --spawn-rate 5 --run-time 2m --headless

Or via environment variable:

    LOCUST_BASE_URL=http://localhost:8000 \\
        locust -f backend/tests/load/locustfile.py -u 20 -r 5 -t 2m --headless

Environment variables
---------------------
LOCUST_BASE_URL   Base URL of the running backend  [default: http://localhost:8000]
ADMIN_EMAIL       Admin user e-mail  (required for AdminUser tasks)
ADMIN_PASSWORD    Admin user password (required for AdminUser tasks)

User classes
------------
AnonymousUser   Simulates unauthenticated API consumers.
                tasks: health_check (×3), create_session (×2), chat_stream (×1)

AdminUser       Simulates authenticated admin users.
                tasks: health_check (×2), login (×1)

Latency targets (PLANEJAMENTO.md §13)
--------------------------------------
GET  /health            p95 < 50 ms
POST /auth/login        p95 < 500 ms  (valid creds)
POST /chat/sessions     p95 < 200 ms
POST /chat/stream TTFB  p95 ≤ 2 000 ms
"""

import os

from locust import HttpUser, between, task

_BASE_URL = os.environ.get("LOCUST_BASE_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# AnonymousUser
# ---------------------------------------------------------------------------


class AnonymousUser(HttpUser):
    """Unauthenticated API consumer: health checks, session creation, chat."""

    host = _BASE_URL
    wait_time = between(0.5, 2.0)

    @task(3)
    def health_check(self):
        """GET /health — expected p95 < 50 ms (PLANEJAMENTO.md §13)."""
        with self.client.get("/health", catch_response=True) as resp:
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                resp.success()
            else:
                resp.failure(f"Unexpected response: {resp.status_code} {resp.text[:80]}")

    @task(2)
    def create_session(self):
        """POST /chat/sessions — expected p95 < 200 ms (PLANEJAMENTO.md §13)."""
        with self.client.post("/chat/sessions", catch_response=True) as resp:
            if resp.status_code == 201:
                resp.success()
            else:
                resp.failure(f"Expected 201, got {resp.status_code}: {resp.text[:80]}")

    @task(1)
    def chat_stream(self):
        """POST /chat/stream — expected TTFB p95 ≤ 2 000 ms (PLANEJAMENTO.md §13).

        Only the first SSE event is consumed and then the connection is closed.
        This measures time-to-first-token without waiting for the full response,
        matching the PLANEJAMENTO.md §13 TTFB budget.
        """
        payload = {"message": "O que é PIBIC?"}
        with self.client.post(
            "/chat/stream",
            json=payload,
            stream=True,
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(
                    f"Expected 200, got {resp.status_code}: {resp.text[:80]}"
                )
                return

            first_chunk_received = False
            for line in resp.iter_lines():
                if line:
                    first_chunk_received = True
                    break  # consume only the first SSE event, then close

            if first_chunk_received:
                resp.success()
            else:
                resp.failure("No SSE data received from /chat/stream")


# ---------------------------------------------------------------------------
# AdminUser
# ---------------------------------------------------------------------------


class AdminUser(HttpUser):
    """Authenticated admin user: health checks and login."""

    host = _BASE_URL
    wait_time = between(1.0, 3.0)

    # Credentials read from environment; never hard-coded.
    _email: str = os.environ.get("ADMIN_EMAIL", "")
    _password: str = os.environ.get("ADMIN_PASSWORD", "")

    def on_start(self):
        """Validate that credentials are configured before tasks run."""
        if not self._email or not self._password:
            raise RuntimeError(
                "AdminUser requires ADMIN_EMAIL and ADMIN_PASSWORD env vars."
            )

    @task(2)
    def health_check(self):
        """GET /health — expected p95 < 50 ms (PLANEJAMENTO.md §13)."""
        with self.client.get("/health", catch_response=True) as resp:
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                resp.success()
            else:
                resp.failure(f"Unexpected response: {resp.status_code} {resp.text[:80]}")

    @task(1)
    def login(self):
        """POST /auth/login — expected p95 < 500 ms (PLANEJAMENTO.md §13).

        bcrypt verification (work factor 12) is the dominant cost (~200 ms).
        The 500 ms budget includes DB round-trip and ASGI overhead.
        """
        with self.client.post(
            "/auth/login",
            json={"email": self._email, "password": self._password},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Login failed: invalid credentials — check ADMIN_EMAIL/ADMIN_PASSWORD")
            else:
                resp.failure(f"Unexpected status {resp.status_code}: {resp.text[:80]}")
