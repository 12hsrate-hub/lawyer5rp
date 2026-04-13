from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True)
class ObjectMetadata:
    storage_key: str
    size_bytes: int
    mime_type: str
    checksum: str


class LocalObjectStorageClient:
    def __init__(self, root_dir: str | Path | None = None):
        root_path = Path(root_dir or os.getenv("OGP_OBJECT_STORAGE_ROOT") or "web/data/object_storage")
        self.root_dir = root_path
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        safe = str(storage_key).strip().lstrip("/")
        return self.root_dir / safe

    def stat_object(self, storage_key: str) -> ObjectMetadata | None:
        path = self._path(storage_key)
        if not path.exists() or not path.is_file():
            return None
        data = path.read_bytes()
        return ObjectMetadata(
            storage_key=storage_key,
            size_bytes=len(data),
            mime_type="application/octet-stream",
            checksum=hashlib.sha256(data).hexdigest(),
        )

    def put_object_bytes(self, storage_key: str, payload: bytes) -> ObjectMetadata:
        path = self._path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return ObjectMetadata(
            storage_key=storage_key,
            size_bytes=len(payload),
            mime_type="application/octet-stream",
            checksum=hashlib.sha256(payload).hexdigest(),
        )

    def delete_object(self, storage_key: str) -> None:
        path = self._path(storage_key)
        if path.exists() and path.is_file():
            path.unlink()


class ObjectStorageService:
    def __init__(self, client: LocalObjectStorageClient | None = None):
        self.client = client or LocalObjectStorageClient()
        secret = os.getenv("OGP_OBJECT_STORAGE_SECRET") or os.getenv("OGP_WEB_SECRET") or "dev-object-storage-secret"
        self._secret = secret.encode("utf-8")
        self._base_url = (os.getenv("OGP_OBJECT_STORAGE_PUBLIC_BASE_URL") or "https://storage.local").rstrip("/")

    def build_storage_key(self, *, server_id: str, entity_type: str, entity_id: int, filename: str) -> str:
        safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in filename.strip())
        safe_name = safe_name or "file.bin"
        return f"{server_id}/{entity_type}/{entity_id}/{int(time.time())}_{safe_name}"

    def _sign_payload(self, payload: dict[str, object]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hmac.new(self._secret, raw, hashlib.sha256).hexdigest()

    def _make_presigned_url(self, *, action: str, storage_key: str, ttl_seconds: int, constraints: dict[str, object]) -> dict[str, object]:
        expires_at = int(time.time()) + max(60, int(ttl_seconds))
        payload: dict[str, object] = {
            "action": action,
            "key": storage_key,
            "exp": expires_at,
            "constraints": constraints,
        }
        signature = self._sign_payload(payload)
        url = (
            f"{self._base_url}/{action}/{quote(storage_key)}"
            f"?exp={expires_at}&sig={signature}"
        )
        return {"url": url, "expires_at": expires_at, "constraints": constraints}

    def generate_presigned_upload_url(
        self,
        *,
        storage_key: str,
        ttl_seconds: int,
        content_type: str,
        size_bytes: int,
    ) -> dict[str, object]:
        constraints = {
            "content_type": str(content_type or "application/octet-stream"),
            "max_size_bytes": int(size_bytes),
        }
        return self._make_presigned_url(action="upload", storage_key=storage_key, ttl_seconds=ttl_seconds, constraints=constraints)

    def generate_presigned_download_url(self, *, storage_key: str, ttl_seconds: int) -> dict[str, object]:
        return self._make_presigned_url(action="download", storage_key=storage_key, ttl_seconds=ttl_seconds, constraints={})

    def read_object_metadata(self, *, storage_key: str) -> ObjectMetadata | None:
        return self.client.stat_object(storage_key)

    def finalize_upload(self, *, storage_key: str, expected_max_size: int | None = None) -> ObjectMetadata:
        metadata = self.read_object_metadata(storage_key=storage_key)
        if metadata is None:
            raise ValueError("Uploaded object not found in storage.")
        if expected_max_size is not None and metadata.size_bytes > int(expected_max_size):
            raise ValueError("Uploaded object exceeds allowed size.")
        return metadata

    def store_bytes(self, *, storage_key: str, payload: bytes) -> ObjectMetadata:
        return self.client.put_object_bytes(storage_key, payload)

    def delete_object(self, *, storage_key: str) -> None:
        self.client.delete_object(storage_key)
