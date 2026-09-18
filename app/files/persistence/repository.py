from app.core.domain import DomainError
from app.files.domain.ports import File
from app.files.models import FileModel


def file_bo(row):
    return File(
        row.id,
        row.owner_id,
        row.filename,
        row.description,
        row.content_key,
        row.content_type,
        row.size_bytes,
        row.sha256,
        row.created_at,
        row.updated_at,
    )


class PostgresFiles:
    async def create(self, owner, filename, description):
        return file_bo(
            await FileModel.create(owner_id=owner, filename=filename, description=description)
        )

    async def list_owned(self, owner):
        return [file_bo(row) for row in await FileModel.filter(owner_id=owner).order_by("id")]

    async def get_owned(self, file_id, owner, *, lock=False):
        query = FileModel.filter(id=file_id, owner_id=owner)
        if lock:
            query = query.select_for_update()
        row = await query.first()
        if row is None:
            raise DomainError("file_not_found")
        return file_bo(row)

    async def set_content(self, file_id, owner, key, content_type, size, sha256):
        row = await FileModel.get(id=file_id, owner_id=owner)
        row.content_key, row.content_type, row.size_bytes, row.sha256 = (
            key,
            content_type,
            size,
            sha256,
        )
        await row.save()
        return file_bo(row)

    async def delete(self, file_id, owner):
        await FileModel.filter(id=file_id, owner_id=owner).delete()
