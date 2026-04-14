from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ogp_web.dependencies import requires_permission
from ogp_web.schemas import DocumentBuilderBundleResponse
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.document_builder_bundle_service import build_document_builder_bundle


router = APIRouter()


@router.get("/api/document-builder/bundle", response_model=DocumentBuilderBundleResponse)
async def get_document_builder_bundle(
    user: AuthUser = Depends(requires_permission("court_claims")),
    server_id: str = Query(default=""),
    document_type: str = Query(default=""),
) -> DocumentBuilderBundleResponse:
    resolved_server_id = str(server_id or "").strip().lower() or str(user.server_code or "").strip().lower()
    try:
        payload = build_document_builder_bundle(
            server_id=resolved_server_id,
            document_type=document_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    return DocumentBuilderBundleResponse(**payload)
