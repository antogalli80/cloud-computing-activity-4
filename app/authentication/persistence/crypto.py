import asyncio

from app.authentication.security import (
    digest_token,
    generate_opaque_token,
    hash_password,
    verify_password,
)


class ScryptPasswords:
    def __init__(self):
        self.dummy = hash_password("dummy-identity-does-not-exist")

    async def hash(self, password):
        return await asyncio.to_thread(hash_password, password)

    async def verify(self, password, encoded):
        return await asyncio.to_thread(verify_password, password, encoded or self.dummy)


class OpaqueTokens:
    generate = staticmethod(generate_opaque_token)
    digest = staticmethod(digest_token)
