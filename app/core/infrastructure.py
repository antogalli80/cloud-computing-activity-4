from contextlib import asynccontextmanager
from datetime import datetime, timezone

from tortoise.transactions import in_transaction


class SystemClock:
    def now(self):
        return datetime.now(timezone.utc)


class PostgresUnitOfWork:
    @asynccontextmanager
    async def transaction(self):
        async with in_transaction():
            yield
