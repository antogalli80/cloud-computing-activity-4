"""S3-compatible object storage adapter for file content (Activity 4).

Why object storage for this data. File bytes are large, immutable once
written, and never queried or joined: storing them in PostgreSQL would bloat
every backup and every replica for no benefit. S3 is built exactly for that
shape, scales horizontally, and can hand the client a temporary signed URL so
a download never occupies an application worker.

Why this class is interchangeable with LocalContentStorage. Both satisfy the
same `ContentStorage` protocol, so swapping them is one line in the
dependency-injection container. The domain, the routers and the domain tests
are untouched by the choice — that is the whole point of the port.

MinIO is used locally because it speaks the S3 API; pointing `s3_endpoint_url`
at AWS instead is a configuration change, not a code change.
"""

import asyncio
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.domain import DomainError


class S3ContentStorage:
    def __init__(
        self,
        endpoint_url,
        region,
        bucket,
        access_key,
        secret_key,
        url_expiry_seconds,
    ):
        self.bucket = bucket
        self.url_expiry_seconds = url_expiry_seconds
        # One client reused for the whole process: boto3 keeps a connection
        # pool, so building a client per request would throw that away.
        # `s3v4` + `path` addressing are what MinIO expects; both are also
        # valid against AWS, so the same client works in either deployment.
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    async def ensure_bucket(self):
        """Create the bucket if it is not there yet. Idempotent, so it is safe
        to call on every start; it keeps a fresh environment from failing on
        the first upload."""

        def create():
            try:
                self._client.head_bucket(Bucket=self.bucket)
            except ClientError:
                try:
                    self._client.create_bucket(Bucket=self.bucket)
                except ClientError as exc:
                    # Another worker won the race: that is the desired state.
                    code = exc.response.get("Error", {}).get("Code", "")
                    if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                        raise

        await asyncio.to_thread(create)

    async def put(self, content):
        """Store bytes under a fresh opaque key and return it.

        The key is generated here and never derived from the filename: a
        user-supplied name must never reach the storage layer, and an opaque
        key also means re-uploading the same name cannot overwrite anything.
        """
        key = uuid4().hex

        def upload():
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType="application/octet-stream",
            )

        try:
            await asyncio.to_thread(upload)
        except (BotoCoreError, ClientError) as exc:
            raise DomainError("content_unavailable") from exc
        return key

    async def get(self, key):
        def download():
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            try:
                return response["Body"].read()
            finally:
                response["Body"].close()

        try:
            return await asyncio.to_thread(download)
        except (BotoCoreError, ClientError) as exc:
            raise DomainError("content_unavailable") from exc

    async def delete(self, key):
        """Remove the object. S3 treats deleting an absent key as success, so
        this is idempotent and matches the local adapter's behaviour."""

        def remove():
            self._client.delete_object(Bucket=self.bucket, Key=key)

        try:
            await asyncio.to_thread(remove)
        except (BotoCoreError, ClientError) as exc:
            raise DomainError("content_unavailable") from exc

    async def shareable_url(self, key, filename):
        """Return a time-limited signed URL for a direct download.

        This is the operational reason to choose S3: the client fetches the
        bytes straight from storage, so a large download does not tie up an
        API worker. The link expires on its own and carries no credentials of
        ours, and the Content-Disposition header restores the display name
        that the opaque key deliberately threw away.
        """

        def sign():
            return self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ResponseContentDisposition": f'attachment; filename="{filename}"',
                },
                ExpiresIn=self.url_expiry_seconds,
            )

        try:
            return await asyncio.to_thread(sign)
        except (BotoCoreError, ClientError):
            # A missing link must never break the response: the caller can
            # still download the content through the API.
            return None
