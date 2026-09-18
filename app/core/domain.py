from dataclasses import dataclass
from datetime import datetime
from typing import AsyncContextManager, Protocol


class DomainError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Actor:
    external_id: int
    email: str


@dataclass(frozen=True)
class Context:
    request_id: str


class Clock(Protocol):
    def now(self) -> datetime: ...


class AuditSink(Protocol):
    async def record(
        self,
        event: str,
        context: Context,
        *,
        actor_id: int | None = None,
        resource_id: int | None = None,
        outcome: str = "success",
    ) -> None: ...


class UnitOfWork(Protocol):
    def transaction(self) -> AsyncContextManager[None]: ...
