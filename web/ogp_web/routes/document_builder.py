from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ogp_web.dependencies import get_user_store
from ogp_web.schemas import DocumentBuilderBundleResponse
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.services.document_builder_bundle_service import build_document_builder_bundle
from ogp_web.services.section_capability_context_service import (
    ensure_section_permission,
    ensure_section_runtime_requirement,
    resolve_section_capability_context,
)
from ogp_web.storage.user_store import UserStore


router = APIRouter()


@router.get("/api/document-builder/bundle", response_model=DocumentBuilderBundleResponse)
async def get_document_builder_bundle(
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    server_id: str = Query(default=""),
    document_type: str = Query(default=""),
) -> DocumentBuilderBundleResponse:
    context = resolve_section_capability_context(
        store,
        user.username,
        section_code="court_claim",
        explicit_server_code=server_id,
    )
    ensure_section_permission(context)
    ensure_section_runtime_requirement(context, route_path="/api/document-builder/bundle")
    try:
        payload = build_document_builder_bundle(
            server_id=context.selected_server_code,
            document_type=document_type,
            backend=getattr(store, "backend", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    return DocumentBuilderBundleResponse(**payload)
