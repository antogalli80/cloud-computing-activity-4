"""Composition root for the Files app.

Same idea as the Authentication container: this is the only place that names
concrete adapters. `get_content_storage()` is where the object-storage
decision lives — swapping S3 for the local volume is one line, and neither
the domain service nor the routers nor the domain tests notice.
"""

from functools import lru_cache

from app.config import get_settings
from app.core.audit import DatabaseAudit
from app.core.infrastructure import PostgresUnitOfWork
from app.files.domain.service import FilesService
from app.files.persistence.introspection import HttpTokenIntrospector
from app.files.persistence.pdf import PypdfMerger
from app.files.persistence.repository import PostgresFiles
from app.files.persistence.s3 import S3ContentStorage


@lru_cache
def get_content_storage():
    """The object store. Swap this for `LocalContentStorage(settings.content_root)`
    and everything keeps working.

    S3 is the right home for file content: the blobs are large, immutable,
    never joined or queried, and keeping them out of PostgreSQL keeps backups
    and replicas small. It also lets us hand the client a signed URL so a
    download never occupies an API worker.
    """
    settings = get_settings()
    return S3ContentStorage(
        settings.s3_endpoint_url,
        settings.s3_region,
        settings.s3_bucket,
        settings.s3_access_key,
        settings.s3_secret_key,
        settings.s3_url_expiry_seconds,
    )


@lru_cache
def get_service():
    settings = get_settings()
    return FilesService(
        PostgresFiles(),
        get_content_storage(),
        PypdfMerger(settings.files_max_pdf_pages, settings.files_max_merged_bytes),
        DatabaseAudit("files"),
        PostgresUnitOfWork(),
        settings.files_max_upload_bytes,
    )


@lru_cache
def get_introspector():
    settings = get_settings()
    return HttpTokenIntrospector(
        settings.auth_service_url.rstrip("/"), settings.auth_service_timeout_seconds
    )
