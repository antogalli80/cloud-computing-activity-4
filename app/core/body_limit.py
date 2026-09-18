from starlette.responses import JSONResponse

from app.core.audit import DatabaseAudit
from app.core.domain import Context
from app.middleware import request_id_from_header


class BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Bound the complete request before multipart parsing can exhaust temporary disk."""

    def __init__(self, app, limit=6 * 1024 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        try:
            headers = dict(scope.get("headers", []))
            length = headers.get(b"content-length", b"0")
            if length.isdigit() and int(length) > self.limit:
                raise BodyTooLarge()
            # Enforce streaming limits before the multipart parser can catch the
            # exception and turn a size rejection into a generic parsing error.
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.limit:
                    raise BodyTooLarge()
                if not message.get("more_body", False):
                    break
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, bounded_receive, send)
        except BodyTooLarge:
            rid = request_id_from_header(headers.get(b"x-request-id", b"").decode(errors="ignore"))
            await DatabaseAudit("api").record("request_too_large", Context(rid), outcome="rejected")
            response = JSONResponse(
                {
                    "status": "error",
                    "code": "upload_too_large",
                    "message": "Request body limit exceeded.",
                },
                status_code=413,
                headers={"X-Request-ID": rid},
            )
            await response(scope, receive, send)
