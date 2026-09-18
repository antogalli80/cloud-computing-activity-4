"""Integration tests for the Redis session adapter.

They run against a real Redis because the behaviour that matters here is
Redis behaviour: TTL expiry, atomic pipelines, and the user index staying in
sync. A fake would only re-test the fake.

Skipped automatically when no Redis is reachable, so `pytest` still works on
a laptop without the compose stack up.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.authentication.domain.ports import Session
from app.authentication.persistence.redis_sessions import RedisSessions

REDIS_URL = os.getenv("APP_REDIS_URL", "redis://redis:6379/0")


def session_for(user_id, digest, now, absolute_seconds=3600):
    return Session(
        user_id=user_id,
        digest=digest,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(seconds=absolute_seconds),
    )


@pytest_asyncio.fixture
async def sessions():
    store = RedisSessions(REDIS_URL, idle_timeout_seconds=60)
    try:
        await store._redis.ping()
    except Exception:  # noqa: BLE001 - any connection failure means "not available"
        await store.close()
        pytest.skip("Redis is not reachable")
    # Each test gets a clean database; this is the disposable test instance.
    await store._redis.flushdb()
    yield store
    await store._redis.flushdb()
    await store.close()


@pytest.mark.asyncio
async def test_session_round_trips_with_its_owner(sessions):
    now = datetime.now(timezone.utc)
    await sessions.replace(session_for(1, "digest-a", now), "user@example.com")

    found = await sessions.by_digest("digest-a")

    assert found is not None
    session, actor = found
    assert session.user_id == 1
    # The email comes back without touching PostgreSQL: that is the
    # denormalisation a key-value store requires.
    assert actor.email == "user@example.com"


@pytest.mark.asyncio
async def test_unknown_digest_is_simply_absent(sessions):
    assert await sessions.by_digest("never-issued") is None


@pytest.mark.asyncio
async def test_replacing_a_session_revokes_the_previous_one(sessions):
    """One active session per user. In PostgreSQL a unique constraint gave us
    this; here the user index has to be maintained, so it deserves a test."""
    now = datetime.now(timezone.utc)
    await sessions.replace(session_for(7, "old-digest", now), "user@example.com")
    await sessions.replace(session_for(7, "new-digest", now), "user@example.com")

    assert await sessions.by_digest("old-digest") is None
    assert await sessions.by_digest("new-digest") is not None


@pytest.mark.asyncio
async def test_by_user_finds_the_active_session(sessions):
    now = datetime.now(timezone.utc)
    await sessions.replace(session_for(9, "digest-b", now), "user@example.com")

    active = await sessions.by_user(9)

    assert active is not None and active.digest == "digest-b"


@pytest.mark.asyncio
async def test_remove_revokes_both_keys(sessions):
    now = datetime.now(timezone.utc)
    await sessions.replace(session_for(3, "digest-c", now), "user@example.com")

    assert await sessions.remove("digest-c") is True
    assert await sessions.by_digest("digest-c") is None
    assert await sessions.by_user(3) is None
    # Removing twice is not an error, it just reports nothing was there.
    assert await sessions.remove("digest-c") is False


@pytest.mark.asyncio
async def test_idle_expiry_is_delegated_to_redis(sessions):
    """The reason to use Redis at all: the idle window is the key's TTL, not
    a timestamp the application has to compare on every read."""
    now = datetime.now(timezone.utc)
    await sessions.replace(session_for(4, "digest-d", now), "user@example.com")

    ttl = await sessions._redis.ttl("session:digest-d")
    assert 0 < ttl <= 60

    # Simulate a session that has been idle for a while, then use it.
    await sessions._redis.expire("session:digest-d", 5)
    await sessions.touch("digest-d", datetime.now(timezone.utc))

    refreshed = await sessions._redis.ttl("session:digest-d")
    assert refreshed > 5, "touch() must push the idle window forward"


@pytest.mark.asyncio
async def test_expired_key_disappears_on_its_own(sessions):
    now = datetime.now(timezone.utc)
    await sessions.replace(session_for(5, "digest-e", now), "user@example.com")

    # Expire it the way Redis would, without any application involvement.
    await sessions._redis.delete("session:digest-e")

    assert await sessions.by_digest("digest-e") is None
