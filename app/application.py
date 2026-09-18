from collections.abc import Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI, status

from app.config import get_settings
from app.database import lifespan
from app.exception_handlers import register_exception_handlers
from app.logging import configure_logging
from app.middleware import register_middleware
from app.schemas import ErrorResponse, SuccessResponse

HEALTH_TAG_METADATA = {
    "name": "Health",
    "description": "Application health and readiness endpoints.",
}
AUTHENTICATION_TAG_METADATA = {
    "name": "Authentication",
    "description": "User registration and session lifecycle endpoints.",
}
FILES_TAG_METADATA = {
    "name": "Files",
    "description": "File metadata, content, and PDF merge endpoints.",
}


def documented_error(
    description: str,
    code: str,
    message: str,
) -> dict[str, object]:
    """Build an OpenAPI error response with a status-specific example."""

    return {
        "model": ErrorResponse,
        "description": description,
        "content": {
            "application/json": {
                "example": {
                    "status": "error",
                    "code": code,
                    "message": message,
                }
            }
        },
    }


ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {
        **documented_error(
            "Bad Request",
            "bad_request",
            "The request could not be processed.",
        )
    },
    status.HTTP_401_UNAUTHORIZED: documented_error(
        "Unauthorized",
        "unauthorized",
        "Authentication is required or has failed.",
    ),
    status.HTTP_404_NOT_FOUND: documented_error(
        "Not Found",
        "not_found",
        "The requested resource was not found.",
    ),
    status.HTTP_405_METHOD_NOT_ALLOWED: documented_error(
        "Method Not Allowed",
        "method_not_allowed",
        "The HTTP method is not allowed for this resource.",
    ),
    status.HTTP_409_CONFLICT: documented_error(
        "Conflict",
        "conflict",
        "The request conflicts with the current resource state.",
    ),
    status.HTTP_422_UNPROCESSABLE_CONTENT: documented_error(
        "Unprocessable Content",
        "validation_error",
        "The request data is invalid.",
    ),
    status.HTTP_500_INTERNAL_SERVER_ERROR: documented_error(
        "Internal Server Error",
        "internal_server_error",
        "An unexpected error occurred.",
    ),
}


def build_lifespan(startup_hooks):
    """Wrap the database lifespan with per-service startup work.

    Each app has different infrastructure to prepare (Files needs its object
    storage bucket to exist), so the factory stays generic and every service
    passes its own hooks instead of this file knowing about Redis or S3.
    """

    @asynccontextmanager
    async def combined(app):
        async with lifespan(app):
            for hook in startup_hooks:
                await hook()
            yield

    return combined


def create_application(
    *,
    service_name: str | None,
    description: str,
    tags_metadata: Sequence[dict[str, str]],
    startup_hooks: Sequence = (),
    readiness_checks: Sequence = (),
) -> FastAPI:
    """Create a consistently configured FastAPI service.

    `readiness_checks` are awaited by `/ready` on top of the database probe,
    so each service reports on the backends it actually depends on.
    """

    settings = get_settings()
    configure_logging(settings.log_level)
    title = settings.name if service_name is None else f"{settings.name} - {service_name}"

    application = FastAPI(
        title=title,
        lifespan=build_lifespan(list(startup_hooks)),
        version=settings.version,
        description=description,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=list(tags_metadata),
        responses=ERROR_RESPONSES,
    )

    register_middleware(application)
    from app.core.body_limit import BodyLimitMiddleware

    application.add_middleware(BodyLimitMiddleware)
    register_exception_handlers(application)

    @application.get(
        "/healthcheck",
        response_model=SuccessResponse,
        status_code=status.HTTP_200_OK,
        operation_id="healthcheck",
        summary="Check service health",
        tags=["Health"],
    )
    async def healthcheck() -> SuccessResponse:
        """Return the standard availability response."""

        return SuccessResponse()

    @application.get("/ready", tags=["Health"])
    async def ready():
        """Readiness: every backend this service needs is actually answering.

        Distinct from /healthcheck, which only says the process is alive. A
        container that responds here is safe to send traffic to.
        """
        from tortoise import connections

        await connections.get("default").execute_query("SELECT 1")
        for check in readiness_checks:
            await check()
        return {"status": "success"}

    return application
