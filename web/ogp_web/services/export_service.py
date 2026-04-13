from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Protocol

from fastapi import HTTPException, status

from ogp_web.services.object_storage_service import ObjectStorageService
from ogp_web.storage.artifact_repository import ArtifactRepository


@dataclass(frozen=True)
class ExportGateResult:
    mode: str
    reason: str = ""


class ValidationGateProvider(Protocol):
    def evaluate(self, *, document_version_id: int) -> ExportGateResult: ...


class DefaultValidationGateProvider:
    def evaluate(self, *, document_version_id: int) -> ExportGateResult:
        return ExportGateResult(mode="warn", reason="validation_unavailable_default_warn")


class InMemoryJobLayer:
    def submit(self, *, job_name: str, run: Callable[[], None]) -> str:
        job_run_id = f"{job_name}:{uuid.uuid4().hex}"
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return job_run_id


class ExportService:
    def __init__(
        self,
        *,
        repository: ArtifactRepository,
        storage_service: ObjectStorageService,
        validation_gate_provider: ValidationGateProvider | None = None,
        job_layer: InMemoryJobLayer | None = None,
    ):
        self.repository = repository
        self.storage_service = storage_service
        self.validation_gate_provider = validation_gate_provider or DefaultValidationGateProvider()
        self.job_layer = job_layer or InMemoryJobLayer()

    @staticmethod
    def _deserialize(row):
        payload = dict(row)
        payload["metadata_json"] = json.loads(payload.get("metadata_json") or "{}")
        payload["created_at"] = str(payload.get("created_at") or "")
        payload["updated_at"] = str(payload.get("updated_at") or "")
        return payload

    def _resolve_actor(self, username: str) -> int:
        actor_id = self.repository.get_user_id_by_username(username)
        if actor_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Пользователь не найден."])
        return actor_id

    def _get_version_or_404(self, *, version_id: int, user_server_id: str):
        version = self.repository.get_document_version(version_id=version_id)
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Версия документа не найдена."])
        if str(version.get("server_id") or "") != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для версии документа."])
        return dict(version)

    def _build_export_payload(self, *, version_row: dict[str, object], export_format: str) -> bytes:
        content_json = json.loads(version_row.get("content_json") or "null")
        payload = {
            "document_version_id": int(version_row["id"]),
            "document_id": int(version_row["document_id"]),
            "version_number": int(version_row["version_number"]),
            "format": export_format,
            "content": content_json,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def _complete_sync_export(self, export_id: int, version_row: dict[str, object], export_format: str, job_run_id: str | None):
        self.repository.update_export(
            export_id=export_id,
            status="processing",
            storage_key="",
            mime_type="application/octet-stream",
            size_bytes=0,
            checksum="",
            job_run_id=job_run_id,
            metadata_json={"phase": "processing"},
        )
        try:
            payload = self._build_export_payload(version_row=version_row, export_format=export_format)
            storage_key = self.storage_service.build_storage_key(
                server_id=str(version_row["server_id"]),
                entity_type="exports",
                entity_id=export_id,
                filename=f"document_version_{int(version_row['id'])}.{export_format}",
            )
            meta = self.storage_service.store_bytes(storage_key=storage_key, payload=payload)
            result = self.repository.update_export(
                export_id=export_id,
                status="ready",
                storage_key=meta.storage_key,
                mime_type="application/json",
                size_bytes=meta.size_bytes,
                checksum=meta.checksum,
                job_run_id=job_run_id,
                metadata_json={"phase": "ready"},
            )
            return self._deserialize(result)
        except Exception as exc:  # noqa: BLE001
            failed = self.repository.update_export(
                export_id=export_id,
                status="failed",
                storage_key="",
                mime_type="application/octet-stream",
                size_bytes=0,
                checksum="",
                job_run_id=job_run_id,
                metadata_json={"phase": "failed", "error": str(exc)},
            )
            return self._deserialize(failed)

    def create_export(
        self,
        *,
        username: str,
        user_server_id: str,
        document_version_id: int,
        export_format: str,
        execution_mode: str,
    ):
        actor_id = self._resolve_actor(username)
        version_row = self._get_version_or_404(version_id=document_version_id, user_server_id=user_server_id)
        gate = self.validation_gate_provider.evaluate(document_version_id=document_version_id)
        if gate.mode == "hard_block":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=["Export заблокирован validation/readiness gate."])

        created = self.repository.create_export(
            document_version_id=document_version_id,
            server_id=user_server_id,
            export_format=export_format,
            status="pending",
            storage_key="",
            mime_type="application/octet-stream",
            size_bytes=0,
            checksum="",
            created_by=actor_id,
            job_run_id=None,
            metadata_json={"gate_mode": gate.mode, "gate_reason": gate.reason, "execution_mode": execution_mode},
        )
        export_payload = self._deserialize(created)
        export_id = int(export_payload["id"])

        if execution_mode == "sync":
            return self._complete_sync_export(export_id, version_row, export_format, None)

        def _run_async() -> None:
            self._complete_sync_export(export_id, version_row, export_format, export_payload.get("job_run_id"))

        job_run_id = self.job_layer.submit(job_name="export", run=_run_async)
        updated = self.repository.update_export(
            export_id=export_id,
            status="pending",
            storage_key="",
            mime_type="application/octet-stream",
            size_bytes=0,
            checksum="",
            job_run_id=job_run_id,
            metadata_json={"gate_mode": gate.mode, "gate_reason": gate.reason, "execution_mode": execution_mode},
        )
        return self._deserialize(updated)

    def list_exports(self, *, user_server_id: str, document_version_id: int):
        self._get_version_or_404(version_id=document_version_id, user_server_id=user_server_id)
        return [self._deserialize(row) for row in self.repository.list_exports_for_document_version(document_version_id=document_version_id)]

    def get_export(self, *, user_server_id: str, export_id: int):
        row = self.repository.get_export(export_id=export_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Export не найден."])
        payload = self._deserialize(row)
        if str(payload.get("document_server_id") or payload.get("server_id") or "") != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для export artifact."])
        return payload

    def get_export_download_url(self, *, user_server_id: str, export_id: int, ttl_seconds: int = 600):
        export_payload = self.get_export(user_server_id=user_server_id, export_id=export_id)
        if export_payload.get("status") != "ready":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=["Скачивание доступно только для ready export artifact."])
        presigned = self.storage_service.generate_presigned_download_url(
            storage_key=str(export_payload["storage_key"]),
            ttl_seconds=ttl_seconds,
        )
        return {"export_id": export_id, **presigned}
