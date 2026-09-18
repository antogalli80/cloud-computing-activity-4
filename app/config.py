from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    name: str = "Cloud Computing Activity 4 API"
    version: str = "1.0.0"
    environment: Environment = "development"
    log_level: LogLevel = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    auth_service_url: str = "http://localhost:8001"
    auth_service_timeout_seconds: float = Field(default=3.0, ge=0.1, le=30.0)
    auth_session_idle_seconds: int = Field(default=900, ge=60, le=86400)
    auth_session_absolute_seconds: int = Field(default=28800, ge=300, le=604800)
    database_url: str = "postgres://cloud_app:local-only@postgres:5432/cloud3"
    content_root: str = "/data/content"

    # ── Redis: session storage (Activity 4) ────────────────────────────────
    # The session TTL is delegated to Redis itself, so idle expiry stops being
    # application logic and becomes a storage guarantee shared by every worker.
    redis_url: str = "redis://redis:6379/0"

    # ── S3-compatible object storage: file content (Activity 4) ────────────
    # MinIO locally, AWS S3 in a real deployment: the adapter is identical
    # because both speak the same API. Credentials never have a default.
    s3_endpoint_url: str = "http://minio:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "activity4-content"
    s3_access_key: str
    s3_secret_key: str
    s3_url_expiry_seconds: int = Field(default=900, ge=60, le=604800)

    files_max_upload_bytes: int = Field(default=5_242_880, ge=1024, le=52_428_800)
    files_max_merged_bytes: int = Field(default=10_485_760, ge=2048, le=104_857_600)
    files_max_pdf_pages: int = Field(default=200, ge=2, le=2000)


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
