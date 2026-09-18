from fastapi import FastAPI

from app.application import (
    AUTHENTICATION_TAG_METADATA,
    FILES_TAG_METADATA,
    HEALTH_TAG_METADATA,
    create_application,
)
from app.authentication.router import router as authentication_router
from app.files.router import router as files_router

TAGS_METADATA = [
    HEALTH_TAG_METADATA,
    AUTHENTICATION_TAG_METADATA,
    FILES_TAG_METADATA,
]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    application = create_application(
        service_name=None,
        description=(
            "Combined development facade for the Authentication and Files APIs. "
            "Docker Compose runs each API as an independent service."
        ),
        tags_metadata=TAGS_METADATA,
    )

    application.include_router(authentication_router)
    application.include_router(files_router)

    return application


app = create_app()
