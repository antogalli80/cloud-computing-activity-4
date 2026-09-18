"""Composition root for the Authentication app.

This is the only file that names concrete implementations. Everything else
depends on the protocols in `domain/ports.py`, which is what makes the
storage backends interchangeable: switching sessions from PostgreSQL to
Redis is the single line marked below, and no domain code changes with it.
"""

from functools import lru_cache

from app.authentication.domain.service import AuthenticationService
from app.authentication.persistence.crypto import OpaqueTokens, ScryptPasswords
from app.authentication.persistence.redis_sessions import RedisSessions
from app.authentication.persistence.repositories import PostgresUsers
from app.config import get_settings
from app.core.audit import DatabaseAudit
from app.core.infrastructure import PostgresUnitOfWork, SystemClock


@lru_cache
def get_sessions():
    """The session store. Swap this for `PostgresSessions()` and the whole
    application keeps working — that is the point of the port.

    Redis is the right home for sessions: they are small, read on every
    request, shared across workers, and they are supposed to expire by
    themselves. The idle timeout is handed to Redis as a TTL instead of being
    recomputed in Python on every read.
    """
    settings = get_settings()
    return RedisSessions(settings.redis_url, settings.auth_session_idle_seconds)


@lru_cache
def get_service():
    settings = get_settings()
    return AuthenticationService(
        PostgresUsers(),
        get_sessions(),
        ScryptPasswords(),
        OpaqueTokens(),
        SystemClock(),
        DatabaseAudit("authentication"),
        PostgresUnitOfWork(),
        settings.auth_session_idle_seconds,
        settings.auth_session_absolute_seconds,
    )
