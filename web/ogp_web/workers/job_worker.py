from __future__ import annotations

import logging
import socket
import uuid
from typing import Any, Callable

from ogp_web.services.async_job_service import AsyncJobService
from ogp_web.services.exam_import_tasks import execute_transitional_runner


logger = logging.getLogger(__name__)


class JobWorker:
    def __init__(
        self,
        *,
        service: AsyncJobService,
        server_id: str | None,
        worker_id: str | None = None,
        handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
    ) -> None:
        self.service = service
        self.server_id = str(server_id or "").strip().lower() or None
        self.worker_id = worker_id or f"worker-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self.handlers = handlers or self._default_handlers()

    def _default_handlers(self) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
        return {
            "document_generation": self._handle_document_generation,
            "document_export": self._handle_document_export,
            "content_reindex": self._handle_content_reindex,
            "content_import": self._handle_content_import,
        }

    def run_once(self, *, limit: int = 10) -> list[dict[str, Any]]:
        jobs = self.service.claim_available_jobs(worker_id=self.worker_id, server_id=self.server_id, limit=limit)
        completed: list[dict[str, Any]] = []
        for job in jobs:
            result = self._process_job(job)
            completed.append(result)
        return completed

    def _process_job(self, job: dict[str, Any]) -> dict[str, Any]:
        handler = self.handlers.get(job["job_type"])
        if handler is None:
            return self.service.mark_failed(
                job_id=int(job["id"]),
                worker_id=self.worker_id,
                error_code="unsupported_job_type",
                error_message=f"No handler for job type {job['job_type']}",
                error_details={"job_type": job["job_type"]},
            )

        try:
            result = handler(job)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Async job failed: job_id=%s type=%s", job.get("id"), job.get("job_type"))
            return self.service.mark_failed(
                job_id=int(job["id"]),
                worker_id=self.worker_id,
                error_code=exc.__class__.__name__.lower(),
                error_message=str(exc) or exc.__class__.__name__,
                error_details={"handler": handler.__name__, "worker_id": self.worker_id},
            )
        return self.service.mark_succeeded(job_id=int(job["id"]), worker_id=self.worker_id, result_json=result)

    def _handle_document_generation(self, job: dict[str, Any]) -> dict[str, Any]:
        from ogp_web.services.document_service import DocumentService
        from ogp_web.storage.case_repository import CaseRepository
        from ogp_web.storage.document_repository import DocumentRepository

        payload = dict(job.get("payload_json") or {})
        document_service = DocumentService(
            case_repository=CaseRepository(self.service.backend),
            document_repository=DocumentRepository(self.service.backend),
        )
        version = document_service.create_document_version(
            username=str(payload["username"]),
            user_server_id=str(payload["user_server_id"]),
            document_id=int(payload["document_id"]),
            content_json=payload.get("content_json") or {},
        )
        return {
            "document_version": version,
            "snapshot": payload.get("snapshot") or {},
            "citations": payload.get("citations") or [],
            "validation": payload.get("validation") or {},
        }

    def _handle_document_export(self, job: dict[str, Any]) -> dict[str, Any]:
        from ogp_web.storage.validation_repository import ValidationRepository

        payload = dict(job.get("payload_json") or {})
        validation_repo = ValidationRepository(self.service.backend)
        version = validation_repo.get_document_version_target(version_id=int(payload["version_id"]))
        if version is None:
            raise ValueError("Document version for export was not found.")
        return {
            "version_id": int(version["id"]),
            "document_id": int(version["document_id"]),
            "export_format": str(payload.get("format") or "json"),
            "artifact": {
                "status": "ready",
                "name": f"document-{version['id']}.{payload.get('format') or 'json'}",
            },
        }

    def _handle_content_reindex(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = dict(job.get("payload_json") or {})
        return {
            "reindex_scope": payload.get("scope") or "all",
            "reindexed": True,
            "request_id": payload.get("request_id") or "",
        }

    def _handle_content_import(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = dict(job.get("payload_json") or {})

        def _runner(progress_callback=None):
            if progress_callback:
                progress_callback({"phase": "started"})
            return {
                "imported": True,
                "source": payload.get("source") or "transitional_adapter",
                "request_id": payload.get("request_id") or "",
            }

        return execute_transitional_runner(_runner)
