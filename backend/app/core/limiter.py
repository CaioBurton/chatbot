from slowapi import Limiter
from starlette.requests import Request


def _client_ip(request: Request) -> str:
    # nginx sets X-Real-IP to $remote_addr (the connecting client's IP,
    # not a client-controlled header) — use it when available so the limiter
    # sees the real user IP instead of the nginx container IP.
    return (
        request.headers.get("X-Real-IP")
        or (request.client.host if request.client else "127.0.0.1")
    )


limiter = Limiter(key_func=_client_ip)
