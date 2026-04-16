from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from ogp_web.services.async_job_service import AsyncJobService
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.job_status_service import enrich_job_status
from ogp_web.storage.case_repository import CaseRepository
from ogp_web.storage.user_store import UserStore


class JobsRuntimeService:
    def _service(self, *, store: UserStore, request: Request) -> AsyncJobService:
        queue_provider = getattr(request.app.state, "queue_provider", None)
        return AsyncJobService(store.backend, queue_provider=queue_provider)

    def _actor_id(self, *, store: UserStore, username: str) -> int | None:
        return CaseRepository(store.backend).get_user_id_by_username(username)

    def _translate_service_error(self, exc: Exception) -> HTTPException:
        if isinstance(exc, LookupError):
            return HTTPException(status_code=404, detail=[str(exc)])
        if isinstance(exc, PermissionError):
            return HTTPException(status_code=403, detail=[str(exc)])
        return HTTPException(status_code=400, detail=[str(exc)])

    def _job_create_response(self, job: dict[str, Any]) -> dict[str, Any]:
        enriched = enrich_job_status(job, subsystem="async_job")
        return {
            "job_id": int(job["id"]),
            "status": str(job["status"]),
            "raw_status": str(enriched["raw_status"]),
            "canonical_status": str(enriched["canonical_status"]),
        }

    def _job_action_response(self, job: dict[str, Any]) -> dict[str, Any]:
        enriched = enrich_job_status(job, subsystem="async_job")
        return {
            "id": int(job["id"]),
            "status": str(job["status"]),
            "raw_status": str(enriched["raw_status"]),
            "canonical_status": str(enriched["canonical_status"]),
            "job_type": str(job["job_type"]),
        }

    def list_jobs(
        self,
        *,
        request: Request,
        store: UserStore,
        user: AuthUser,
        limit: int,
    ) -> dict[str, Any]:
        items = self._service(store=store, request=request).list_jobs(server_id=user.server_code, limit=limit)
        return {"items": [enrich_job_status(item, subsystem="async_job") for item in items]}

    def get_job(
        self,
        *,
        job_id: int,
        request: Request,
        store: UserStore,
        user: AuthUser,
    ) -> dict[str, Any]:
        try:
            job = self._service(store=store, request=request).get_job(job_id=job_id, server_id=user.server_code)
        except Exception as exc:  # noqa: BLE001
            raise self._translate_service_error(exc) from exc
        return enrich_job_status(job, subsystem="async_job")

    def list_job_attempts(
        self,
        *,
        job_id: int,
        request: Request,
        store: UserStore,
        user: AuthUser,
    ) -> dict[str, Any]:
        try:
            items = self._service(store=store, request=request).list_attempts(job_id=job_id, server_id=user.server_code)
        except Exception as exc:  # noqa: BLE001
            raise self._translate_service_error(exc) from exc
        return {"items": [enrich_job_status(item, subsystem="async_job") for item in items]}

    def retry_job(
        self,
        *,
        job_id: int,
        request: Request,
        store: UserStore,
        user: AuthUser,
    ) -> dict[str, Any]:
        try:
            job = self._service(store=store, request=request).retry_job(job_id=job_id, server_id=user.server_code)
        except Exception as exc:  # noqa: BLE001
            raise self._translate_service_error(exc) from exc
        return self._job_action_response(job)

    def cancel_job(
        self,
        *,
        job_id: int,
        request: Request,
        store: UserStore,
        user: AuthUser,
    ) -> dict[str, Any]:
        try:
            job = self._service(store=store, request=request).cancel_job(job_id=job_id, server_id=user.server_code)
        except Exception as exc:  # noqa: BLE001
            raise self._translate_service_error(exc) from exc
        return self._job_action_response(job)

    def create_document_generation_job(
        self,
        *,
        document_id: int,
        content_json: dict[str, Any] | list[Any] | str | int | float | bool,
        idempotency_key: str | None,
        publish_batch_id: int | None,
        request: Request,
        store: UserStore,
        user: AuthUser,
    ) -> dict[str, Any]:
        try:
            job = self._service(store=store, request=request).create_job(
                server_scope="server",
                server_id=user.server_code,
                job_type="document_generation",
                entity_type="document",
                entity_id=document_id,
                payload_json={
                    "document_id": document_id,
                    "content_json": content_json,
                    "username": user.username,
                    "user_server_id": user.server_code,
                    "request_id": getattr(request.state, "request_id", ""),
                    "publish_batch_id": publish_batch_id,
                },
                created_by=self._actor_id(store=store, username=user.username),
                idempotency_key=idempotency_key,
                enqueue=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._translate_service_error(exc) from exc
        return self._job_create_response(job)

    def create_export_job(
        self,
        *,
        version_id: int,
        export_format: str,
        idempotency_key: str | None,
        publish_batch_id: int | None,
        request: Request,
        store: UserStore,
        user: AuthUser,
    ) -> dict[str, Any]:
        try:
            job = self._service(store=store, request=request).create_job(
                server_scope="server",
                server_id=user.server_code,
                job_type="document_export",
                entity_type="document_version",
                entity_id=version_id,
                payload_json={
                    "version_id": version_id,
                    "format": export_format,
                    "request_id": getattr(request.state, "request_id", ""),
                    "publish_batch_id": publish_batch_id,
                },
                created_by=self._actor_id(store=store, username=user.username),
                idempotency_key=idempotency_key,
                enqueue=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._translate_service_error(exc) from exc
        return self._job_create_response(job)

    def create_reindex_job(
        self,
        *,
        scope: str,
        idempotency_key: str | None,
        request: Request,
        store: UserStore,
        user: AuthUser,
    ) -> dict[str, Any]:
        normalized_scope = str(scope or "all").strip().lower() or "all"
        resolved_idempotency_key = str(idempotency_key or "").strip() or f"content_reindex:{normalized_scope}"
        try:
            job = self._service(store=store, request=request).create_job(
                server_scope="global",
                server_id=None,
                job_type="content_reindex",
                entity_type="content",
                entity_id=None,
                payload_json={"scope": normalized_scope, "request_id": getattr(request.state, "request_id", "")},
                created_by=self._actor_id(store=store, username=user.username),
                idempotency_key=resolved_idempotency_key,
                enqueue=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._translate_service_error(exc) from exc
        return self._job_create_response(job)

    def create_import_job(
        self,
        *,
        source: str,
        idempotency_key: str | None,
        request: Request,
        store: UserStore,
        user: AuthUser,
    ) -> dict[str, Any]:
        normalized_source = str(source or "").strip()
        if not normalized_source:
            raise HTTPException(status_code=400, detail=["source обязателен."])
        try:
            job = self._service(store=store, request=request).create_job(
                server_scope="global",
                server_id=None,
                job_type="content_import",
                entity_type="content",
                entity_id=None,
                payload_json={"source": normalized_source, "request_id": getattr(request.state, "request_id", "")},
                created_by=self._actor_id(store=store, username=user.username),
                idempotency_key=idempotency_key,
                enqueue=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._translate_service_error(exc) from exc
        return self._job_create_response(job)
