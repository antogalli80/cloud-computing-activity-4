from fastapi import FastAPI

from app.application import (
    AUTHENTICATION_TAG_METADATA,
    HEALTH_TAG_METADATA,
    create_application,
)
from app.authentication.dependency_injection.container import get_sessions
from app.authentication.router import router


async def session_store_ready():
    """Readiness probe for the session store.

    Reading a digest that does not exist is the cheapest round trip that
    still proves the connection works; the adapter answers None and nothing
    is written.
    """
    await get_sessions().by_digest("readiness-probe")


def create_authentication_app() -> FastAPI:
    """Create the independently deployable Authentication API."""

    application = create_application(
        service_name="Authentication",
        description="User registration, authentication, and session introspection service.",
        tags_metadata=[HEALTH_TAG_METADATA, AUTHENTICATION_TAG_METADATA],
        readiness_checks=[session_store_ready],
    )
    application.include_router(router)
    return application


app = create_authentication_app()
