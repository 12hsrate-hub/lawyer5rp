from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException, status

from ogp_web.services.auth_service import AuthUser
from ogp_web.services.job_status_service import enrich_job_status
from ogp_web.services.law_admin_service import LawAdminService
from ogp_web.services.server_context_service import resolve_user_server_permissions
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.storage.user_store import UserStore


def resolve_law_sources_target_server_code(
    *,
    user: AuthUser,
    user_store: UserStore,
    requested_server_code: str = "",
) -> str:
    normalized = str(requested_server_code or "").strip().lower()
    target_server_code = normalized or user.server_code
    if target_server_code == user.server_code:
        return target_server_code

    current_permissions = resolve_user_server_permissions(user_store, user.username, server_code=user.server_code)
    if not current_permissions.has("manage_servers"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=["Недостаточно прав для управления источниками законов другого сервера."],
        )

    target_permissions = resolve_user_server_permissions(user_store, user.username, server_code=target_server_code)
    if not target_permissions.has("manage_laws"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=[f"Недостаточно прав manage_laws для сервера '{target_server_code}'."],
        )

    return target_server_code


def build_law_sources_status_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
) -> dict[str, Any]:
    snapshot = LawAdminService(workflow_service).get_effective_sources(server_code=server_code)
    return {
        "server_code": server_code,
        "source_urls": list(snapshot.source_urls),
        "source_origin": snapshot.source_origin,
        "manifest_item": snapshot.manifest_item,
        "manifest_version": snapshot.manifest_version,
        "active_law_version": snapshot.active_law_version,
        "bundle_meta": snapshot.bundle_meta,
    }


def sync_law_sources_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    actor_user_id: int,
    request_id: str,
) -> dict[str, Any]:
    return LawAdminService(workflow_service).sync_sources_manifest_from_server_config(
        server_code=server_code,
        actor_user_id=actor_user_id,
        request_id=request_id,
        safe_rerun=True,
    )


def rebuild_law_sources_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    source_urls: list[str],
    actor_user_id: int,
    request_id: str,
    persist_sources: bool,
) -> dict[str, Any]:
    return LawAdminService(workflow_service).rebuild_index(
        server_code=server_code,
        source_urls=source_urls,
        actor_user_id=actor_user_id,
        request_id=request_id,
        persist_sources=bool(persist_sources),
    )


def save_law_sources_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    source_urls: list[str],
    actor_user_id: int,
    request_id: str,
) -> dict[str, Any]:
    return LawAdminService(workflow_service).publish_sources_manifest(
        server_code=server_code,
        source_urls=source_urls,
        actor_user_id=actor_user_id,
        request_id=request_id,
        comment="law_sources_save_only",
    )


def preview_law_sources_payload(
    *,
    workflow_service: ContentWorkflowService,
    source_urls: list[str],
) -> dict[str, Any]:
    return LawAdminService(workflow_service).preview_sources(source_urls=source_urls)


def list_law_sources_history_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    limit: int,
) -> dict[str, Any]:
    return LawAdminService(workflow_service).list_recent_versions(server_code=server_code, limit=limit)


def describe_law_sources_dependencies_payload(*, workflow_service: ContentWorkflowService) -> dict[str, Any]:
    return LawAdminService(workflow_service).describe_sources_dependencies()


def require_law_sources_task_status_payload(
    *,
    task_id: str,
    target_server_code: str,
    task_loader: Callable[[str], dict[str, Any] | None],
) -> dict[str, Any]:
    task = task_loader(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Задача не найдена."])
    if task.get("scope") != "law_sources_rebuild":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Задача не найдена."])
    if str(task.get("server_code") or "") != target_server_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Доступ запрещён."])
    return enrich_job_status(task, subsystem="admin_task")
