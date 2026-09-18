from datetime import timedelta

from app.authentication.domain.ports import Passwords, Session, Sessions, Tokens, Users
from app.core.domain import AuditSink, Clock, Context, DomainError, UnitOfWork


class AuthenticationService:
    def __init__(
        self,
        users: Users,
        sessions: Sessions,
        passwords: Passwords,
        tokens: Tokens,
        clock: Clock,
        audit: AuditSink,
        uow: UnitOfWork,
        idle: int,
        absolute: int,
    ):
        self.users, self.sessions, self.passwords, self.tokens = users, sessions, passwords, tokens
        self.clock, self.audit, self.uow = clock, audit, uow
        self.idle, self.absolute = idle, absolute

    async def register(self, email: str, password: str, ctx: Context):
        encoded = await self.passwords.hash(password)
        async with self.uow.transaction():
            user = await self.users.create(email, encoded)
            await self.audit.record("user_registered", ctx, actor_id=user.external_id)
        return user

    def expired(self, session: Session, now):
        return now >= min(session.expires_at, session.last_seen_at + timedelta(seconds=self.idle))

    async def login(self, email: str, password: str, ctx: Context):
        user = await self.users.by_email(email)
        valid = await self.passwords.verify(password, user.password_hash if user else "")
        if user is None or not valid:
            raise DomainError("invalid_credentials")
        token = self.tokens.generate()
        async with self.uow.transaction():
            await self.users.lock(user.external_id)
            now = self.clock.now()
            old = await self.sessions.by_user(user.external_id)
            if old and not self.expired(old, now):
                raise DomainError("active_session_exists")
            session = Session(
                user.external_id,
                self.tokens.digest(token),
                now,
                now,
                now + timedelta(seconds=self.absolute),
            )
            await self.sessions.replace(session, user.email)
            await self.audit.record("session_login", ctx, actor_id=user.external_id)
        return token, session

    async def introspect(self, token: str, ctx: Context):
        async with self.uow.transaction():
            pair = await self.sessions.by_digest(self.tokens.digest(token))
            if pair is None:
                raise DomainError("invalid_session")
            session, actor = pair
            now = self.clock.now()
            if self.expired(session, now):
                raise DomainError("session_expired")
            await self.sessions.touch(session.digest, now)
            await self.audit.record("session_introspection", ctx, actor_id=actor.external_id)
        return session, actor, min(now + timedelta(seconds=self.idle), session.expires_at)

    async def logout(self, token: str, ctx: Context):
        async with self.uow.transaction():
            pair = await self.sessions.by_digest(self.tokens.digest(token))
            if pair is None:
                raise DomainError("invalid_session")
            session, actor = pair
            await self.sessions.remove(session.digest)
            await self.audit.record("session_logout", ctx, actor_id=actor.external_id)
