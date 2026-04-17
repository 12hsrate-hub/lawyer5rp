from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ogp_web.dependencies import get_user_store
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.services.law_context_readiness_service import build_law_context_readiness_service
from ogp_web.services.section_capability_context_service import (
    ensure_section_permission,
    resolve_section_capability_context,
)
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["runtime_context"])


@router.get("/api/runtime/sections/{section_code}/capability-context")
async def get_section_capability_context(
    section_code: str,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    server_code: str = Query(default=""),
) -> dict[str, object]:
    try:
        context = resolve_section_capability_context(
            store,
            user.username,
            section_code=section_code,
            explicit_server_code=server_code,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    ensure_section_permission(context)
    return context.to_payload()


@router.get("/api/runtime/servers/{server_code}/law-context-readiness")
async def get_server_law_context_readiness(
    server_code: str,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    requested_law_version_id: int | None = Query(default=None),
) -> dict[str, object]:
    context = resolve_section_capability_context(
        store,
        user.username,
        section_code="law_qa",
        explicit_server_code=server_code,
    )
    ensure_section_permission(context)
    readiness = build_law_context_readiness_service(backend=getattr(store, "backend", None)).get_readiness(
        server_code=context.selected_server_code,
        requested_law_version_id=requested_law_version_id,
    )
    return readiness.to_payload()
