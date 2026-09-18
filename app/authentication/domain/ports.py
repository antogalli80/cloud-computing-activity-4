from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.domain import Actor


@dataclass(frozen=True)
class User:
    external_id: int
    email: str
    password_hash: str


@dataclass(frozen=True)
class Session:
    user_id: int
    digest: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class Users(Protocol):
    async def create(self, email: str, password_hash: str) -> User: ...
    async def by_email(self, email: str) -> User | None: ...
    async def lock(self, user_id: int) -> None: ...


class Sessions(Protocol):
    """Port for session storage.

    `replace` takes the owner's email even though the session itself does not
    carry it. The relational adapter ignores the argument because it can join
    on the user table; the Redis adapter needs it, because a key-value store
    has no joins and must denormalise. Exposing it in the port is what lets
    both implementations be swapped without the domain noticing.
    """

    async def by_user(self, user_id: int) -> Session | None: ...
    async def by_digest(self, digest: str) -> tuple[Session, Actor] | None: ...
    async def replace(self, session: Session, email: str) -> None: ...
    async def touch(self, digest: str, now: datetime) -> None: ...
    async def remove(self, digest: str) -> bool: ...


class Passwords(Protocol):
    async def hash(self, password: str) -> str: ...
    async def verify(self, password: str, encoded: str) -> bool: ...


class Tokens(Protocol):
    def generate(self) -> str: ...
    def digest(self, token: str) -> str: ...
