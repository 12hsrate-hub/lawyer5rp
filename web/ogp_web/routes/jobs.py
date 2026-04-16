from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ogp_web.dependencies import get_jobs_runtime_service, get_user_store, requires_permission
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.jobs_runtime_service import JobsRuntimeService
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["jobs"])


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
    jobs_runtime_service: JobsRuntimeService = Depends(get_jobs_runtime_service),
):
    return jobs_runtime_service.list_jobs(request=request, store=store, user=user, limit=limit)


@router.get("/api/jobs/{job_id}")
async def get_job(
    job_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    jobs_runtime_service: JobsRuntimeService = Depends(get_jobs_runtime_service),
):
    return jobs_runtime_service.get_job(job_id=job_id, request=request, store=store, user=user)


@router.get("/api/jobs/{job_id}/attempts")
async def list_job_attempts(
    job_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    jobs_runtime_service: JobsRuntimeService = Depends(get_jobs_runtime_service),
):
    return jobs_runtime_service.list_job_attempts(job_id=job_id, request=request, store=store, user=user)


@router.post("/api/jobs/{job_id}/retry", response_model=JobActionResponse)
async def retry_job(
    job_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    jobs_runtime_service: JobsRuntimeService = Depends(get_jobs_runtime_service),
):
    return JobActionResponse(**jobs_runtime_service.retry_job(job_id=job_id, request=request, store=store, user=user))


@router.post("/api/jobs/{job_id}/cancel", response_model=JobActionResponse)
async def cancel_job(
    job_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    jobs_runtime_service: JobsRuntimeService = Depends(get_jobs_runtime_service),
):
    return JobActionResponse(**jobs_runtime_service.cancel_job(job_id=job_id, request=request, store=store, user=user))


@router.post("/api/documents/{document_id}/generate-async", response_model=JobCreateResponse)
async def create_document_generation_job(
    document_id: int,
    payload: GenerationAsyncPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    jobs_runtime_service: JobsRuntimeService = Depends(get_jobs_runtime_service),
):
    return JobCreateResponse(
        **jobs_runtime_service.create_document_generation_job(
            document_id=document_id,
            content_json=payload.content_json,
            idempotency_key=payload.idempotency_key,
            publish_batch_id=payload.publish_batch_id,
            request=request,
            store=store,
            user=user,
        )
    )


@router.post("/api/document-versions/{version_id}/exports", response_model=JobCreateResponse)
async def create_export_job(
    version_id: int,
    payload: ExportCreatePayload,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    jobs_runtime_service: JobsRuntimeService = Depends(get_jobs_runtime_service),
):
    return JobCreateResponse(
        **jobs_runtime_service.create_export_job(
            version_id=version_id,
            export_format=payload.format,
            idempotency_key=payload.idempotency_key,
            publish_batch_id=payload.publish_batch_id,
            request=request,
            store=store,
            user=user,
        )
    )


@router.post("/api/admin/reindex", response_model=JobCreateResponse)
async def create_reindex_job(
    payload: AdminReindexPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    store: UserStore = Depends(get_user_store),
    jobs_runtime_service: JobsRuntimeService = Depends(get_jobs_runtime_service),
):
    return JobCreateResponse(
        **jobs_runtime_service.create_reindex_job(
            scope=payload.scope,
            idempotency_key=payload.idempotency_key,
            request=request,
            store=store,
            user=user,
        )
    )


@router.post("/api/admin/import", response_model=JobCreateResponse)
async def create_import_job(
    payload: AdminImportPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    store: UserStore = Depends(get_user_store),
    jobs_runtime_service: JobsRuntimeService = Depends(get_jobs_runtime_service),
):
    return JobCreateResponse(
        **jobs_runtime_service.create_import_job(
            source=payload.source,
            idempotency_key=payload.idempotency_key,
            request=request,
            store=store,
            user=user,
        )
    )
