import base64
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Request, UploadFile

from app.core.domain import Context, DomainError
from app.files.dependency_injection.container import get_introspector, get_service
from app.files.schemas import (
    FileContentResponse,
    FileCreatedResponse,
    FileDeletedResponse,
    FileDetail,
    FileListResponse,
    FileMergedResponse,
    FileMetadataRequest,
    FileSummary,
    MergeFilesRequest,
)

router = APIRouter(prefix="/files", tags=["Files"])
Service = Annotated[object, Depends(get_service)]
Auth = Annotated[str, Header(alias="Auth", min_length=32, max_length=256)]


async def current_user(auth: Auth, request: Request, introspector=Depends(get_introspector)):
    actor = await introspector.introspect(auth, request.state.request_id)
    request.state.actor_id = actor.external_id
    return actor


CurrentUser = Annotated[object, Depends(current_user)]


def summary(file):
    return FileSummary(
        id=file.id,
        owner_external_id=file.owner_external_id,
        filename=file.filename,
        description=file.description,
        has_content=file.content_key is not None,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
        created_at=file.created_at,
        updated_at=file.updated_at,
    )


@router.get("", response_model=FileListResponse, operation_id="files_list")
async def list_files(user: CurrentUser, request: Request, service: Service):
    files = await service.list_owned(user.external_id, Context(request.state.request_id))
    return FileListResponse(count=len(files), files=[summary(f) for f in files])


@router.post("", response_model=FileCreatedResponse, operation_id="files_create")
async def create_file(
    payload: FileMetadataRequest, user: CurrentUser, request: Request, service: Service
):
    file = await service.create(
        user.external_id, payload.filename, payload.description, Context(request.state.request_id)
    )
    return FileCreatedResponse(file=summary(file))


@router.post("/merge", response_model=FileMergedResponse, operation_id="files_merge")
async def merge(payload: MergeFilesRequest, user: CurrentUser, request: Request, service: Service):
    ids = payload.source_ids()
    file = await service.merge(ids, user.external_id, Context(request.state.request_id))
    return FileMergedResponse(source_file_ids=ids, file=summary(file))


@router.get("/{id}", response_model=FileDetail, operation_id="files_get")
async def get_file(id: int, user: CurrentUser, request: Request, service: Service):
    file, content, url = await service.get(id, user.external_id, Context(request.state.request_id))
    return FileDetail(
        **summary(file).model_dump(),
        content_encoding="base64" if content is not None else None,
        content_base64=base64.b64encode(content).decode() if content is not None else None,
        download_url=url,
    )


@router.post("/{id}", response_model=FileContentResponse, operation_id="files_update")
async def upload(
    id: int,
    user: CurrentUser,
    request: Request,
    service: Service,
    file_content: Annotated[UploadFile, File()],
):
    data = bytearray()
    try:
        while chunk := await file_content.read(65536):
            data.extend(chunk)
            if len(data) > service.max_upload:
                raise DomainError("upload_too_large")
        file = await service.upload(
            id,
            user.external_id,
            bytes(data),
            (file_content.content_type or "application/octet-stream")[:255],
            Context(request.state.request_id),
        )
    finally:
        await file_content.close()
    return FileContentResponse(file=summary(file))


@router.delete("/{id}", response_model=FileDeletedResponse, operation_id="files_delete")
async def delete(id: int, user: CurrentUser, request: Request, service: Service):
    await service.delete(id, user.external_id, Context(request.state.request_id))
    return FileDeletedResponse(file_id=id)
