from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ogp_web.dependencies import get_user_store, requires_permission
from ogp_web.schemas_artifacts import ExportCreateRequest, ExportDownloadUrlResponse, ExportResponse
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.async_job_service import AsyncJobService
from ogp_web.services.export_service import ExportService
from ogp_web.services.object_storage_service import ObjectStorageService
from ogp_web.storage.artifact_repository import ArtifactRepository
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["exports"])


def _service(store: UserStore, request: Request) -> ExportService:
    queue_provider = getattr(request.app.state, "queue_provider", None)
    return ExportService(
        repository=ArtifactRepository(store.backend),
        storage_service=ObjectStorageService(),
        async_job_service=AsyncJobService(store.backend, queue_provider=queue_provider),
    )


@router.post("/api/document-versions/{version_id}/exports", response_model=ExportResponse)
async def create_export(
    version_id: int,
    payload: ExportCreateRequest,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ExportResponse:
    item = _service(store, request).create_export(
        username=user.username,
        user_server_id=user.server_code,
        document_version_id=version_id,
        export_format=payload.format,
        execution_mode=payload.execution_mode,
        request_id=getattr(request.state, "request_id", ""),
    )
    return ExportResponse(**item)


@router.get("/api/document-versions/{version_id}/exports", response_model=list[ExportResponse])
async def list_exports(
    version_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> list[ExportResponse]:
    return [
        ExportResponse(**item)
        for item in _service(store, request).list_exports(user_server_id=user.server_code, document_version_id=version_id)
    ]


@router.get("/api/exports/{export_id}", response_model=ExportResponse)
async def get_export(
    export_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ExportResponse:
    return ExportResponse(**_service(store, request).get_export(user_server_id=user.server_code, export_id=export_id))


@router.get("/api/exports/{export_id}/download-url", response_model=ExportDownloadUrlResponse)
async def get_export_download_url(
    export_id: int,
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ExportDownloadUrlResponse:
    return ExportDownloadUrlResponse(
        **_service(store, request).get_export_download_url(user_server_id=user.server_code, export_id=export_id)
    )
