import asyncio
import os
import re
from pathlib import Path
from uuid import uuid4

from app.core.domain import DomainError


class LocalContentStorage:
    """Local volume adapter: immutable opaque keys, never user-provided paths.

    Kept alongside the S3 adapter on purpose: it is the second implementation
    that proves ContentStorage is a real port, and the domain test suite uses
    it so business rules can be tested without object storage.
    """

    def __init__(self, root):
        self.root = Path(root).resolve()

    def _path(self, key):
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            raise DomainError("content_unavailable")
        return self.root / key

    async def put(self, content):
        key = uuid4().hex

        def write():
            self.root.mkdir(parents=True, exist_ok=True)
            with self._path(key).open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            directory_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

        await asyncio.to_thread(write)
        return key

    async def get(self, key):
        try:
            return await asyncio.to_thread(self._path(key).read_bytes)
        except OSError as exc:
            raise DomainError("content_unavailable") from exc

    async def delete(self, key):
        # missing_ok: deleting an absent blob is a success, not an error. The
        # caller only needs the guarantee that the object is gone afterwards.
        await asyncio.to_thread(self._path(key).unlink, True)

    async def shareable_url(self, key, filename):
        # A volume has no addressable URL. Returning None keeps this adapter a
        # valid ContentStorage; the API simply omits the link.
        return None
