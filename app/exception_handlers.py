import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.middleware import REQUEST_ID_HEADER
from app.schemas import ErrorResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Represent an expected API error with a safe public contract."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


HTTP_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: (
        "bad_request",
        "The request could not be processed.",
    ),
    status.HTTP_404_NOT_FOUND: (
        "not_found",
        "The requested resource was not found.",
    ),
    status.HTTP_405_METHOD_NOT_ALLOWED: (
        "method_not_allowed",
        "The requested method is not allowed.",
    ),
}


def build_error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Build a consistent JSON error response."""

    request_id = getattr(request.state, "request_id", None)
    headers = {REQUEST_ID_HEADER: str(request_id)} if request_id else {}

    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(code=code, message=message).model_dump(),
        headers=headers,
    )


async def http_exception_handler(
    request: Request,
    exception: StarletteHTTPException,
) -> JSONResponse:
    """Handle HTTP errors with the standard response schema."""

    code, message = HTTP_ERROR_RESPONSES.get(
        exception.status_code,
        ("http_error", "The request could not be completed."),
    )
    return build_error_response(
        request,
        exception.status_code,
        code,
        message,
    )


async def validation_exception_handler(
    request: Request,
    _exception: RequestValidationError,
) -> JSONResponse:
    """Handle request validation errors without exposing internals."""

    from app.core.audit import DatabaseAudit
    from app.core.domain import Context

    await DatabaseAudit("api").record(
        "validation_rejected", Context(request.state.request_id), outcome="rejected"
    )
    return build_error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        "The request contains invalid data.",
    )


async def api_error_handler(request: Request, exception: ApiError) -> JSONResponse:
    """Handle expected domain errors without exposing internal state."""

    return build_error_response(
        request,
        exception.status_code,
        exception.code,
        exception.message,
    )


async def unhandled_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Handle unexpected errors without exposing implementation details."""

    logger.error("Unhandled application exception", extra={"error_type": type(exception).__name__})
    # Never include SQL parameters, credentials or exception text in logs.
    from app.core.audit import DatabaseAudit
    from app.core.domain import Context

    try:
        await DatabaseAudit("api").record(
            "operation_failed", Context(request.state.request_id), outcome="failed"
        )
    except Exception:
        logger.critical("Audit database unavailable; operation failed closed.")
    return build_error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_server_error",
        "An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all application exception handlers."""

    from app.core.api_errors import domain_error_handler
    from app.core.domain import DomainError

    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
