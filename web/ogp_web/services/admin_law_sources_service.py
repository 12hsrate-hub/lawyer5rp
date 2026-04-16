from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException, status

from ogp_web.services.auth_service import AuthUser
from ogp_web.services.job_status_service import enrich_job_status
from ogp_web.services.law_admin_service import LawAdminService
from ogp_web.services.law_sources_validation import validate_source_urls
from ogp_web.services.server_context_service import resolve_user_server_permissions
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore
from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore
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


def _build_projection_bridge_summary(
    *,
    server_code: str,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    active_law_version: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if projections_store is None:
        return None
    runs = projections_store.list_runs(server_code=server_code)
    if not runs:
        return None
    active_version_id = int((active_law_version or {}).get("id") or 0)
    selected_run = None
    for run in runs:
        summary_json = dict(run.summary_json or {})
        activation = dict(summary_json.get("activation") or {})
        if active_version_id > 0 and int(activation.get("law_version_id") or 0) == active_version_id:
            selected_run = run
            break
    if selected_run is None:
        selected_run = runs[0]
    summary_json = dict(selected_run.summary_json or {})
    materialization = dict(summary_json.get("materialization") or {})
    activation = dict(summary_json.get("activation") or {})
    return {
        "run_id": int(selected_run.id),
        "status": str(selected_run.status or ""),
        "decision_status": str(summary_json.get("decision_status") or ""),
        "law_set_id": int(materialization.get("law_set_id") or 0) or None,
        "law_version_id": int(activation.get("law_version_id") or 0) or None,
        "matches_active_law_version": (
            active_version_id > 0 and int(activation.get("law_version_id") or 0) == active_version_id
            if active_version_id > 0
            else None
        ),
        "created_at": str(selected_run.created_at or ""),
    }


def build_law_sources_status_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
) -> dict[str, Any]:
    snapshot = LawAdminService(workflow_service).get_effective_sources(server_code=server_code)
    projection_bridge = _build_projection_bridge_summary(
        server_code=server_code,
        projections_store=projections_store,
        active_law_version=snapshot.active_law_version if isinstance(snapshot.active_law_version, dict) else None,
    )
    return {
        "server_code": server_code,
        "primary_explanation": "projection_bridge" if projection_bridge else "legacy_effective_sources",
        "projection_bridge": projection_bridge,
        "source_urls": list(snapshot.source_urls),
        "source_origin": snapshot.source_origin,
        "manifest_item": snapshot.manifest_item,
        "manifest_version": snapshot.manifest_version,
        "active_law_version": snapshot.active_law_version,
        "bundle_meta": snapshot.bundle_meta,
    }


def _legacy_source_set_key(*, server_code: str) -> str:
    normalized_server = str(server_code or "").strip().lower()
    return f"legacy-{normalized_server}-default"


def backfill_law_sources_source_set_payload(
    *,
    workflow_service: ContentWorkflowService,
    source_sets_store: LawSourceSetsStore,
    server_code: str,
    actor_user_id: int,
    request_id: str,
) -> dict[str, Any]:
    normalized_server = str(server_code or "").strip().lower()
    if not normalized_server:
        raise ValueError("server_code_required")

    snapshot = LawAdminService(workflow_service).get_effective_sources(server_code=normalized_server)
    source_urls = list(snapshot.source_urls)
    if not source_urls:
        raise ValueError("server_has_no_law_qa_sources")

    source_set_key = _legacy_source_set_key(server_code=normalized_server)
    source_set = source_sets_store.get_source_set(source_set_key=source_set_key)
    source_set_created = False
    if source_set is None:
        source_set = source_sets_store.create_source_set(
            source_set_key=source_set_key,
            title=f"Legacy law sources import for {normalized_server}",
            description="Imported from legacy flat law source URLs.",
        )
        source_set_created = True

    revisions = source_sets_store.list_revisions(source_set_key=source_set_key)
    latest_revision = revisions[0] if revisions else None
    revision_created = False
    if latest_revision and latest_revision.status == "legacy_flat" and tuple(source_urls) == latest_revision.container_urls:
        revision = latest_revision
    else:
        revision = source_sets_store.create_revision(
            source_set_key=source_set_key,
            container_urls=source_urls,
            status="legacy_flat",
            adapter_policy_json={"mode": "legacy_flat_import"},
            metadata_json={
                "import_mode": "legacy_flat",
                "source_origin": snapshot.source_origin,
                "server_code": normalized_server,
                "actor_user_id": int(actor_user_id),
                "request_id": str(request_id or ""),
            },
        )
        revision_created = True

    bindings = source_sets_store.list_bindings(server_code=normalized_server)
    binding = next((item for item in bindings if item.source_set_key == source_set_key), None)
    binding_created = False
    if binding is None:
        binding = source_sets_store.create_binding(
            server_code=normalized_server,
            source_set_key=source_set_key,
            priority=100,
            is_active=True,
            metadata_json={
                "origin": "legacy_import",
                "source_origin": snapshot.source_origin,
                "actor_user_id": int(actor_user_id),
                "request_id": str(request_id or ""),
            },
        )
        binding_created = True

    return {
        "ok": True,
        "changed": bool(source_set_created or revision_created or binding_created),
        "server_code": normalized_server,
        "source_origin": snapshot.source_origin,
        "source_urls": source_urls,
        "source_set_key": source_set_key,
        "source_set_created": source_set_created,
        "revision_created": revision_created,
        "binding_created": binding_created,
        "source_set": {
            "source_set_key": source_set.source_set_key,
            "title": source_set.title,
            "description": source_set.description,
            "scope": source_set.scope,
        },
        "revision": {
            "id": revision.id,
            "revision": revision.revision,
            "status": revision.status,
            "container_urls": list(revision.container_urls),
            "metadata_json": dict(revision.metadata_json),
        },
        "binding": {
            "id": binding.id,
            "server_code": binding.server_code,
            "source_set_key": binding.source_set_key,
            "priority": binding.priority,
            "is_active": binding.is_active,
            "metadata_json": dict(binding.metadata_json),
        },
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
    source_urls: list[str],
) -> dict[str, Any]:
    return validate_law_sources_preview_payload(source_urls=source_urls)


def validate_law_sources_preview_payload(*, source_urls: list[str]) -> dict[str, Any]:
    validation = validate_source_urls(source_urls)
    return {
        "ok": True,
        "accepted_urls": list(validation.accepted_urls),
        "invalid_urls": list(validation.invalid_urls),
        "invalid_details": list(validation.invalid_details),
        "duplicate_count": validation.duplicate_count,
        "duplicate_urls": list(validation.duplicate_urls),
        "accepted_count": len(validation.accepted_urls),
        "invalid_count": len(validation.invalid_urls),
    }


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
