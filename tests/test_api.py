from io import BytesIO
from uuid import uuid4

import httpx
import pytest
from pypdf import PdfWriter

from app.authentication.dependency_injection.container import get_service as get_auth
from app.authentication.main import app as auth_app
from app.core.audit import AuditEvent
from app.core.domain import Context
from app.files.dependency_injection.container import get_introspector
from app.files.dependency_injection.container import get_service as get_files
from app.files.main import app as files_app


@pytest.fixture
def clients(services):
    auth, files = services

    class TestIntrospector:
        async def introspect(self, token, request_id):
            _, actor, _ = await auth.introspect(token, Context(request_id))
            return actor

    auth_app.dependency_overrides[get_auth] = lambda: auth
    files_app.dependency_overrides[get_files] = lambda: files
    files_app.dependency_overrides[get_introspector] = lambda: TestIntrospector()
    yield auth_app, files_app
    auth_app.dependency_overrides.clear()
    files_app.dependency_overrides.clear()


async def test_http_full_contract_and_audit(clients):
    a, f = clients
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=a), base_url="http://auth") as auth,
        httpx.AsyncClient(transport=httpx.ASGITransport(app=f), base_url="http://files") as files,
    ):
        credentials = {"email": "person@example.com", "password": "safe-long-password-123"}
        assert (await auth.post("/authentication/register", json=credentials)).status_code == 200
        assert (await auth.post("/authentication/register", json=credentials)).status_code == 409
        login = await auth.post("/authentication/login", json=credentials)
        assert login.status_code == 200
        token = login.json()["token"]
        rid = str(uuid4())
        headers = {"Auth": token, "X-Request-ID": rid}
        introspection = await auth.get("/authentication/introspect", headers=headers)
        assert introspection.status_code == 200 and "password" not in introspection.text
        assert (await files.get("/files")).status_code == 422
        ids = []
        for index in range(3):
            response = await files.post(
                "/files", json={"filename": f"{index}.pdf"}, headers=headers
            )
            assert response.status_code == 200, response.text
            item = response.json()["file"]
            assert item["has_content"] is False
            ids.append(item["id"])
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            stream = BytesIO()
            writer.write(stream)
            response = await files.post(
                f"/files/{item['id']}",
                files={"file_content": ("x.pdf", stream.getvalue(), "application/pdf")},
                headers=headers,
            )
            assert response.status_code == 200, response.text
        response = await files.post("/files/merge", json={"file_ids": ids}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["source_file_ids"] == ids
        merged = response.json()["file"]["id"]
        assert (await files.get(f"/files/{merged}", headers=headers)).json()[
            "content_encoding"
        ] == "base64"
        assert (await files.get("/files", headers=headers)).json()["count"] == 4
        assert (await files.delete(f"/files/{merged}", headers=headers)).status_code == 200
        assert (await auth.post("/authentication/logout", headers=headers)).status_code == 200
        assert (await files.get("/files", headers=headers)).status_code == 401
        assert await AuditEvent.filter(event="invalid_session", outcome="rejected").exists()
        assert await AuditEvent.filter(event="files_merged", request_id=rid).exists()
        assert await AuditEvent.filter(event="validation_rejected").exists()


async def test_bad_credentials_and_auth_header(clients):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=clients[0]), base_url="http://auth"
    ) as client:
        response = await client.post(
            "/authentication/login",
            json={"email": "missing@example.com", "password": "wrong-long-password"},
        )
        assert response.status_code == 401
        assert (
            await client.get("/authentication/introspect?Auth=never-accept-in-url")
        ).status_code == 422
        assert (
            await client.get("/authentication/introspect", headers={"Auth": "x" * 40})
        ).status_code == 401


async def test_oversized_request_audited_before_parsing(clients):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=clients[1]), base_url="http://files"
    ) as client:
        response = await client.post(
            "/files/1", content=b"x", headers={"Content-Length": str(7 * 1024 * 1024)}
        )
        assert response.status_code == 413
        assert await AuditEvent.filter(event="request_too_large").exists()


def test_openapi_exposes_required_endpoints():
    assert set(auth_app.openapi()["paths"]) == {
        "/healthcheck",
        "/ready",
        "/authentication/register",
        "/authentication/login",
        "/authentication/logout",
        "/authentication/introspect",
    }
    assert set(files_app.openapi()["paths"]) == {
        "/healthcheck",
        "/ready",
        "/files",
        "/files/{id}",
        "/files/merge",
    }
    assert set(files_app.openapi()["paths"]["/files/{id}"]) == {"get", "post", "delete"}


async def test_chunked_oversized_request(clients):
    async def chunks():
        for _ in range(7):
            yield b"x" * (1024 * 1024)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=clients[1]), base_url="http://files"
    ) as client:
        response = await client.post(
            "/files/1",
            content=chunks(),
            headers={"Content-Type": "multipart/form-data; boundary=test"},
        )
        assert response.status_code == 413
        assert await AuditEvent.filter(event="request_too_large").exists()
