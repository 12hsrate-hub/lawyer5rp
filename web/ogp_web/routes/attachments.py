from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from ogp_web.dependencies import get_user_store, requires_permission
from ogp_web.schemas_artifacts import (
    AttachmentDownloadUrlResponse,
    AttachmentResponse,
    AttachmentUploadUrlRequest,
    AttachmentUploadUrlResponse,
)
from ogp_web.services.attachment_service import AttachmentService
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.object_storage_service import ObjectStorageService
from ogp_web.storage.artifact_repository import ArtifactRepository
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["attachments"])


def _service(store: UserStore) -> AttachmentService:
    return AttachmentService(
        repository=ArtifactRepository(store.backend),
        storage_service=ObjectStorageService(),
    )


@router.post("/api/document-versions/{version_id}/attachments/upload-url", response_model=AttachmentUploadUrlResponse)
async def create_attachment_upload_url(
    version_id: int,
    payload: AttachmentUploadUrlRequest,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> AttachmentUploadUrlResponse:
    result = _service(store).create_upload_url(
        username=user.username,
        user_server_id=user.server_code,
        document_version_id=version_id,
        filename=payload.filename,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        link_type=payload.link_type,
        ttl_seconds=payload.ttl_seconds,
    )
    return AttachmentUploadUrlResponse(
        document_version_id=result["document_version_id"],
        attachment=AttachmentResponse(**result["attachment"]),
        upload=result["upload"],
    )


@router.post("/api/attachments/{attachment_id}/finalize", response_model=AttachmentResponse)
async def finalize_attachment_upload(
    attachment_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> AttachmentResponse:
    payload = _service(store).finalize_upload(
        username=user.username,
        user_server_id=user.server_code,
        attachment_id=attachment_id,
    )
    return AttachmentResponse(**payload)


@router.get("/api/document-versions/{version_id}/attachments", response_model=list[AttachmentResponse])
async def list_version_attachments(
    version_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> list[AttachmentResponse]:
    items = _service(store).list_attachments(user_server_id=user.server_code, document_version_id=version_id)
    return [AttachmentResponse(**item) for item in items]


@router.get("/api/attachments/{attachment_id}/download-url", response_model=AttachmentDownloadUrlResponse)
async def get_attachment_download_url(
    attachment_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> AttachmentDownloadUrlResponse:
    return AttachmentDownloadUrlResponse(
        **_service(store).get_download_url(user_server_id=user.server_code, attachment_id=attachment_id)
    )


@router.delete("/api/document-versions/{version_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment_link(
    version_id: int,
    attachment_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> Response:
    _service(store).unlink_attachment(
        user_server_id=user.server_code,
        document_version_id=version_id,
        attachment_id=attachment_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
