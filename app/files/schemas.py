import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UNSAFE_FILENAME_PATTERN = re.compile(r"[/\\\x00-\x1f\x7f]")


class FileMetadataRequest(BaseModel):
    """Metadata used to create a file before its binary content is uploaded."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255, examples=["invoice-2026.pdf"])
    description: str | None = Field(
        default=None,
        max_length=1000,
        examples=["September cloud activity evidence"],
    )

    @field_validator("filename", mode="before")
    @classmethod
    def validate_filename(cls, value: object) -> str:
        """Reject path components and control characters in display filenames."""

        if not isinstance(value, str):
            raise ValueError("Filename must be a string.")
        filename = value.strip()
        if not filename or filename in {".", ".."}:
            raise ValueError("Filename cannot be empty or relative.")
        if UNSAFE_FILENAME_PATTERN.search(filename):
            raise ValueError("Filename cannot contain paths or control characters.")
        return filename

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        """Normalize optional descriptions without inventing content."""

        if isinstance(value, str):
            description = value.strip()
            return description or None
        return value


class MergeFilesRequest(BaseModel):
    """Ordered list of 2-10 IDs; legacy two-ID requests remain accepted."""

    model_config = ConfigDict(extra="forbid")
    file_ids: list[int] | None = Field(default=None, min_length=2, max_length=10)
    file_id_1: int | None = Field(default=None, ge=1)
    file_id_2: int | None = Field(default=None, ge=1)

    def source_ids(self) -> list[int]:
        return self.file_ids if self.file_ids is not None else [self.file_id_1, self.file_id_2]

    @model_validator(mode="after")
    def validate_sources(self):
        if self.file_ids is not None:
            if self.file_id_1 is not None or self.file_id_2 is not None:
                raise ValueError("Use one input form only.")
        elif self.file_id_1 is None or self.file_id_2 is None:
            raise ValueError("Provide an ordered list or both legacy IDs.")
        ids = self.source_ids()
        if any(not isinstance(i, int) or isinstance(i, bool) or i < 1 for i in ids) or len(
            set(ids)
        ) != len(ids):
            raise ValueError("Use distinct positive IDs.")
        return self


class FileSummary(BaseModel):
    """Safe metadata returned without file content."""

    model_config = ConfigDict(extra="forbid")

    id: int
    owner_external_id: int
    filename: str
    description: str | None
    has_content: bool
    content_type: str | None
    size_bytes: int
    sha256: str | None
    created_at: datetime
    updated_at: datetime


class FileDetail(FileSummary):
    """File metadata and Base64 content when content has been uploaded."""

    content_encoding: Literal["base64"] | None
    content_base64: str | None
    download_url: str | None = None
    """Time-limited signed URL served straight from object storage.

    Present only when the storage backend can produce one (S3 can, a local
    volume cannot). Fetching the bytes through this link keeps large
    downloads off the API workers entirely.
    """


class FileListResponse(BaseModel):
    """All file metadata owned by the authenticated user."""

    status: Literal["success"] = "success"
    count: int
    files: list[FileSummary]


class FileCreatedResponse(BaseModel):
    """Metadata returned after reserving a new file identifier."""

    status: Literal["success"] = "success"
    file: FileSummary


class FileContentResponse(BaseModel):
    """Metadata returned after content is stored or replaced."""

    status: Literal["success"] = "success"
    message: Literal["File content stored."] = "File content stored."
    file: FileSummary


class FileDeletedResponse(BaseModel):
    """Confirmation that an owned file was removed."""

    status: Literal["success"] = "success"
    message: Literal["File deleted."] = "File deleted."
    file_id: int


class FileMergedResponse(BaseModel):
    """New file created by merging two owned PDF resources."""

    status: Literal["success"] = "success"
    source_file_ids: list[int]
    file: FileSummary
