import os
from contextlib import asynccontextmanager

from tortoise import Tortoise

from app.config import get_settings

TORTOISE_ORM = {
    # `or` instead of a getenv default on purpose: the default argument would
    # be evaluated eagerly, so get_settings() would run even for the migration
    # containers. Those only receive MIGRATION_DATABASE_URL and none of the
    # S3 credentials, and Settings refuses to build without them — migrations
    # would fail on configuration they do not need.
    "connections": {"default": os.getenv("MIGRATION_DATABASE_URL") or get_settings().database_url},
    "apps": {
        "models": {
            "models": [
                "app.authentication.models",
                "app.files.models",
                "app.core.audit",
                "aerich.models",
            ],
            "default_connection": "default",
        }
    },
    "use_tz": True,
    "timezone": "UTC",
}


@asynccontextmanager
async def lifespan(app):
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        yield
    finally:
        await Tortoise.close_connections()
