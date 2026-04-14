from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredObjectMetadata:
    key: str
    size_bytes: int
    content_type: str
    checksum: str


class ObjectStoreProvider(Protocol):
    def stat(self, *, key: str) -> StoredObjectMetadata | None: ...

    def put_bytes(self, *, key: str, payload: bytes, content_type: str = "application/octet-stream") -> StoredObjectMetadata: ...

    def delete(self, *, key: str) -> None: ...


class LocalObjectStoreProvider:
    """Dev-only local filesystem adapter."""

    def __init__(self, *, root_dir: str | Path | None = None):
        root_path = Path(root_dir or os.getenv("OGP_OBJECT_STORAGE_ROOT") or "web/data/object_storage")
        self.root_dir = root_path
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root_dir / str(key).strip().lstrip("/")

    def stat(self, *, key: str) -> StoredObjectMetadata | None:
        path = self._path(key)
        if not path.exists() or not path.is_file():
            return None
        payload = path.read_bytes()
        return StoredObjectMetadata(
            key=key,
            size_bytes=len(payload),
            content_type="application/octet-stream",
            checksum=hashlib.sha256(payload).hexdigest(),
        )

    def put_bytes(self, *, key: str, payload: bytes, content_type: str = "application/octet-stream") -> StoredObjectMetadata:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return StoredObjectMetadata(
            key=key,
            size_bytes=len(payload),
            content_type=content_type,
            checksum=hashlib.sha256(payload).hexdigest(),
        )

    def delete(self, *, key: str) -> None:
        path = self._path(key)
        if path.exists() and path.is_file():
            path.unlink()


class S3ObjectStoreProvider:
    def __init__(self, *, bucket: str, endpoint_url: str | None = None, region: str | None = None):
        try:
            import boto3
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("boto3 package is required for S3ObjectStoreProvider") from exc
        self.bucket = bucket
        self._client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)

    def stat(self, *, key: str) -> StoredObjectMetadata | None:
        try:
            response = self._client.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return None
        return StoredObjectMetadata(
            key=key,
            size_bytes=int(response.get("ContentLength") or 0),
            content_type=str(response.get("ContentType") or "application/octet-stream"),
            checksum=str(response.get("ETag") or "").replace('"', ""),
        )

    def put_bytes(self, *, key: str, payload: bytes, content_type: str = "application/octet-stream") -> StoredObjectMetadata:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=payload, ContentType=content_type)
        stat = self.stat(key=key)
        if stat is None:
            raise RuntimeError("S3 write succeeded but object head lookup failed")
        return stat

    def delete(self, *, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)


def build_object_store_provider_from_env() -> ObjectStoreProvider:
    provider = (os.getenv("OGP_OBJECT_STORE_PROVIDER") or "local").strip().lower()
    if provider == "s3":
        bucket = (os.getenv("OGP_S3_BUCKET") or "").strip()
        if not bucket:
            raise RuntimeError("OGP_S3_BUCKET is required when OGP_OBJECT_STORE_PROVIDER=s3")
        return S3ObjectStoreProvider(
            bucket=bucket,
            endpoint_url=(os.getenv("OGP_S3_ENDPOINT_URL") or "").strip() or None,
            region=(os.getenv("OGP_S3_REGION") or "").strip() or None,
        )
    return LocalObjectStoreProvider()
