from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.domain import Actor


@dataclass(frozen=True)
class File:
    id: int
    owner_external_id: int
    filename: str
    description: str | None
    content_key: str | None
    content_type: str | None
    size_bytes: int
    sha256: str | None
    created_at: datetime
    updated_at: datetime


class FileRepository(Protocol):
    async def create(self, owner: int, filename: str, description: str | None) -> File: ...
    async def list_owned(self, owner: int) -> list[File]: ...
    async def get_owned(self, file_id: int, owner: int, *, lock: bool = False) -> File: ...
    async def set_content(
        self, file_id: int, owner: int, key: str, content_type: str, size: int, sha256: str
    ) -> File: ...
    async def delete(self, file_id: int, owner: int) -> None: ...


class ContentStorage(Protocol):
    """Port for binary content. Every method is storage-agnostic on purpose:
    the domain never learns whether the bytes live on a volume or in S3.

    `shareable_url` returns None when the backend cannot produce one. That is
    a capability, not a failure: the local adapter has no way to hand out a
    direct link, while S3 can sign a temporary URL so downloads bypass the
    API entirely instead of streaming through it.
    """

    async def put(self, content: bytes) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def shareable_url(self, key: str, filename: str) -> str | None: ...


class PdfMerger(Protocol):
    async def merge(self, contents: list[bytes]) -> bytes: ...


class TokenIntrospector(Protocol):
    async def introspect(self, token: str, request_id: str) -> Actor: ...
