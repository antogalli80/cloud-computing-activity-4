import asyncio
import hashlib
from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfReader, PdfWriter
from tortoise import connections

from app.authentication.models import SessionModel, UserModel
from app.core.audit import AuditEvent
from app.core.domain import Context, DomainError
from app.files.models import FileModel


def ctx():
    return Context(str(uuid4()))


def pdf(width=100):
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=100)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


async def owner(auth, email="one@example.com"):
    return await auth.register(email, "safe-long-password-for-testing", ctx())


async def test_register_and_password_secrecy(services):
    auth, _ = services
    user = await owner(auth)
    row = await UserModel.get(id=user.external_id)
    assert isinstance(user.external_id, int) and row.password_hash.startswith("scrypt$")
    assert "safe-long-password" not in row.password_hash
    assert await AuditEvent.filter(event="user_registered", actor_id=user.external_id).count() == 1


async def test_concurrent_registration(services):
    auth, _ = services
    result = await asyncio.gather(*(owner(auth) for _ in range(8)), return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in result) == 1
    assert all(
        isinstance(r, DomainError) and r.code == "user_already_exists"
        for r in result
        if isinstance(r, Exception)
    )
    assert await UserModel.all().count() == 1


async def test_concurrent_login_single_session(services):
    auth, _ = services
    await owner(auth)
    result = await asyncio.gather(
        *(auth.login("one@example.com", "safe-long-password-for-testing", ctx()) for _ in range(8)),
        return_exceptions=True,
    )
    assert sum(not isinstance(r, Exception) for r in result) == 1
    assert await SessionModel.all().count() == 1


async def test_session_lifecycle_and_digest(services):
    auth, _ = services
    await owner(auth)
    token, session = await auth.login("one@example.com", "safe-long-password-for-testing", ctx())
    row = await SessionModel.get(user_id=session.user_id)
    assert token != row.digest and row.digest == hashlib.sha256(token.encode()).hexdigest()
    _, actor, _ = await auth.introspect(token, ctx())
    assert actor.external_id == session.user_id
    await auth.logout(token, ctx())
    with pytest.raises(DomainError, match="invalid_session"):
        await auth.introspect(token, ctx())


@pytest.mark.parametrize("kind", ["idle", "absolute"])
async def test_expiry(services, kind):
    auth, _ = services
    await owner(auth)
    token, _ = await auth.login("one@example.com", "safe-long-password-for-testing", ctx())
    field = "last_seen_at" if kind == "idle" else "expires_at"
    await SessionModel.all().update(**{field: auth.clock.now() - timedelta(days=1)})
    with pytest.raises(DomainError, match="session_expired"):
        await auth.introspect(token, ctx())
    new_token, _ = await auth.login("one@example.com", "safe-long-password-for-testing", ctx())
    assert new_token != token


async def test_file_lifecycle_and_no_binary_columns(services):
    auth, files = services
    user = await owner(auth)
    item = await files.create(user.external_id, "a.pdf", None, ctx())
    assert item.content_key is None
    data = pdf()
    await files.upload(item.id, user.external_id, data, "application/pdf", ctx())
    record, actual, _ = await files.get(item.id, user.external_id, ctx())
    assert actual == data and record.sha256 == hashlib.sha256(data).hexdigest()
    assert len(await files.list_owned(user.external_id, ctx())) == 1
    columns = await connections.get("default").execute_query_dict(
        "SELECT data_type FROM information_schema.columns WHERE table_name='files'"
    )
    assert all(row["data_type"] != "bytea" for row in columns)
    await files.delete(item.id, user.external_id, ctx())
    assert await FileModel.all().count() == 0
    assert await AuditEvent.filter(event="file_deleted", resource_id=item.id).exists()


@pytest.mark.parametrize("operation", ["get", "upload", "delete", "merge"])
async def test_owner_isolation(services, operation):
    auth, files = services
    one, two = await owner(auth), await owner(auth, "two@example.com")
    first = await files.create(one.external_id, "a.pdf", None, ctx())
    second = await files.create(one.external_id, "b.pdf", None, ctx())
    with pytest.raises(DomainError, match="file_not_found"):
        if operation == "get":
            await files.get(first.id, two.external_id, ctx())
        if operation == "upload":
            await files.upload(first.id, two.external_id, b"x", "text/plain", ctx())
        if operation == "delete":
            await files.delete(first.id, two.external_id, ctx())
        if operation == "merge":
            await files.merge([first.id, second.id], two.external_id, ctx())
    assert await files.list_owned(two.external_id, ctx()) == []


async def test_merge_three_preserves_order(services):
    auth, files = services
    user = await owner(auth)
    ids = []
    for width in [100, 200, 300]:
        item = await files.create(user.external_id, "a.pdf", None, ctx())
        await files.upload(item.id, user.external_id, pdf(width), "application/pdf", ctx())
        ids.append(item.id)
    merged = await files.merge(list(reversed(ids)), user.external_id, ctx())
    _, data, _ = await files.get(merged.id, user.external_id, ctx())
    assert [int(p.mediabox.width) for p in PdfReader(BytesIO(data)).pages] == [300, 200, 100]


async def test_invalid_merge_rolls_back(services):
    auth, files = services
    user = await owner(auth)
    ids = []
    for content in [pdf(), b"not a pdf"]:
        item = await files.create(user.external_id, "file", None, ctx())
        await files.upload(item.id, user.external_id, content, "application/pdf", ctx())
        ids.append(item.id)
    with pytest.raises(DomainError, match="invalid_pdf"):
        await files.merge(ids, user.external_id, ctx())
    assert await FileModel.all().count() == 2
    assert await AuditEvent.filter(event="files_merged").count() == 0


async def test_audit_failure_rolls_back_business_change(services):
    auth, files = services
    user = await owner(auth)

    class BrokenAudit:
        async def record(self, *a, **kw):
            raise RuntimeError("simulated audit outage")

    files.audit = BrokenAudit()
    with pytest.raises(RuntimeError):
        await files.create(user.external_id, "never-committed", None, ctx())
    assert await FileModel.all().count() == 0


async def test_content_tampering_detected(services):
    auth, files = services
    user = await owner(auth)
    item = await files.create(user.external_id, "file", None, ctx())
    item = await files.upload(item.id, user.external_id, b"original", "text/plain", ctx())
    (files.content.root / item.content_key).write_bytes(b"tampered")
    with pytest.raises(DomainError, match="content_integrity_failure"):
        await files.get(item.id, user.external_id, ctx())


async def test_audit_is_append_only_and_runtime_least_privilege(services):
    auth, _ = services
    await owner(auth)
    db = connections.get("default")
    for statement in [
        "UPDATE audit_events SET outcome='hidden'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ]:
        with pytest.raises(Exception):
            await db.execute_query(statement)
    await db.execute_query("SET ROLE cloud_app")
    try:
        for statement in [
            "SELECT * FROM audit_events",
            "CREATE TABLE forbidden(id int)",
            "TRUNCATE files",
        ]:
            with pytest.raises(Exception):
                await db.execute_query(statement)
    finally:
        await db.execute_query("RESET ROLE")


async def test_constraints_reject_orphans(services):
    with pytest.raises(Exception):
        await FileModel.create(owner_id=999999, filename="orphan")


async def test_migrations_are_idempotent(db):
    from aerich import Command

    from app.database import TORTOISE_ORM

    command = Command(tortoise_config=TORTOISE_ORM, app="models", location="./migrations")
    await command.init()
    assert await command.upgrade(run_in_transaction=True) == []
