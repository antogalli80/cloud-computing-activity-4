import os

import pytest_asyncio
from aerich import Command
from tortoise import Tortoise, connections

from app.database import TORTOISE_ORM


@pytest_asyncio.fixture
async def db():
    # Only the dedicated disposable test database may be reset.
    url = os.environ["APP_DATABASE_URL"]
    assert url.endswith("/cloud3_test"), "Refusing to reset a non-test database"
    await Tortoise.init(config=TORTOISE_ORM)
    await connections.get("default").execute_script(
        "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    )
    await Tortoise.close_connections()
    command = Command(tortoise_config=TORTOISE_ORM, app="models", location="./migrations")
    await command.init()
    await command.upgrade(run_in_transaction=True)
    yield
    await Tortoise.close_connections()


@pytest_asyncio.fixture
async def services(db, tmp_path):
    """Build both domain services with the *local* adapters.

    This is the interchangeability of Activity 4 demonstrated rather than
    claimed: production wires Redis and S3 through the dependency-injection
    containers, these tests wire PostgreSQL and a temporary directory, and
    the domain services are the same objects in both cases. Not a single line
    of `AuthenticationService` or `FilesService` knows the difference.

    It also keeps the domain suite fast and dependency-free: no Redis and no
    MinIO are needed to test business rules. The adapters themselves are
    covered separately in test_redis_sessions.py and test_s3_storage.py.
    """
    from app.authentication.domain.service import AuthenticationService
    from app.authentication.persistence.crypto import OpaqueTokens, ScryptPasswords
    from app.authentication.persistence.repositories import PostgresSessions, PostgresUsers
    from app.config import get_settings
    from app.core.audit import DatabaseAudit
    from app.core.infrastructure import PostgresUnitOfWork, SystemClock
    from app.files.domain.service import FilesService
    from app.files.persistence.content import LocalContentStorage
    from app.files.persistence.pdf import PypdfMerger
    from app.files.persistence.repository import PostgresFiles

    settings = get_settings()
    auth = AuthenticationService(
        PostgresUsers(),
        PostgresSessions(),
        ScryptPasswords(),
        OpaqueTokens(),
        SystemClock(),
        DatabaseAudit("authentication"),
        PostgresUnitOfWork(),
        settings.auth_session_idle_seconds,
        settings.auth_session_absolute_seconds,
    )
    files = FilesService(
        PostgresFiles(),
        LocalContentStorage(tmp_path),
        PypdfMerger(200, 10485760),
        DatabaseAudit("files"),
        PostgresUnitOfWork(),
        5242880,
    )
    return auth, files
