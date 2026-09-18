import httpx

from app.core.domain import Actor, DomainError


class HttpTokenIntrospector:
    def __init__(self, url, timeout):
        self.url, self.timeout = url, timeout

    async def introspect(self, token, request_id):
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.url + "/authentication/introspect",
                    headers={"Auth": token, "X-Request-ID": request_id},
                )
            if response.status_code in (401, 422):
                raise DomainError("invalid_session")
            if response.status_code != 200:
                raise DomainError("authentication_unavailable")
            data = response.json()
            user = data["user"]
            if (
                data.get("active") is not True
                or data.get("status") != "success"
                or not isinstance(user["external_id"], int)
                or isinstance(user["external_id"], bool)
                or user["external_id"] < 1
                or not isinstance(user["email"], str)
            ):
                raise ValueError("Invalid introspection contract")
            return Actor(user["external_id"], user["email"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise DomainError("authentication_unavailable") from exc
