import logging
import time
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, Response, status

logger = logging.getLogger(__name__)
REQUEST_ID_HEADER = "X-Request-ID"
CallNext = Callable[[Request], Awaitable[Response]]


def request_id_from_header(value: str | None) -> str:
    """Reuse valid UUID request IDs so calls can be correlated across services."""

    if value:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


def register_middleware(app: FastAPI) -> None:
    """Register request tracing and structured access logging."""

    @app.middleware("http")
    async def log_requests(request: Request, call_next: CallNext) -> Response:
        request_id = request_id_from_header(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started_at = time.perf_counter()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": status_code,
                    "duration_ms": duration_ms,
                },
            )
