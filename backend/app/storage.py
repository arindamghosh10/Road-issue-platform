"""Object storage for photos (S3-compatible: MinIO locally, Cloudflare R2 when hosted).

Two buckets, on purpose:
* original bucket — the raw upload, exactly as the phone sent it (may contain EXIF,
  faces, number plates). Private. Only the verification worker reads it.
* public bucket   — the sanitized copy (EXIF stripped, faces/plates blurred). This is
  the only version government users and the public ever see.
"""

from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class ObjectStore(Protocol):
    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, bucket: str, key: str) -> bytes: ...


class S3Store:
    def __init__(self) -> None:
        import boto3  # imported lazily so unit tests don't need AWS config

        s = get_settings()
        self._client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            region_name="auto",
        )

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, bucket: str, key: str) -> bytes:
        return self._client.get_object(Bucket=bucket, Key=key)["Body"].read()


class LocalStore:
    """Plain folders on disk (<root>/<bucket>/<key>). For running without MinIO/Docker."""

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def _path(self, bucket: str, key: str) -> Path:
        path = (self._root / bucket / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise ValueError("invalid object key")
        return path

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        path = self._path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, bucket: str, key: str) -> bytes:
        return self._path(bucket, key).read_bytes()


class MemoryStore:
    """In-process store for tests."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.objects[(bucket, key)] = data

    def get(self, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]


@lru_cache
def get_store() -> ObjectStore:
    backend = get_settings().storage_backend
    if backend == "memory":
        return MemoryStore()
    if backend == "s3":
        return S3Store()
    if backend == "local":
        return LocalStore(get_settings().local_storage_dir)
    raise ValueError(f"unknown STORAGE_BACKEND {backend!r}")


def public_url(key: str) -> str:
    return f"{get_settings().s3_public_base_url.rstrip('/')}/{key}"
