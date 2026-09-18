from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.domain import Context, DomainError
from app.files.domain.ports import File
from app.files.domain.service import FilesService
from app.files.persistence.content import LocalContentStorage
from app.files.persistence.pdf import PypdfMerger


class MemoryContent:
    def __init__(self):
        self.items = {}

    async def put(self, content):
        key = uuid4().hex
        self.items[key] = content
        return key

    async def get(self, key):
        return self.items[key]

    async def delete(self, key):
        # Idempotent, like both real adapters: an absent blob is a success.
        self.items.pop(key, None)

    async def shareable_url(self, key, filename):
        # An in-memory store has no address, same as the local volume.
        return None


class MemoryFiles:
    def __init__(self):
        self.items = {}

    async def create(self, owner, filename, description):
        now = datetime.now(timezone.utc)
        file = File(
            len(self.items) + 1, owner, filename, description, None, None, 0, None, now, now
        )
        self.items[file.id] = file
        return file

    async def get_owned(self, file_id, owner, *, lock=False):
        item = self.items.get(file_id)
        if item is None or item.owner_external_id != owner:
            raise DomainError("file_not_found")
        return item

    async def set_content(self, file_id, owner, key, content_type, size, sha256):
        item = await self.get_owned(file_id, owner)
        item = replace(
            item, content_key=key, content_type=content_type, size_bytes=size, sha256=sha256
        )
        self.items[file_id] = item
        return item

    async def list_owned(self, owner):
        return [f for f in self.items.values() if f.owner_external_id == owner]

    async def delete(self, file_id, owner):
        await self.get_owned(file_id, owner)
        del self.items[file_id]


class NoDatabaseTransaction:
    @asynccontextmanager
    async def transaction(self):
        yield


class RecordingAudit:
    def __init__(self):
        self.events = []

    async def record(self, event, context, **kw):
        self.events.append((event, kw))


@pytest.mark.parametrize("storage", ["memory", "volume"])
async def test_content_adapter_substitution_without_domain_change(storage, tmp_path):
    content = MemoryContent() if storage == "memory" else LocalContentStorage(tmp_path)
    audit = RecordingAudit()
    service = FilesService(
        MemoryFiles(), content, PypdfMerger(200, 10000), audit, NoDatabaseTransaction(), 1024
    )
    ctx = Context(str(uuid4()))
    item = await service.create(1, "sample", None, ctx)
    assert (await service.get(item.id, 1, ctx))[1] is None
    await service.upload(item.id, 1, b"content", "text/plain", ctx)
    assert (await service.get(item.id, 1, ctx))[1] == b"content"
    await service.delete(item.id, 1, ctx)
    assert await service.list_owned(1, ctx) == []
    assert "file_deleted" in [event for event, _ in audit.events]


@pytest.mark.parametrize("key", ["../secret", "/etc/passwd", "a" * 31, "g" * 32])
async def test_content_path_rejection(tmp_path, key):
    with pytest.raises(DomainError, match="content_unavailable"):
        await LocalContentStorage(tmp_path).get(key)


async def test_missing_content(tmp_path):
    with pytest.raises(DomainError, match="content_unavailable"):
        await LocalContentStorage(tmp_path).get("a" * 32)


@pytest.mark.parametrize("ids", [[1], [1, 1], list(range(11))])
async def test_domain_rejects_invalid_merge_before_storage(ids):
    service = FilesService(
        MemoryFiles(), MemoryContent(), None, RecordingAudit(), NoDatabaseTransaction(), 1024
    )
    with pytest.raises(DomainError, match="invalid_merge_sources"):
        await service.merge(ids, 1, Context(str(uuid4())))


async def test_domain_enforces_upload_limit():
    service = FilesService(
        MemoryFiles(), MemoryContent(), None, RecordingAudit(), NoDatabaseTransaction(), 1024
    )
    with pytest.raises(DomainError, match="upload_too_large"):
        await service.upload(1, 1, b"x" * 1025, "text/plain", Context(str(uuid4())))
