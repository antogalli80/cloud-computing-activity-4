from fastapi import FastAPI

from app.application import FILES_TAG_METADATA, HEALTH_TAG_METADATA, create_application
from app.files.dependency_injection.container import get_content_storage
from app.files.router import router


async def ensure_bucket():
    """Create the object-storage bucket if it is missing.

    Idempotent, so a fresh environment works on the first upload instead of
    failing. The local adapter has no bucket, so it simply has no such method
    and this hook is skipped.
    """
    storage = get_content_storage()
    if hasattr(storage, "ensure_bucket"):
        await storage.ensure_bucket()


async def object_storage_ready():
    """Readiness probe for the object store: sign a URL for a key that does
    not need to exist. It exercises credentials and configuration without
    writing anything."""
    storage = get_content_storage()
    if hasattr(storage, "shareable_url"):
        await storage.shareable_url("readiness-probe", "readiness-probe")


def create_files_app() -> FastAPI:
    """Create the independently deployable Files API."""

    application = create_application(
        service_name="Files",
        description="User-owned file metadata, content, and PDF merge service.",
        tags_metadata=[HEALTH_TAG_METADATA, FILES_TAG_METADATA],
        startup_hooks=[ensure_bucket],
        readiness_checks=[object_storage_ready],
    )
    application.include_router(router)
    return application


app = create_files_app()
