from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_DB_BACKEND", "postgres")

from ogp_web.services.attachment_service import AttachmentService
from ogp_web.services.export_service import ExportGateResult, ExportService
from ogp_web.services.object_storage_service import ObjectMetadata


@dataclass
class _DocVersion:
    id: int
    document_id: int
    version_number: int
    server_id: str
    content_json: dict


class FakeStorageService:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def build_storage_key(self, *, server_id: str, entity_type: str, entity_id: int, filename: str) -> str:
        return f"{server_id}/{entity_type}/{entity_id}/{filename}"

    def generate_presigned_upload_url(self, *, storage_key: str, ttl_seconds: int, content_type: str, size_bytes: int):
        return {
            "url": f"https://storage.local/upload/{storage_key}",
            "expires_at": 123,
            "constraints": {"content_type": content_type, "max_size_bytes": size_bytes, "ttl_seconds": ttl_seconds},
        }

    def generate_presigned_download_url(self, *, storage_key: str, ttl_seconds: int):
        return {"url": f"https://storage.local/download/{storage_key}", "expires_at": 456, "constraints": {"ttl_seconds": ttl_seconds}}

    def finalize_upload(self, *, storage_key: str, expected_max_size: int | None = None):
        if storage_key not in self.objects:
            raise ValueError("missing")
        payload = self.objects[storage_key]
        if expected_max_size is not None and len(payload) > expected_max_size:
            raise ValueError("too big")
        return ObjectMetadata(storage_key=storage_key, size_bytes=len(payload), mime_type="application/pdf", checksum="abc")

    def store_bytes(self, *, storage_key: str, payload: bytes):
        self.objects[storage_key] = payload
        return ObjectMetadata(storage_key=storage_key, size_bytes=len(payload), mime_type="application/json", checksum="sum")


class FakeRepo:
    def __init__(self):
        self.users = {"alice": 10}
        self.document_versions = {
            1: _DocVersion(id=1, document_id=100, version_number=1, server_id="blackberry", content_json={"a": 1}),
            2: _DocVersion(id=2, document_id=100, version_number=2, server_id="blackberry", content_json={"a": 2}),
            3: _DocVersion(id=3, document_id=200, version_number=1, server_id="strawberry", content_json={"x": 1}),
        }
        self.attachments = {}
        self.links = []
        self.exports = {}
        self._next_attachment_id = 1
        self._next_export_id = 1
        self.export_status_history: list[str] = []

    def get_user_id_by_username(self, username: str):
        return self.users.get(username)

    def get_document_version(self, *, version_id: int):
        item = self.document_versions.get(version_id)
        if not item:
            return None
        return {
            "id": item.id,
            "document_id": item.document_id,
            "version_number": item.version_number,
            "server_id": item.server_id,
            "case_id": 1,
            "content_json": json.dumps(item.content_json),
        }

    def create_attachment(self, **kwargs):
        attachment_id = self._next_attachment_id
        self._next_attachment_id += 1
        payload = {"id": attachment_id, **kwargs, "metadata_json": json.dumps(kwargs["metadata_json"]), "created_at": "t"}
        self.attachments[attachment_id] = payload
        return payload

    def create_document_version_attachment_link(self, **kwargs):
        self.links.append(kwargs)
        return {"id": len(self.links), **kwargs, "created_at": "t"}

    def get_attachment_with_version(self, *, attachment_id: int):
        att = self.attachments.get(attachment_id)
        if not att:
            return None
        link = next(link for link in self.links if link["attachment_id"] == attachment_id)
        version = self.document_versions[link["document_version_id"]]
        return {**att, "document_version_id": version.id, "document_server_id": version.server_id}

    def update_attachment_upload_status(self, *, attachment_id: int, **kwargs):
        self.attachments[attachment_id].update(kwargs)
        self.attachments[attachment_id]["metadata_json"] = json.dumps(kwargs["metadata_json"])
        return self.attachments[attachment_id]

    def list_attachments_for_document_version(self, *, document_version_id: int):
        ids = [link["attachment_id"] for link in self.links if link["document_version_id"] == document_version_id]
        return [self.attachments[idx] for idx in ids]

    def delete_attachment_link(self, *, document_version_id: int, attachment_id: int):
        before = len(self.links)
        self.links = [x for x in self.links if not (x["document_version_id"] == document_version_id and x["attachment_id"] == attachment_id)]
        return 1 if len(self.links) < before else 0

    def create_export(self, **kwargs):
        export_id = self._next_export_id
        self._next_export_id += 1
        payload = {
            "id": export_id,
            **kwargs,
            "metadata_json": json.dumps(kwargs["metadata_json"]),
            "created_at": "t",
            "updated_at": "t",
        }
        self.exports[export_id] = payload
        self.export_status_history.append(kwargs["status"])
        return payload

    def update_export(self, *, export_id: int, **kwargs):
        self.exports[export_id].update(kwargs)
        self.exports[export_id]["metadata_json"] = json.dumps(kwargs["metadata_json"])
        self.export_status_history.append(kwargs["status"])
        return self.exports[export_id]

    def list_exports_for_document_version(self, *, document_version_id: int):
        return [x for x in self.exports.values() if x["document_version_id"] == document_version_id]

    def get_export(self, *, export_id: int):
        item = self.exports.get(export_id)
        if not item:
            return None
        version = self.document_versions[item["document_version_id"]]
        return {**item, "document_server_id": version.server_id}


class GateWarn:
    def evaluate(self, *, document_version_id: int):
        return ExportGateResult(mode="warn", reason="ok")


class GateHardBlock:
    def evaluate(self, *, document_version_id: int):
        return ExportGateResult(mode="hard_block", reason="blocked")


class InlineAsyncJobService:
    def __init__(self):
        self._seq = 1

    def create_job(self, **kwargs):
        job = {"id": self._seq, **kwargs}
        self._seq += 1
        return job


def test_attachment_linked_to_document_version_and_finalized():
    repo = FakeRepo()
    storage = FakeStorageService()
    service = AttachmentService(repository=repo, storage_service=storage)

    result = service.create_upload_url(
        username="alice",
        user_server_id="blackberry",
        document_version_id=1,
        filename="evidence.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        link_type="evidence",
        ttl_seconds=300,
    )
    attachment_id = result["attachment"]["id"]
    assert repo.links[0]["document_version_id"] == 1

    storage.objects[result["attachment"]["storage_key"]] = b"12345"
    finalized = service.finalize_upload(username="alice", user_server_id="blackberry", attachment_id=attachment_id)
    assert finalized["upload_status"] == "uploaded"
    assert finalized["size_bytes"] == 5


def test_cross_server_attachment_rejected():
    repo = FakeRepo()
    service = AttachmentService(repository=repo, storage_service=FakeStorageService())
    with pytest.raises(HTTPException) as exc:
        service.create_upload_url(
            username="alice",
            user_server_id="blackberry",
            document_version_id=3,
            filename="x.txt",
            mime_type="text/plain",
            size_bytes=1,
            link_type="supporting",
            ttl_seconds=300,
        )
    assert exc.value.status_code == 403


def test_export_sync_creates_versioned_artifact_new_version_new_export():
    repo = FakeRepo()
    storage = FakeStorageService()
    service = ExportService(
        repository=repo,
        storage_service=storage,
        validation_gate_provider=GateWarn(),
        async_job_service=InlineAsyncJobService(),
    )
    first = service.create_export(
        username="alice",
        user_server_id="blackberry",
        document_version_id=1,
        export_format="json",
        execution_mode="sync",
    )
    second = service.create_export(
        username="alice",
        user_server_id="blackberry",
        document_version_id=2,
        export_format="json",
        execution_mode="sync",
    )
    assert first["document_version_id"] == 1
    assert second["document_version_id"] == 2
    assert first["id"] != second["id"]


def test_export_async_lifecycle_and_download_ready_only():
    repo = FakeRepo()
    service = ExportService(
        repository=repo,
        storage_service=FakeStorageService(),
        validation_gate_provider=GateWarn(),
        async_job_service=InlineAsyncJobService(),
    )
    created = service.create_export(
        username="alice",
        user_server_id="blackberry",
        document_version_id=1,
        export_format="json",
        execution_mode="async",
    )
    assert created["status"] == "pending"
    assert "pending" in set(repo.export_status_history)


def test_export_gate_modes_enforced():
    repo = FakeRepo()
    base_kwargs = dict(
        repository=repo,
        storage_service=FakeStorageService(),
        async_job_service=InlineAsyncJobService(),
    )
    warn_service = ExportService(validation_gate_provider=GateWarn(), **base_kwargs)
    allowed = warn_service.create_export(
        username="alice",
        user_server_id="blackberry",
        document_version_id=1,
        export_format="json",
        execution_mode="sync",
    )
    assert allowed["status"] == "ready"

    hard_block_service = ExportService(validation_gate_provider=GateHardBlock(), **base_kwargs)
    with pytest.raises(HTTPException) as exc:
        hard_block_service.create_export(
            username="alice",
            user_server_id="blackberry",
            document_version_id=1,
            export_format="json",
            execution_mode="sync",
        )
    assert exc.value.status_code == 409


def test_download_url_permissions_and_ready_status():
    repo = FakeRepo()
    storage = FakeStorageService()
    attachment_service = AttachmentService(repository=repo, storage_service=storage)
    export_service = ExportService(
        repository=repo,
        storage_service=storage,
        validation_gate_provider=GateWarn(),
        async_job_service=InlineAsyncJobService(),
    )

    upload = attachment_service.create_upload_url(
        username="alice",
        user_server_id="blackberry",
        document_version_id=1,
        filename="evidence.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        link_type="evidence",
        ttl_seconds=300,
    )
    attachment_id = upload["attachment"]["id"]
    with pytest.raises(HTTPException):
        attachment_service.get_download_url(user_server_id="strawberry", attachment_id=attachment_id)

    export = export_service.create_export(
        username="alice",
        user_server_id="blackberry",
        document_version_id=1,
        export_format="json",
        execution_mode="sync",
    )
    export_id = export["id"]
    assert export_service.get_export_download_url(user_server_id="blackberry", export_id=export_id)["url"]

    repo.exports[export_id]["status"] = "processing"
    with pytest.raises(HTTPException):
        export_service.get_export_download_url(user_server_id="blackberry", export_id=export_id)
