"""Redis session storage (Activity 4).

Why sessions belong in a cache and not in PostgreSQL. A session is small,
hot, read on every single request, and it is *meant* to disappear on its own.
That is the exact shape Redis is built for, and it buys three things the
relational table could not give us:

1. Idle expiry stops being application logic. Instead of storing a timestamp
   and comparing it on every read, the key carries a TTL and Redis deletes it.
   Refreshing the session is one `EXPIRE` call.
2. Expired sessions cost nothing. No rows accumulate, no cleanup job.
3. Several workers share one session store without touching the database, so
   the API can be scaled out horizontally.

Why this class is interchangeable with PostgresSessions. Both satisfy the
same `Sessions` protocol, so choosing one is a single line in the
dependency-injection container. The domain service is unaware of either.

Key layout — two keys, kept in sync:

    session:<digest>  → hash with the session and its owner. TTL = idle limit.
    user:<user_id>    → the digest of that user's active session. Same TTL.

The second key is what enforces "one active session per user": it is how we
find the previous session in order to replace it. In PostgreSQL that was a
unique constraint; here it is an explicit index we maintain, which is the
usual trade when moving to a key-value store.

The absolute expiry stays inside the payload and is checked by the domain.
Only the idle limit is delegated to the TTL, because that is the one that
must move forward every time the session is used.
"""

from datetime import datetime

import redis.asyncio as redis

from app.authentication.domain.ports import Session
from app.core.domain import Actor

SESSION_KEY = "session:{}"
USER_KEY = "user:{}"


def _encode(value: datetime) -> str:
    return value.isoformat()


def _decode(value: str) -> datetime:
    return datetime.fromisoformat(value)


class RedisSessions:
    def __init__(self, url, idle_timeout_seconds):
        # decode_responses keeps this adapter working with str instead of
        # bytes, which is what the domain objects expect.
        self._redis = redis.from_url(url, decode_responses=True)
        self.idle_timeout_seconds = idle_timeout_seconds

    async def close(self):
        await self._redis.aclose()

    async def by_user(self, user_id):
        digest = await self._redis.get(USER_KEY.format(user_id))
        if digest is None:
            return None
        found = await self.by_digest(digest)
        return found[0] if found else None

    async def by_digest(self, digest):
        data = await self._redis.hgetall(SESSION_KEY.format(digest))
        if not data:
            # Either it never existed or Redis already expired it. From the
            # caller's point of view those are the same answer.
            return None
        session = Session(
            user_id=int(data["user_id"]),
            digest=digest,
            created_at=_decode(data["created_at"]),
            last_seen_at=_decode(data["last_seen_at"]),
            expires_at=_decode(data["expires_at"]),
        )
        return session, Actor(int(data["user_id"]), data["email"])

    async def replace(self, session, email):
        """Store the session and make it the only active one for its user.

        Both keys are written in a single pipeline so a crash cannot leave a
        session without its user index (which would silently break the
        one-session-per-user rule).
        """
        previous = await self._redis.get(USER_KEY.format(session.user_id))

        pipe = self._redis.pipeline()
        if previous is not None and previous != session.digest:
            pipe.delete(SESSION_KEY.format(previous))
        pipe.hset(
            SESSION_KEY.format(session.digest),
            mapping={
                "user_id": str(session.user_id),
                "email": email,
                "created_at": _encode(session.created_at),
                "last_seen_at": _encode(session.last_seen_at),
                "expires_at": _encode(session.expires_at),
            },
        )
        pipe.expire(SESSION_KEY.format(session.digest), self.idle_timeout_seconds)
        pipe.set(
            USER_KEY.format(session.user_id),
            session.digest,
            ex=self.idle_timeout_seconds,
        )
        await pipe.execute()

    async def touch(self, digest, now):
        """Register activity: update last_seen_at and push the TTL forward.

        This is the method that makes Redis worth it. The idle window is not
        computed anywhere — it is simply the remaining life of the key.
        """
        found = await self.by_digest(digest)
        if found is None:
            return

        session, _ = found
        pipe = self._redis.pipeline()
        pipe.hset(SESSION_KEY.format(digest), "last_seen_at", _encode(now))
        pipe.expire(SESSION_KEY.format(digest), self.idle_timeout_seconds)
        pipe.expire(USER_KEY.format(session.user_id), self.idle_timeout_seconds)
        await pipe.execute()

    async def remove(self, digest):
        """Revoke a session. Returns whether there was one to revoke."""
        found = await self.by_digest(digest)
        if found is None:
            return False

        session, _ = found
        pipe = self._redis.pipeline()
        pipe.delete(SESSION_KEY.format(digest))
        pipe.delete(USER_KEY.format(session.user_id))
        await pipe.execute()
        return True
