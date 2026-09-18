"""Integration tests for the S3 object-storage adapter.

Run against MinIO, which speaks the real S3 API, so these exercise actual
signing, bucket handling and error mapping rather than a stub. Skipped when
the endpoint is unreachable.
"""

import os
from urllib.parse import urlparse

import pytest
import pytest_asyncio

from app.core.domain import DomainError
from app.files.persistence.s3 import S3ContentStorage

ENDPOINT = os.getenv("APP_S3_ENDPOINT_URL", "http://minio:9000")
ACCESS_KEY = os.getenv("APP_S3_ACCESS_KEY", "")
SECRET_KEY = os.getenv("APP_S3_SECRET_KEY", "")


@pytest_asyncio.fixture
async def storage():
    if not ACCESS_KEY or not SECRET_KEY:
        pytest.skip("S3 credentials are not configured")

    store = S3ContentStorage(
        endpoint_url=ENDPOINT,
        region=os.getenv("APP_S3_REGION", "us-east-1"),
        bucket=os.getenv("APP_S3_BUCKET", "activity4-content") + "-test",
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        url_expiry_seconds=900,
    )
    try:
        await store.ensure_bucket()
    except Exception:  # noqa: BLE001 - any failure means the store is unavailable
        pytest.skip("Object storage is not reachable")
    return store


@pytest.mark.asyncio
async def test_content_round_trips(storage):
    key = await storage.put(b"activity 4 content")

    assert await storage.get(key) == b"activity 4 content"


@pytest.mark.asyncio
async def test_keys_are_opaque_and_unique(storage):
    """The key never derives from the filename: a user-supplied name must not
    reach the storage layer, and two uploads must never collide."""
    first = await storage.put(b"same bytes")
    second = await storage.put(b"same bytes")

    assert first != second
    assert first.isalnum() and len(first) == 32


@pytest.mark.asyncio
async def test_missing_object_is_a_domain_error(storage):
    """Infrastructure failures are translated at the boundary, so the domain
    never sees a botocore exception."""
    with pytest.raises(DomainError):
        await storage.get("0" * 32)


@pytest.mark.asyncio
async def test_delete_removes_the_object_and_is_idempotent(storage):
    key = await storage.put(b"to be deleted")

    await storage.delete(key)
    with pytest.raises(DomainError):
        await storage.get(key)

    # Deleting again is a success: the caller only needs the guarantee that
    # the object is gone.
    await storage.delete(key)


@pytest.mark.asyncio
async def test_shareable_url_is_signed_and_temporary(storage):
    """The operational payoff of object storage: the client downloads straight
    from the store, so a large file never occupies an API worker."""
    key = await storage.put(b"shared bytes")

    url = await storage.shareable_url(key, "report.pdf")

    assert url is not None
    query = urlparse(url).query
    assert "X-Amz-Signature" in query, "the URL must be signed"
    assert "X-Amz-Expires" in query, "the URL must expire on its own"
    assert "report.pdf" in url, "the display name is restored on download"


@pytest.mark.asyncio
async def test_ensure_bucket_can_be_called_repeatedly(storage):
    """It runs on every start, so it has to be idempotent."""
    await storage.ensure_bucket()
    await storage.ensure_bucket()
