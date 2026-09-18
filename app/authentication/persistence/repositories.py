from tortoise.exceptions import IntegrityError

from app.authentication.domain.ports import Session, User
from app.authentication.models import SessionModel, UserModel
from app.core.domain import Actor, DomainError


def session_bo(row):
    return Session(row.user_id, row.digest, row.created_at, row.last_seen_at, row.expires_at)


class PostgresUsers:
    async def create(self, email, password_hash):
        try:
            row = await UserModel.create(email=email, password_hash=password_hash)
        except IntegrityError as exc:
            raise DomainError("user_already_exists") from exc
        return User(row.id, row.email, row.password_hash)

    async def by_email(self, email):
        row = await UserModel.get_or_none(email=email)
        return User(row.id, row.email, row.password_hash) if row else None

    async def lock(self, user_id):
        await UserModel.filter(id=user_id).select_for_update().get()


class PostgresSessions:
    async def by_user(self, user_id):
        row = await SessionModel.get_or_none(user_id=user_id)
        return session_bo(row) if row else None

    async def by_digest(self, digest):
        row = await SessionModel.filter(digest=digest).select_for_update().first()
        if not row:
            return None
        user = await row.user
        return session_bo(row), Actor(user.id, user.email)

    async def replace(self, session, email=None):
        # `email` is part of the port for the key-value adapter's sake; here
        # the foreign key already gives us the user, so it is unused.
        await SessionModel.filter(user_id=session.user_id).delete()
        await SessionModel.create(
            user_id=session.user_id,
            digest=session.digest,
            created_at=session.created_at,
            last_seen_at=session.last_seen_at,
            expires_at=session.expires_at,
        )

    async def touch(self, digest, now):
        await SessionModel.filter(digest=digest).update(last_seen_at=now)

    async def remove(self, digest):
        return bool(await SessionModel.filter(digest=digest).delete())
