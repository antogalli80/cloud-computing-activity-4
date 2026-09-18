import hashlib

from app.core.domain import AuditSink, Context, DomainError, UnitOfWork
from app.files.domain.ports import ContentStorage, FileRepository, PdfMerger


class FilesService:
    def __init__(
        self,
        repository: FileRepository,
        content: ContentStorage,
        merger: PdfMerger,
        audit: AuditSink,
        uow: UnitOfWork,
        max_upload: int,
    ):
        self.repository, self.content, self.merger = repository, content, merger
        self.audit, self.uow, self.max_upload = audit, uow, max_upload

    async def create(self, owner, filename, description, ctx: Context):
        async with self.uow.transaction():
            file = await self.repository.create(owner, filename, description)
            await self.audit.record("file_created", ctx, actor_id=owner, resource_id=file.id)
        return file

    async def list_owned(self, owner, ctx: Context):
        async with self.uow.transaction():
            files = await self.repository.list_owned(owner)
            await self.audit.record("files_listed", ctx, actor_id=owner)
        return files

    async def get(self, file_id, owner, ctx: Context):
        async with self.uow.transaction():
            file = await self.repository.get_owned(file_id, owner)
            content = await self.content.get(file.content_key) if file.content_key else None
            if content is not None and hashlib.sha256(content).hexdigest() != file.sha256:
                raise DomainError("content_integrity_failure")
            await self.audit.record("file_retrieved", ctx, actor_id=owner, resource_id=file.id)

        # Signed direct-download link, when the backend can produce one. It is
        # built outside the transaction because signing is a local operation
        # that must not hold a database connection open.
        url = (
            await self.content.shareable_url(file.content_key, file.filename)
            if file.content_key
            else None
        )
        return file, content, url

    async def upload(self, file_id, owner, content, content_type, ctx: Context):
        if len(content) > self.max_upload:
            raise DomainError("upload_too_large")
        async with self.uow.transaction():
            await self.repository.get_owned(file_id, owner, lock=True)
            key = await self.content.put(content)
            file = await self.repository.set_content(
                file_id, owner, key, content_type, len(content), hashlib.sha256(content).hexdigest()
            )
            await self.audit.record("file_content_stored", ctx, actor_id=owner, resource_id=file.id)
        return file

    async def delete(self, file_id, owner, ctx: Context):
        async with self.uow.transaction():
            file = await self.repository.get_owned(file_id, owner, lock=True)
            await self.repository.delete(file_id, owner)
            await self.audit.record("file_deleted", ctx, actor_id=owner, resource_id=file_id)

        # The object is removed AFTER the metadata transaction commits, and on
        # purpose in that order. Object storage cannot join the database
        # transaction, so one of the two failure modes has to be chosen:
        #   - blob first: a rollback would leave metadata pointing at nothing,
        #     and the file would be permanently unreadable.
        #   - metadata first: a failure here leaves an unreferenced object,
        #     which costs storage and nothing else.
        # The second is strictly recoverable, so it is the one we take.
        if file.content_key:
            await self.content.delete(file.content_key)

    async def merge(self, ids, owner, ctx: Context):
        if len(ids) < 2 or len(ids) > 10 or len(set(ids)) != len(ids):
            raise DomainError("invalid_merge_sources")
        async with self.uow.transaction():
            # Consistent lock order prevents deadlocks; caller order controls PDF order.
            sources = {i: await self.repository.get_owned(i, owner, lock=True) for i in sorted(ids)}
            contents = []
            for i in ids:
                source = sources[i]
                if not source.content_key:
                    raise DomainError("file_content_missing")
                data = await self.content.get(source.content_key)
                if hashlib.sha256(data).hexdigest() != source.sha256:
                    raise DomainError("content_integrity_failure")
                contents.append(data)
            merged = await self.merger.merge(contents)
            key = await self.content.put(merged)
            file = await self.repository.create(owner, "merged.pdf", "Merged owned PDF documents")
            file = await self.repository.set_content(
                file.id,
                owner,
                key,
                "application/pdf",
                len(merged),
                hashlib.sha256(merged).hexdigest(),
            )
            await self.audit.record("files_merged", ctx, actor_id=owner, resource_id=file.id)
        return file
