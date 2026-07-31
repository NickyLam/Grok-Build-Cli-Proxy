from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("grok_proxy.access")


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:16]}"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach X-Request-ID and emit structured access logs."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("x-request-id") or request.headers.get("X-Request-ID")
        if not rid:
            rid = new_request_id()
        request.state.request_id = rid
        t0 = time.time()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            duration_ms = int((time.time() - t0) * 1000)
            auth = getattr(request.state, "auth", None)
            actor = getattr(auth, "actor_id", None) if auth else None
            logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%s actor=%s",
                rid,
                request.method,
                request.url.path,
                status,
                duration_ms,
                actor or "-",
            )


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


def bind_log_fields(**fields: Any) -> str:
    return " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
