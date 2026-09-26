"""S3-compatible object storage (AWS S3, Cloudflare R2, MinIO).

STATUS: written, never run — there were no credentials and no reachable bucket
in the environment this was written in, so treat it as a first draft rather than
a working backend until one request has gone through it.

Unlike the PP-StructureV3 stub, this one *is* written out: boto3's client API is
stable and the call shapes are unambiguous, so there is nothing here that a
version bump quietly changes underneath you. What has not been checked is the
configuration around it — endpoint URL form for R2, region handling, and whether
the bucket exists.

To use it: ``pip install boto3`` and set STORAGE_BACKEND=s3 plus the S3_* values
in .env. Cloudflare R2 wants S3_ENDPOINT_URL set to
``https://<account>.r2.cloudflarestorage.com`` and S3_REGION=auto.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.services.storage.base import ObjectNotFound, StorageBackend, StorageError


class S3Storage(StorageBackend):
    name = "s3"

    def __init__(self) -> None:
        self._client = None
        settings = get_settings()
        if not settings.s3_bucket:
            raise StorageError("STORAGE_BACKEND=s3 needs S3_BUCKET set")
        self._bucket = settings.s3_bucket

    def _get_client(self):
        if self._client is None:
            settings = get_settings()
            try:
                import boto3  # noqa: PLC0415
            except ImportError as exc:
                raise StorageError("boto3 is not installed. Run: pip install boto3") from exc

            self._client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url or None,
                region_name=settings.s3_region or None,
                aws_access_key_id=settings.s3_access_key_id or None,
                aws_secret_access_key=settings.s3_secret_access_key or None,
            )
        return self._client

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        client = self._get_client()
        await run_in_threadpool(
            client.put_object, Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )

    async def get(self, key: str) -> bytes:
        client = self._get_client()
        try:
            response = await run_in_threadpool(client.get_object, Bucket=self._bucket, Key=key)
        except Exception as exc:  # botocore raises ClientError for a missing key
            if "NoSuchKey" in str(exc) or "404" in str(exc):
                raise ObjectNotFound(key) from exc
            raise StorageError(f"S3 get failed for {key!r}: {exc}") from exc
        return await run_in_threadpool(response["Body"].read)

    async def delete(self, key: str) -> None:
        client = self._get_client()
        await run_in_threadpool(client.delete_object, Bucket=self._bucket, Key=key)
