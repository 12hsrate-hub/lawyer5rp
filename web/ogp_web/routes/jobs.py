from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ogp_web.dependencies import get_user_store, requires_permission
from ogp_web.services.async_job_service import AsyncJobService
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.job_status_service import enrich_job_status
from ogp_web.storage.case_repository import CaseRepository
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["jobs"])


def _service(store: UserStore, request: Request) -> AsyncJobService:
    queue_provider = getattr(request.app.state, "queue_provider", None)
    return AsyncJobService(store.backend, queue_provider=queue_provider)


def _actor_id(store: UserStore, username: str) -> int | None:
    return CaseRepository(store.backend).get_user_id_by_username(username)


def _translate_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=[str(exc)])
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=[str(exc)])
    return HTTPException(status_code=400, detail=[str(exc)])


class JobCreateResponse(BaseModel):
    job_id: int
    status: str
    raw_status: str = ""
    canonical_status: str = ""


class JobActionResponse(BaseModel):
    id: int
    status: str
    raw_status: str = ""
    canonical_status: str = ""
    job_type: str


class GenerationAsyncPayload(BaseModel):
    content_json: dict[str, Any] | list[Any] | str | int | float | bool
    idempotency_key: str | None = None
    publish_batch_id: int | None = None


class ExportCreatePayload(BaseModel):
    format: str = "json"
    idempotency_key: str | None = None
    publish_batch_id: int | None = None


class AdminReindexPayload(BaseModel):
    scope: str = "all"
    idempotency_key: str | None = None


class AdminImportPayload(BaseModel):
    source: str = "manual"
    idempotency_key: str | None = None


@router.get("/api/jobs")
async def list_jobs(
    request: Request,
    limit: int = 50,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
):
    items = _service(store, request).list_jobs(server_id=user.server_code, limit=limit)
    return {"items": [enrich_job_status(item, subsystem="async_job") for item in items]}


@router.get("/api/jobs/{job_id}")
async def get_job(
    job_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
):
    try:
        job = _service(store, request).get_job(job_id=job_id, server_id=user.server_code)
        return enrich_job_status(job, subsystem="async_job")
    except Exception as exc:  # noqa: BLE001
        raise _translate_service_error(exc) from exc


@router.get("/api/jobs/{job_id}/attempts")
async def list_job_attempts(
    job_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
):
    try:
        items = _service(store, request).list_attempts(job_id=job_id, server_id=user.server_code)
        return {"items": [enrich_job_status(item, subsystem="async_job") for item in items]}
    except Exception as exc:  # noqa: BLE001
        raise _translate_service_error(exc) from exc


@router.post("/api/jobs/{job_id}/retry", response_model=JobActionResponse)
async def retry_job(
    job_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
):
    try:
        job = _service(store, request).retry_job(job_id=job_id, server_id=user.server_code)
    except Exception as exc:  # noqa: BLE001
        raise _translate_service_error(exc) from exc
    enriched = enrich_job_status(job, subsystem="async_job")
    return JobActionResponse(
        id=int(job["id"]),
        status=str(job["status"]),
        raw_status=str(enriched["raw_status"]),
        canonical_status=str(enriched["canonical_status"]),
        job_type=str(job["job_type"]),
    )


@router.post("/api/jobs/{job_id}/cancel", response_model=JobActionResponse)
async def cancel_job(
    job_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
):
    try:
        job = _service(store, request).cancel_job(job_id=job_id, server_id=user.server_code)
    except Exception as exc:  # noqa: BLE001
        raise _translate_service_error(exc) from exc
    enriched = enrich_job_status(job, subsystem="async_job")
    return JobActionResponse(
        id=int(job["id"]),
        status=str(job["status"]),
        raw_status=str(enriched["raw_status"]),
        canonical_status=str(enriched["canonical_status"]),
        job_type=str(job["job_type"]),
    )


@router.post("/api/documents/{document_id}/generate-async", response_model=JobCreateResponse)
async def create_document_generation_job(
    document_id: int,
    payload: GenerationAsyncPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
):
    try:
        job = _service(store, request).create_job(
            server_scope="server",
            server_id=user.server_code,
            job_type="document_generation",
            entity_type="document",
            entity_id=document_id,
            payload_json={
                "document_id": document_id,
                "content_json": payload.content_json,
                "username": user.username,
                "user_server_id": user.server_code,
                "request_id": getattr(request.state, "request_id", ""),
                "publish_batch_id": payload.publish_batch_id,
            },
            created_by=_actor_id(store, user.username),
            idempotency_key=payload.idempotency_key,
            enqueue=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_service_error(exc) from exc
    enriched = enrich_job_status(job, subsystem="async_job")
    return JobCreateResponse(
        job_id=int(job["id"]),
        status=str(job["status"]),
        raw_status=str(enriched["raw_status"]),
        canonical_status=str(enriched["canonical_status"]),
    )


@router.post("/api/document-versions/{version_id}/exports", response_model=JobCreateResponse)
async def create_export_job(
    version_id: int,
    payload: ExportCreatePayload,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
):
    try:
        job = _service(store, request).create_job(
            server_scope="server",
            server_id=user.server_code,
            job_type="document_export",
            entity_type="document_version",
            entity_id=version_id,
            payload_json={
                "version_id": version_id,
                "format": payload.format,
                "request_id": getattr(request.state, "request_id", ""),
                "publish_batch_id": payload.publish_batch_id,
            },
            created_by=_actor_id(store, user.username),
            idempotency_key=payload.idempotency_key,
            enqueue=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_service_error(exc) from exc
    enriched = enrich_job_status(job, subsystem="async_job")
    return JobCreateResponse(
        job_id=int(job["id"]),
        status=str(job["status"]),
        raw_status=str(enriched["raw_status"]),
        canonical_status=str(enriched["canonical_status"]),
    )


@router.post("/api/admin/reindex", response_model=JobCreateResponse)
async def create_reindex_job(
    payload: AdminReindexPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    store: UserStore = Depends(get_user_store),
):
    normalized_scope = str(payload.scope or "all").strip().lower() or "all"
    resolved_idempotency_key = str(payload.idempotency_key or "").strip() or f"content_reindex:{normalized_scope}"
    try:
        job = _service(store, request).create_job(
            server_scope="global",
            server_id=None,
            job_type="content_reindex",
            entity_type="content",
            entity_id=None,
            payload_json={"scope": normalized_scope, "request_id": getattr(request.state, "request_id", "")},
            created_by=_actor_id(store, user.username),
            idempotency_key=resolved_idempotency_key,
            enqueue=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_service_error(exc) from exc
    enriched = enrich_job_status(job, subsystem="async_job")
    return JobCreateResponse(
        job_id=int(job["id"]),
        status=str(job["status"]),
        raw_status=str(enriched["raw_status"]),
        canonical_status=str(enriched["canonical_status"]),
    )


@router.post("/api/admin/import", response_model=JobCreateResponse)
async def create_import_job(
    payload: AdminImportPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    store: UserStore = Depends(get_user_store),
):
    if not str(payload.source or "").strip():
        raise HTTPException(status_code=400, detail=["source обязателен."])
    try:
        job = _service(store, request).create_job(
            server_scope="global",
            server_id=None,
            job_type="content_import",
            entity_type="content",
            entity_id=None,
            payload_json={"source": payload.source, "request_id": getattr(request.state, "request_id", "")},
            created_by=_actor_id(store, user.username),
            idempotency_key=payload.idempotency_key,
            enqueue=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_service_error(exc) from exc
    enriched = enrich_job_status(job, subsystem="async_job")
    return JobCreateResponse(
        job_id=int(job["id"]),
        status=str(job["status"]),
        raw_status=str(enriched["raw_status"]),
        canonical_status=str(enriched["canonical_status"]),
    )
