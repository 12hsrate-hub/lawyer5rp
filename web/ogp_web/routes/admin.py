from __future__ import annotations

import logging
import os
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from datetime import datetime, timezone

from ogp_web.dependencies import get_content_workflow_service
from ogp_web.dependencies import (
    get_admin_analytics_service,
    get_admin_ai_pipeline_service,
    get_admin_dashboard_service,
    get_canonical_law_documents_store,
    get_canonical_law_document_versions_store,
    get_law_source_discovery_store,
    get_law_source_sets_store,
    get_server_effective_law_projections_store,
    get_admin_metrics_store,
    get_admin_task_ops_service,
    get_exam_answers_store,
    get_user_store,
    requires_permission,
)
from ogp_web.dependencies import get_runtime_law_sets_store, get_runtime_servers_store
from ogp_web.schemas import (
    AdminBlockPayload,
    AdminBulkActionPayload,
    AdminCatalogItemPayload,
    AdminCatalogRollbackPayload,
    AdminServerTemplatePreviewPayload,
    AdminCatalogWorkflowPayload,
    AdminCanonicalLawDocumentIngestPayload,
    AdminCanonicalLawDocumentVersionFetchPayload,
    AdminCanonicalLawDocumentVersionIngestPayload,
    AdminCanonicalLawDocumentVersionParsePayload,
    AdminLawProjectionRunPayload,
    AdminLawProjectionDecisionPayload,
    AdminLawProjectionMaterializePayload,
    AdminLawProjectionActivatePayload,
    AdminDeactivatePayload,
    AdminEmailUpdatePayload,
    AdminExamScoreResetPayload,
    AdminLawSourcesPayload,
    AdminLawSourceDiscoveryRunPayload,
    AdminLawSourceSetPayload,
    AdminLawSourceSetRevisionPayload,
    AdminLawSourceSetBackfillPayload,
    AdminLawSetPayload,
    AdminLawSetRebuildPayload,
    AdminLawSetRollbackPayload,
    AdminLawSourceRegistryPayload,
    AdminServerLawBindingPayload,
    AdminServerSourceSetBindingPayload,
    AdminPasswordResetPayload,
    AdminQuotaPayload,
    AdminRuntimeServerPayload,
    AdminUserRoleAssignmentPayload,
    DocumentVersionProvenanceResponse,
)
from ogp_web.services.law_admin_service import LawAdminService
from ogp_web.services.law_bundle_service import load_law_bundle_meta
from ogp_web.services.law_version_service import resolve_active_law_version
from ogp_web.services.admin_overview_service import (
    build_async_jobs_overview_payload,
    build_exam_import_overview_payload,
    build_law_jobs_overview_payload,
)
from ogp_web.services.auth_service import AuthError, AuthUser, require_admin_user
from ogp_web.services.generated_document_trace_service import (
    list_admin_recent_generated_documents,
    require_admin_generated_document_trace_bundle,
    resolve_generated_document_provenance_payload_from_bundle,
    resolve_generated_document_review_context_payload_from_bundle,
)
from ogp_web.services.point3_policy_service import load_point3_eval_thresholds
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.content_contracts import normalize_content_type
from ogp_web.server_config import resolve_default_server_code
from ogp_web.services.server_context_service import (
    extract_server_shell_context,
    resolve_user_server_context,
    resolve_user_server_permissions,
)
from ogp_web.services.async_job_service import AsyncJobService
from ogp_web.services.admin_analytics_service import AdminAnalyticsService
from ogp_web.services.admin_ai_pipeline_service import AdminAiPipelineService
from ogp_web.services.admin_task_ops_service import AdminTaskOpsService
from ogp_web.services.admin_dashboard_service import AdminDashboardService
from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_server_health_payload,
    create_runtime_server_payload,
    list_runtime_servers_payload,
    set_runtime_server_active_payload,
    update_runtime_server_payload,
)
from ogp_web.services.admin_server_workspace_service import (
    build_server_activity_payload,
    build_server_workspace_payload,
)
from ogp_web.services.admin_server_access_workspace_service import (
    assign_user_role_payload,
    build_server_access_summary_payload,
    list_permissions_payload,
    list_roles_payload,
    list_user_role_assignments_payload,
    revoke_user_role_assignment_payload,
)
from ogp_web.services.admin_server_content_workspace_service import (
    build_server_template_placeholders_payload,
    build_server_template_preview_payload,
    execute_server_content_workflow_payload,
    get_server_template_item_payload,
    list_server_features_payload,
    list_server_templates_payload,
    reset_server_template_to_default_payload,
    save_server_feature_override_payload,
    save_server_template_override_payload,
)
from ogp_web.services.admin_server_laws_workspace_service import (
    build_server_effective_laws_payload,
    build_server_laws_diff_payload,
    build_server_laws_recheck_payload,
    build_server_laws_summary_payload,
    run_server_laws_refresh_preview_payload,
)
from ogp_web.services.admin_law_sets_service import (
    add_runtime_server_law_binding_payload,
    create_law_source_registry_payload,
    create_runtime_server_law_set_payload,
    list_law_source_registry_payload,
    list_runtime_server_law_bindings_payload,
    list_runtime_server_law_sets_payload,
    publish_law_set_payload,
    resolve_law_set_rebuild_context,
    resolve_law_set_rollback_context,
    update_law_set_payload,
    update_law_source_registry_payload,
)
from ogp_web.services.admin_law_sources_service import (
    build_law_sources_status_payload,
    backfill_law_sources_source_set_payload,
    describe_law_sources_dependencies_payload,
    list_law_sources_history_payload,
    preview_law_sources_payload,
    rebuild_law_sources_payload,
    require_law_sources_task_status_payload,
    resolve_law_sources_target_server_code,
    save_law_sources_payload,
    sync_law_sources_payload,
)
from ogp_web.services.admin_catalog_service import (
    build_catalog_audit_payload,
    build_catalog_item_payload,
    build_catalog_list_payload,
    build_catalog_payload_config,
    build_catalog_versions_payload,
    create_catalog_item_payload,
    execute_catalog_workflow_payload,
    normalize_admin_catalog_entity_type,
    resolve_active_change_request,
    resolve_active_change_request_id,
    review_catalog_change_request_payload,
    rollback_catalog_payload,
    validate_catalog_change_request_payload,
    update_catalog_item_payload,
)
from ogp_web.services.admin_users_service import (
    build_admin_role_history_payload,
    build_admin_user_details_payload,
    build_admin_users_csv_content,
    build_admin_users_payload,
)
from ogp_web.services.admin_user_mutations_service import (
    block_admin_user_payload,
    deactivate_admin_user_payload,
    grant_gka_payload,
    grant_tester_payload,
    reactivate_admin_user_payload,
    reset_admin_user_password_payload,
    revoke_gka_payload,
    revoke_tester_payload,
    run_admin_user_mutation,
    set_admin_user_daily_quota_payload,
    unblock_admin_user_payload,
    update_admin_user_email_payload,
    verify_admin_user_email_payload,
)
from ogp_web.services.synthetic_runner_service import SyntheticRunnerService
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_store import UserStore
from ogp_web.storage.runtime_servers_store import RuntimeServerRecord, RuntimeServersStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.canonical_law_documents_store import CanonicalLawDocumentsStore
from ogp_web.storage.canonical_law_document_versions_store import CanonicalLawDocumentVersionsStore
from ogp_web.storage.law_source_discovery_store import LawSourceDiscoveryStore
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore
from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore
from ogp_web.services.admin_canonical_law_documents_service import (
    ingest_discovery_run_documents_payload,
    list_discovery_run_documents_payload,
)
from ogp_web.services.admin_canonical_law_document_versions_service import (
    ingest_discovery_run_document_versions_payload,
    list_canonical_law_document_versions_payload,
    list_discovery_run_document_versions_payload,
)
from ogp_web.services.admin_canonical_law_document_fetch_service import (
    fetch_discovery_run_document_versions_payload,
)
from ogp_web.services.admin_canonical_law_document_parse_service import (
    parse_discovery_run_document_versions_payload,
)
from ogp_web.services.admin_law_source_discovery_service import (
    execute_source_set_discovery_payload,
    list_discovery_run_links_payload,
    list_source_set_discovery_runs_payload,
)
from ogp_web.services.admin_law_source_sets_service import (
    create_server_source_set_binding_payload,
    create_source_set_payload,
    create_source_set_revision_payload,
    list_server_source_set_bindings_payload,
    list_source_set_revisions_payload,
    list_source_sets_payload,
    update_server_source_set_binding_payload,
    update_source_set_payload,
)
from ogp_web.services.admin_law_projection_service import (
    activate_server_effective_law_projection_payload,
    decide_server_effective_law_projection_payload,
    get_server_effective_law_projection_status_payload,
    list_server_effective_law_projection_items_payload,
    list_server_effective_law_projection_runs_payload,
    materialize_server_effective_law_projection_payload,
    preview_server_effective_law_projection_payload,
)
from ogp_web.web import page_context, templates


router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)

_BLUEPRINT_STAGE_LABELS: dict[str, str] = {
    "phase_a_foundation": "Phase A — Stabilize foundation",
    "phase_b_visual_workflows": "Phase B — Visual workflows",
    "phase_c_quality_center": "Phase C — Quality command center",
    "phase_d_scale_out": "Phase D — Multi-server scale-out",
}


def _resolve_admin_platform_stage() -> dict[str, str]:
    raw_stage = str(os.getenv("OGP_ADMIN_PLATFORM_STAGE", "phase_a_foundation") or "").strip().lower()
    stage_code = raw_stage if raw_stage in _BLUEPRINT_STAGE_LABELS else "phase_a_foundation"
    return {
        "stage_code": stage_code,
        "stage_label": _BLUEPRINT_STAGE_LABELS[stage_code],
    }


def _point3_monitoring_threshold(level: str, metric: str, fallback: float) -> float:
    payload = load_point3_eval_thresholds()
    monitoring = payload.get("monitoring") if isinstance(payload, dict) else {}
    level_payload = monitoring.get(level) if isinstance(monitoring, dict) else {}
    try:
        value = float((level_payload or {}).get(metric))
    except (TypeError, ValueError, AttributeError):
        value = fallback
    return value * 100.0


def _raise_admin_http_error(*, status_code: int, code: str, message: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail=[message],
        headers={"X-Error-Code": code},
    )


def _normalize_api_error(exc: Exception, *, source: str) -> dict[str, str]:
    return {
        "source": source,
        "message": str(exc) or f"{source}_error",
    }


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().lower()


def _detail_lines(*items: Any) -> list[str]:
    lines = [str(item or "").strip() for item in items]
    return [line for line in lines if line]


def _raise_http_error(status_code: int, *detail: Any) -> None:
    raise HTTPException(status_code=status_code, detail=_detail_lines(*detail))


def _raise_bad_request(*detail: Any) -> None:
    _raise_http_error(status.HTTP_400_BAD_REQUEST, *detail)


def _raise_not_found(*detail: Any) -> None:
    _raise_http_error(status.HTTP_404_NOT_FOUND, *detail)


def _admin_ok(**payload: Any) -> dict[str, Any]:
    return {"ok": True, **payload}


def _get_async_job_service(request: Request, user_store: UserStore) -> AsyncJobService:
    queue_provider = getattr(request.app.state, "queue_provider", None)
    return AsyncJobService(user_store.backend, queue_provider=queue_provider)


def _get_content_workflow_service_for_request(request: Request) -> ContentWorkflowService:
    override = getattr(request.app, "dependency_overrides", {}).get(get_content_workflow_service)
    if override is None:
        return get_content_workflow_service(request)
    try:
        return override()
    except TypeError:
        return override(request)


def _admin_template_payload(request: Request, user: AuthUser, *, admin_focus: str) -> dict[str, Any]:
    user_store = request.app.state.user_store
    server_config, permissions = resolve_user_server_context(user_store, user.username)
    shell_context = extract_server_shell_context(server_config, permissions)
    return page_context(
        username=user.username,
        nav_active="admin",
        is_admin=permissions.is_admin,
        show_test_pages=permissions.can_access_exam_import,
        show_tester_pages=permissions.can_access_court_claims,
        **shell_context,
        admin_focus=admin_focus,
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user: AuthUser = Depends(requires_permission("manage_servers"))):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="dashboard"),
    )


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request, user: AuthUser = Depends(requires_permission("view_analytics"))):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="dashboard"),
    )


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, user: AuthUser = Depends(requires_permission("manage_servers"))):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="users"),
    )


@router.get("/admin/servers", response_class=HTMLResponse)
async def admin_servers_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="servers"),
    )


@router.get("/admin/servers/{server_code}", response_class=HTMLResponse)
async def admin_server_detail_page(
    request: Request,
    server_code: str,
    user: AuthUser = Depends(require_admin_user),
):
    payload = _admin_template_payload(request, user, admin_focus="servers")
    payload["admin_server_code"] = _normalize_code(server_code)
    return templates.TemplateResponse(
        request,
        "admin.html",
        payload,
    )


@router.get("/admin/laws", response_class=HTMLResponse)
async def admin_laws_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="laws"),
    )


@router.get("/admin/templates", response_class=HTMLResponse)
async def admin_templates_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    _ = user
    return RedirectResponse(url="/admin/servers", status_code=status.HTTP_302_FOUND)


@router.get("/admin/features", response_class=HTMLResponse)
async def admin_features_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    _ = user
    return RedirectResponse(url="/admin/servers", status_code=status.HTTP_302_FOUND)


@router.get("/admin/rules", response_class=HTMLResponse)
async def admin_rules_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    _ = user
    return RedirectResponse(url="/admin/servers", status_code=status.HTTP_302_FOUND)




@router.get("/api/admin/runtime-servers")
async def admin_runtime_servers_list(
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
):
    _ = user
    return list_runtime_servers_payload(store=store, law_sets_store=law_sets_store, projections_store=projections_store)


@router.post("/api/admin/runtime-servers")
async def admin_runtime_servers_create(
    payload: AdminRuntimeServerPayload,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = create_runtime_server_payload(
            store=store,
            law_sets_store=law_sets_store,
            projections_store=projections_store,
            code=payload.code,
            title=payload.title,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    row = result["item"]
    metrics_store.log_event(
        event_type="admin_runtime_server_create",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/runtime-servers",
        method="POST",
        status_code=200,
        meta={"code": row["code"]},
    )
    return _admin_ok(**result)


@router.put("/api/admin/runtime-servers/{server_code}")
async def admin_runtime_servers_update(
    server_code: str,
    payload: AdminRuntimeServerPayload,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    normalized_code = _normalize_code(server_code)
    if normalized_code != payload.code:
        _raise_bad_request("server_code_mismatch")
    try:
        result = update_runtime_server_payload(
            store=store,
            law_sets_store=law_sets_store,
            projections_store=projections_store,
            code=normalized_code,
            title=payload.title,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    row = result["item"]
    metrics_store.log_event(
        event_type="admin_runtime_server_update",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/runtime-servers/{normalized_code}",
        method="PUT",
        status_code=200,
        meta={"code": row["code"]},
    )
    return _admin_ok(**result)


@router.post("/api/admin/runtime-servers/{server_code}/activate")
async def admin_runtime_servers_activate(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    normalized_code = _normalize_code(server_code)
    try:
        result = set_runtime_server_active_payload(
            store=store,
            law_sets_store=law_sets_store,
            projections_store=projections_store,
            code=normalized_code,
            is_active=True,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    row = result["item"]
    metrics_store.log_event(
        event_type="admin_runtime_server_activate",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/activate",
        method="POST",
        status_code=200,
        meta={"code": row["code"]},
    )
    return _admin_ok(**result)


@router.get("/api/admin/runtime-servers/{server_code}/health")
async def admin_runtime_server_health(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    normalized_code = _normalize_code(server_code)
    payload = build_runtime_server_health_payload(
        server_code=normalized_code,
        runtime_servers_store=store,
        law_sets_store=law_sets_store,
        projections_store=projections_store,
    )
    if not payload["checks"]["server"]["ok"]:
        _raise_not_found("server_not_found")
    metrics_store.log_event(
        event_type="admin_runtime_server_health",
        username=user.username,
        server_code=normalized_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/health",
        method="GET",
        status_code=200,
        meta=payload.get("summary") or {},
    )
    return payload


@router.get("/api/admin/runtime-servers/{server_code}/workspace")
async def admin_runtime_server_workspace(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    runtime_servers_store: RuntimeServersStore = Depends(get_runtime_servers_store),
    law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    source_sets_store: LawSourceSetsStore = Depends(get_law_source_sets_store),
):
    try:
        payload = build_server_workspace_payload(
            server_code=server_code,
            runtime_servers_store=runtime_servers_store,
            law_sets_store=law_sets_store,
            projections_store=projections_store,
            workflow_service=workflow_service,
            dashboard_service=dashboard_service,
            metrics_store=metrics_store,
            user_store=user_store,
            source_sets_store=source_sets_store,
            username=user.username,
        )
    except KeyError as exc:
        _raise_not_found(exc)
    return _admin_ok(**payload)


@router.get("/api/admin/runtime-servers/{server_code}/activity")
async def admin_runtime_server_activity(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
):
    payload = build_server_activity_payload(
        server_code=server_code,
        metrics_store=metrics_store,
        dashboard_service=dashboard_service,
        username=user.username,
    )
    return _admin_ok(**payload)


@router.get("/api/admin/runtime-servers/{server_code}/features")
async def admin_runtime_server_features(
    server_code: str,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    _ = user
    return _admin_ok(
        **list_server_features_payload(
            workflow_service=workflow_service,
            server_code=server_code,
        )
    )


@router.post("/api/admin/runtime-servers/{server_code}/features")
async def admin_runtime_server_features_create(
    server_code: str,
    payload: AdminCatalogItemPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = save_server_feature_override_payload(
            workflow_service=workflow_service,
            server_code=server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            payload=payload,
        )
    except (ValueError, PermissionError) as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_server_feature_create",
        username=user.username,
        server_code=_normalize_code(server_code),
        path=f"/api/admin/runtime-servers/{_normalize_code(server_code)}/features",
        method="POST",
        status_code=200,
        meta={"content_key": payload.key or payload.feature_flag},
    )
    return _admin_ok(**result)


@router.put("/api/admin/runtime-servers/{server_code}/features/{feature_key}")
async def admin_runtime_server_features_update(
    server_code: str,
    feature_key: str,
    payload: AdminCatalogItemPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = save_server_feature_override_payload(
            workflow_service=workflow_service,
            server_code=server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            payload=payload,
            feature_key=feature_key,
        )
    except (ValueError, PermissionError) as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_server_feature_update",
        username=user.username,
        server_code=_normalize_code(server_code),
        path=f"/api/admin/runtime-servers/{_normalize_code(server_code)}/features/{_normalize_code(feature_key)}",
        method="PUT",
        status_code=200,
        meta={"content_key": _normalize_code(feature_key)},
    )
    return _admin_ok(**result)


@router.post("/api/admin/runtime-servers/{server_code}/features/{feature_key}/workflow")
async def admin_runtime_server_features_workflow(
    server_code: str,
    feature_key: str,
    payload: AdminCatalogWorkflowPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = execute_server_content_workflow_payload(
            workflow_service=workflow_service,
            server_code=server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            content_type="features",
            content_key=feature_key,
            payload=payload,
        )
    except (ValueError, PermissionError) as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_server_feature_workflow",
        username=user.username,
        server_code=_normalize_code(server_code),
        path=f"/api/admin/runtime-servers/{_normalize_code(server_code)}/features/{_normalize_code(feature_key)}/workflow",
        method="POST",
        status_code=200,
        meta={"content_key": _normalize_code(feature_key), "action": payload.action},
    )
    return _admin_ok(**result)


@router.get("/api/admin/runtime-servers/{server_code}/templates")
async def admin_runtime_server_templates(
    server_code: str,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    _ = user
    return _admin_ok(
        **list_server_templates_payload(
            workflow_service=workflow_service,
            server_code=server_code,
        )
    )


@router.get("/api/admin/runtime-servers/{server_code}/templates/{template_key}")
async def admin_runtime_server_template_item(
    server_code: str,
    template_key: str,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    _ = user
    try:
        payload = get_server_template_item_payload(
            workflow_service=workflow_service,
            server_code=server_code,
            template_key=template_key,
        )
    except KeyError as exc:
        _raise_not_found(exc)
    return _admin_ok(**payload)


@router.post("/api/admin/runtime-servers/{server_code}/templates")
async def admin_runtime_server_templates_create(
    server_code: str,
    payload: AdminCatalogItemPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = save_server_template_override_payload(
            workflow_service=workflow_service,
            server_code=server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            payload=payload,
        )
    except (ValueError, PermissionError) as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_server_template_create",
        username=user.username,
        server_code=_normalize_code(server_code),
        path=f"/api/admin/runtime-servers/{_normalize_code(server_code)}/templates",
        method="POST",
        status_code=200,
        meta={"content_key": payload.key},
    )
    return _admin_ok(**result)


@router.put("/api/admin/runtime-servers/{server_code}/templates/{template_key}")
async def admin_runtime_server_templates_update(
    server_code: str,
    template_key: str,
    payload: AdminCatalogItemPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = save_server_template_override_payload(
            workflow_service=workflow_service,
            server_code=server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            payload=payload,
            template_key=template_key,
        )
    except (ValueError, PermissionError) as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_server_template_update",
        username=user.username,
        server_code=_normalize_code(server_code),
        path=f"/api/admin/runtime-servers/{_normalize_code(server_code)}/templates/{_normalize_code(template_key)}",
        method="PUT",
        status_code=200,
        meta={"content_key": _normalize_code(template_key)},
    )
    return _admin_ok(**result)


@router.post("/api/admin/runtime-servers/{server_code}/templates/{template_key}/workflow")
async def admin_runtime_server_templates_workflow(
    server_code: str,
    template_key: str,
    payload: AdminCatalogWorkflowPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = execute_server_content_workflow_payload(
            workflow_service=workflow_service,
            server_code=server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            content_type="templates",
            content_key=template_key,
            payload=payload,
        )
    except (ValueError, PermissionError) as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_server_template_workflow",
        username=user.username,
        server_code=_normalize_code(server_code),
        path=f"/api/admin/runtime-servers/{_normalize_code(server_code)}/templates/{_normalize_code(template_key)}/workflow",
        method="POST",
        status_code=200,
        meta={"content_key": _normalize_code(template_key), "action": payload.action},
    )
    return _admin_ok(**result)


@router.post("/api/admin/runtime-servers/{server_code}/templates/{template_key}/preview")
async def admin_runtime_server_template_preview(
    server_code: str,
    template_key: str,
    payload: AdminServerTemplatePreviewPayload,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    _ = user
    try:
        result = build_server_template_preview_payload(
            workflow_service=workflow_service,
            server_code=server_code,
            template_key=template_key,
            sample_json=payload.sample_json,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    return _admin_ok(**result)


@router.post("/api/admin/runtime-servers/{server_code}/templates/{template_key}/reset-to-default")
async def admin_runtime_server_template_reset_to_default(
    server_code: str,
    template_key: str,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = reset_server_template_to_default_payload(
            workflow_service=workflow_service,
            server_code=server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            template_key=template_key,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_server_template_reset_to_default",
        username=user.username,
        server_code=_normalize_code(server_code),
        path=f"/api/admin/runtime-servers/{_normalize_code(server_code)}/templates/{_normalize_code(template_key)}/reset-to-default",
        method="POST",
        status_code=200,
        meta={"content_key": _normalize_code(template_key)},
    )
    return _admin_ok(**result)


@router.get("/api/admin/runtime-servers/{server_code}/templates/{template_key}/placeholders")
async def admin_runtime_server_template_placeholders(
    server_code: str,
    template_key: str,
    user: AuthUser = Depends(require_admin_user),
):
    _ = user
    _ = server_code
    return _admin_ok(**build_server_template_placeholders_payload(template_key=template_key))


@router.get("/api/admin/runtime-servers/{server_code}/laws/summary")
async def admin_runtime_server_laws_summary(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    runtime_servers_store: RuntimeServersStore = Depends(get_runtime_servers_store),
    law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    source_sets_store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
):
    _ = user
    try:
        payload = build_server_laws_summary_payload(
            server_code=server_code,
            runtime_servers_store=runtime_servers_store,
            law_sets_store=law_sets_store,
            source_sets_store=source_sets_store,
            projections_store=projections_store,
            versions_store=versions_store,
        )
    except KeyError as exc:
        _raise_not_found(exc)
    return _admin_ok(**payload)


@router.get("/api/admin/runtime-servers/{server_code}/laws/effective")
async def admin_runtime_server_laws_effective(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    runtime_servers_store: RuntimeServersStore = Depends(get_runtime_servers_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
):
    _ = user
    try:
        payload = build_server_effective_laws_payload(
            server_code=server_code,
            runtime_servers_store=runtime_servers_store,
            projections_store=projections_store,
            versions_store=versions_store,
        )
    except KeyError as exc:
        _raise_not_found(exc)
    return _admin_ok(**payload)


@router.post("/api/admin/runtime-servers/{server_code}/laws/refresh-preview")
async def admin_runtime_server_laws_refresh_preview(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    runtime_servers_store: RuntimeServersStore = Depends(get_runtime_servers_store),
    source_sets_store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        payload = run_server_laws_refresh_preview_payload(
            server_code=server_code,
            runtime_servers_store=runtime_servers_store,
            source_sets_store=source_sets_store,
            projections_store=projections_store,
            versions_store=versions_store,
            trigger_mode="manual",
            safe_rerun=True,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    normalized_server = _normalize_code(server_code)
    metrics_store.log_event(
        event_type="admin_server_laws_refresh_preview",
        username=user.username,
        server_code=normalized_server,
        path=f"/api/admin/runtime-servers/{normalized_server}/laws/refresh-preview",
        method="POST",
        status_code=200,
        meta={"run_id": (payload.get("run") or {}).get("id")},
    )
    return _admin_ok(**payload)


@router.post("/api/admin/runtime-servers/{server_code}/laws/recheck")
async def admin_runtime_server_laws_recheck(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    runtime_servers_store: RuntimeServersStore = Depends(get_runtime_servers_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        payload = build_server_laws_recheck_payload(
            server_code=server_code,
            runtime_servers_store=runtime_servers_store,
            projections_store=projections_store,
            versions_store=versions_store,
        )
    except KeyError as exc:
        _raise_not_found(exc)
    normalized_server = _normalize_code(server_code)
    metrics_store.log_event(
        event_type="admin_server_laws_recheck",
        username=user.username,
        server_code=normalized_server,
        path=f"/api/admin/runtime-servers/{normalized_server}/laws/recheck",
        method="POST",
        status_code=200,
        meta={"count": (payload.get("summary") or {}).get("count")},
    )
    return _admin_ok(**payload)


@router.get("/api/admin/runtime-servers/{server_code}/laws/diff")
async def admin_runtime_server_laws_diff(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    runtime_servers_store: RuntimeServersStore = Depends(get_runtime_servers_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
):
    _ = user
    try:
        payload = build_server_laws_diff_payload(
            server_code=server_code,
            runtime_servers_store=runtime_servers_store,
            projections_store=projections_store,
        )
    except KeyError as exc:
        _raise_not_found(exc)
    return _admin_ok(**payload)


@router.post("/api/admin/runtime-servers/{server_code}/deactivate")
async def admin_runtime_servers_deactivate(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    normalized_code = _normalize_code(server_code)
    try:
        result = set_runtime_server_active_payload(
            store=store,
            law_sets_store=law_sets_store,
            projections_store=projections_store,
            code=normalized_code,
            is_active=False,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    row = result["item"]
    metrics_store.log_event(
        event_type="admin_runtime_server_deactivate",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/deactivate",
        method="POST",
        status_code=200,
        meta={"code": row["code"]},
    )
    return _admin_ok(**result)


@router.get("/api/admin/runtime-servers/{server_code}/law-sets")
async def admin_runtime_server_law_sets(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
):
    _ = user
    return list_runtime_server_law_sets_payload(store=store, server_code=server_code)


@router.get("/api/admin/runtime-servers/{server_code}/law-bindings")
async def admin_runtime_server_law_bindings(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
):
    _ = user
    return list_runtime_server_law_bindings_payload(store=store, server_code=server_code)


@router.get("/api/admin/runtime-servers/{server_code}/source-set-bindings")
async def admin_runtime_server_source_set_bindings(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    normalized_code = _normalize_code(server_code)
    try:
        payload = list_server_source_set_bindings_payload(store=store, server_code=normalized_code)
    except ValueError as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_server_source_set_bindings_list",
        username=user.username,
        server_code=normalized_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/source-set-bindings",
        method="GET",
        status_code=200,
        meta={"count": payload["count"]},
    )
    return payload


@router.get("/api/admin/law-source-sets")
async def admin_law_source_sets(
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    payload = list_source_sets_payload(store=store)
    metrics_store.log_event(
        event_type="admin_law_source_sets_list",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/law-source-sets",
        method="GET",
        status_code=200,
        meta={"count": payload["count"]},
    )
    return payload


@router.post("/api/admin/law-source-sets")
async def admin_law_source_sets_create(
    payload: AdminLawSourceSetPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = create_source_set_payload(
            store=store,
            source_set_key=payload.source_set_key,
            title=payload.title,
            description=payload.description,
            scope=payload.scope,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    item = result["item"]
    metrics_store.log_event(
        event_type="admin_law_source_set_create",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/law-source-sets",
        method="POST",
        status_code=200,
        meta={"source_set_key": item.get("source_set_key")},
    )
    return _admin_ok(**result)


@router.put("/api/admin/law-source-sets/{source_set_key}")
async def admin_law_source_sets_update(
    source_set_key: str,
    payload: AdminLawSourceSetPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    normalized_key = _normalize_code(source_set_key)
    if normalized_key != payload.source_set_key:
        _raise_bad_request("source_set_key_mismatch")
    try:
        result = update_source_set_payload(
            store=store,
            source_set_key=normalized_key,
            title=payload.title,
            description=payload.description,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    item = result["item"]
    metrics_store.log_event(
        event_type="admin_law_source_set_update",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-sets/{normalized_key}",
        method="PUT",
        status_code=200,
        meta={"source_set_key": item.get("source_set_key")},
    )
    return _admin_ok(**result)


@router.get("/api/admin/law-source-sets/{source_set_key}/revisions")
async def admin_law_source_set_revisions(
    source_set_key: str,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    try:
        payload = list_source_set_revisions_payload(store=store, source_set_key=source_set_key)
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_set_revisions_list",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-sets/{str(source_set_key or '').strip().lower()}/revisions",
        method="GET",
        status_code=200,
        meta={"count": payload["count"], "source_set_key": payload["source_set"]["source_set_key"]},
    )
    return payload


@router.post("/api/admin/law-source-sets/{source_set_key}/revisions")
async def admin_law_source_set_revisions_create(
    source_set_key: str,
    payload: AdminLawSourceSetRevisionPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    normalized_key = _normalize_code(source_set_key)
    try:
        result = create_source_set_revision_payload(
            store=store,
            source_set_key=normalized_key,
            container_urls=payload.container_urls,
            adapter_policy_json=payload.adapter_policy_json,
            metadata_json=payload.metadata_json,
            status=payload.status,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    item = result["item"]
    metrics_store.log_event(
        event_type="admin_law_source_set_revision_create",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-sets/{normalized_key}/revisions",
        method="POST",
        status_code=200,
        meta={
            "source_set_key": normalized_key,
            "revision_id": item.get("id"),
            "status": item.get("status"),
        },
    )
    return _admin_ok(**result)


@router.get("/api/admin/law-source-sets/{source_set_key}/discovery-runs")
async def admin_law_source_set_discovery_runs(
    source_set_key: str,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    source_sets_store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    discovery_store: LawSourceDiscoveryStore = Depends(get_law_source_discovery_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    try:
        payload = list_source_set_discovery_runs_payload(
            source_sets_store=source_sets_store,
            discovery_store=discovery_store,
            source_set_key=source_set_key,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_discovery_runs_list",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-sets/{str(source_set_key or '').strip().lower()}/discovery-runs",
        method="GET",
        status_code=200,
        meta={"count": payload["count"], "source_set_key": payload["source_set"]["source_set_key"]},
    )
    return payload


@router.get("/api/admin/law-source-discovery-runs/{run_id}/links")
async def admin_law_source_discovery_run_links(
    run_id: int,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    discovery_store: LawSourceDiscoveryStore = Depends(get_law_source_discovery_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    try:
        payload = list_discovery_run_links_payload(discovery_store=discovery_store, run_id=run_id)
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_discovery_run_links_list",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-discovery-runs/{int(run_id)}/links",
        method="GET",
        status_code=200,
        meta={"count": payload["count"], "run_id": int(run_id)},
    )
    return payload


@router.get("/api/admin/law-source-discovery-runs/{run_id}/documents")
async def admin_law_source_discovery_run_documents(
    run_id: int,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    discovery_store: LawSourceDiscoveryStore = Depends(get_law_source_discovery_store),
    documents_store: CanonicalLawDocumentsStore = Depends(get_canonical_law_documents_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    try:
        payload = list_discovery_run_documents_payload(
            discovery_store=discovery_store,
            documents_store=documents_store,
            run_id=run_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_discovery_run_documents_list",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-discovery-runs/{int(run_id)}/documents",
        method="GET",
        status_code=200,
        meta={"count": payload["count"], "run_id": int(run_id)},
    )
    return payload


@router.get("/api/admin/law-source-discovery-runs/{run_id}/document-versions")
async def admin_law_source_discovery_run_document_versions(
    run_id: int,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    discovery_store: LawSourceDiscoveryStore = Depends(get_law_source_discovery_store),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    try:
        payload = list_discovery_run_document_versions_payload(
            discovery_store=discovery_store,
            versions_store=versions_store,
            run_id=run_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_discovery_run_document_versions_list",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-discovery-runs/{int(run_id)}/document-versions",
        method="GET",
        status_code=200,
        meta={"count": payload["count"], "run_id": int(run_id)},
    )
    return payload


@router.get("/api/admin/canonical-law-documents/{canonical_law_document_id}/versions")
async def admin_canonical_law_document_versions(
    canonical_law_document_id: int,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    try:
        payload = list_canonical_law_document_versions_payload(
            versions_store=versions_store,
            canonical_law_document_id=canonical_law_document_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_canonical_law_document_versions_list",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/canonical-law-documents/{int(canonical_law_document_id)}/versions",
        method="GET",
        status_code=200,
        meta={"count": payload["count"], "canonical_law_document_id": int(canonical_law_document_id)},
    )
    return payload


@router.get("/api/admin/runtime-servers/{server_code}/law-projection-runs")
async def admin_runtime_server_law_projection_runs(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    payload = list_server_effective_law_projection_runs_payload(
        projections_store=projections_store,
        server_code=server_code,
    )
    metrics_store.log_event(
        event_type="admin_runtime_server_law_projection_runs_list",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/runtime-servers/{str(server_code or '').strip().lower()}/law-projection-runs",
        method="GET",
        status_code=200,
        meta={"count": payload["count"], "server_code": payload["server_code"]},
    )
    return payload


@router.get("/api/admin/law-projection-runs/{run_id}/items")
async def admin_law_projection_run_items(
    run_id: int,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    try:
        payload = list_server_effective_law_projection_items_payload(
            projections_store=projections_store,
            run_id=run_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_projection_run_items_list",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-projection-runs/{int(run_id)}/items",
        method="GET",
        status_code=200,
        meta={"count": payload["count"], "run_id": int(run_id)},
    )
    return payload


@router.get("/api/admin/law-projection-runs/{run_id}/status")
async def admin_law_projection_run_status(
    run_id: int,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    runtime_law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    try:
        run = projections_store.get_run(run_id=run_id)
        if run is None:
            raise KeyError("server_effective_law_projection_run_not_found")
        payload = get_server_effective_law_projection_status_payload(
            projections_store=projections_store,
            runtime_law_sets_store=runtime_law_sets_store,
            active_law_version=resolve_active_law_version(server_code=run.server_code),
            run_id=run_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_projection_run_status",
        username=user.username,
        server_code=str((payload.get("run") or {}).get("server_code") or user.server_code),
        path=f"/api/admin/law-projection-runs/{int(run_id)}/status",
        method="GET",
        status_code=200,
        meta={
            "run_id": int(run_id),
            "law_set_id": int((payload.get("materialization") or {}).get("law_set_id") or 0),
            "active_law_version_id": int((payload.get("active_law_version") or {}).get("id") or 0),
        },
    )
    return payload


@router.post("/api/admin/law-source-sets/{source_set_key}/discovery-runs")
async def admin_law_source_set_discovery_runs_execute(
    source_set_key: str,
    payload: AdminLawSourceDiscoveryRunPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    source_sets_store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    discovery_store: LawSourceDiscoveryStore = Depends(get_law_source_discovery_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = execute_source_set_discovery_payload(
            source_sets_store=source_sets_store,
            discovery_store=discovery_store,
            source_set_key=source_set_key,
            source_set_revision_id=payload.source_set_revision_id,
            trigger_mode=payload.trigger_mode,
            safe_rerun=payload.safe_rerun,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_discovery_run_execute",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-sets/{str(source_set_key or '').strip().lower()}/discovery-runs",
        method="POST",
        status_code=200,
        meta={
            "run_id": (result.get("run") or {}).get("id"),
            "source_set_key": (result.get("source_set") or {}).get("source_set_key"),
            "changed": bool(result.get("changed")),
        },
    )
    return result


@router.post("/api/admin/law-source-discovery-runs/{run_id}/ingest-documents")
async def admin_law_source_discovery_run_ingest_documents(
    run_id: int,
    payload: AdminCanonicalLawDocumentIngestPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    discovery_store: LawSourceDiscoveryStore = Depends(get_law_source_discovery_store),
    documents_store: CanonicalLawDocumentsStore = Depends(get_canonical_law_documents_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = ingest_discovery_run_documents_payload(
            discovery_store=discovery_store,
            documents_store=documents_store,
            run_id=run_id,
            safe_rerun=payload.safe_rerun,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_discovery_run_ingest_documents",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-discovery-runs/{int(run_id)}/ingest-documents",
        method="POST",
        status_code=200,
        meta={
            "count": result["count"],
            "run_id": int(run_id),
            "changed": bool(result.get("changed")),
            "created_documents": int(result.get("created_documents") or 0),
        },
    )
    return result


@router.post("/api/admin/law-source-discovery-runs/{run_id}/ingest-document-versions")
async def admin_law_source_discovery_run_ingest_document_versions(
    run_id: int,
    payload: AdminCanonicalLawDocumentVersionIngestPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    discovery_store: LawSourceDiscoveryStore = Depends(get_law_source_discovery_store),
    documents_store: CanonicalLawDocumentsStore = Depends(get_canonical_law_documents_store),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = ingest_discovery_run_document_versions_payload(
            discovery_store=discovery_store,
            documents_store=documents_store,
            versions_store=versions_store,
            run_id=run_id,
            safe_rerun=payload.safe_rerun,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_discovery_run_ingest_document_versions",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-discovery-runs/{int(run_id)}/ingest-document-versions",
        method="POST",
        status_code=200,
        meta={
            "count": result["count"],
            "run_id": int(run_id),
            "changed": bool(result.get("changed")),
            "created_versions": int(result.get("created_versions") or 0),
        },
    )
    return result


@router.post("/api/admin/law-source-discovery-runs/{run_id}/fetch-document-versions")
async def admin_law_source_discovery_run_fetch_document_versions(
    request: Request,
    run_id: int,
    payload: AdminCanonicalLawDocumentVersionFetchPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    discovery_store: LawSourceDiscoveryStore = Depends(get_law_source_discovery_store),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    fetcher = getattr(request.app.state, "canonical_law_document_version_fetcher", None)
    try:
        result = fetch_discovery_run_document_versions_payload(
            discovery_store=discovery_store,
            versions_store=versions_store,
            run_id=run_id,
            safe_rerun=payload.safe_rerun,
            timeout_sec=payload.timeout_sec,
            fetcher=fetcher,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_discovery_run_fetch_document_versions",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-discovery-runs/{int(run_id)}/fetch-document-versions",
        method="POST",
        status_code=200,
        meta={
            "count": result["count"],
            "run_id": int(run_id),
            "changed": bool(result.get("changed")),
            "fetched_versions": int(result.get("fetched_versions") or 0),
            "failed_versions": int(result.get("failed_versions") or 0),
        },
    )
    return result


@router.post("/api/admin/law-source-discovery-runs/{run_id}/parse-document-versions")
async def admin_law_source_discovery_run_parse_document_versions(
    run_id: int,
    payload: AdminCanonicalLawDocumentVersionParsePayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    discovery_store: LawSourceDiscoveryStore = Depends(get_law_source_discovery_store),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = parse_discovery_run_document_versions_payload(
            discovery_store=discovery_store,
            versions_store=versions_store,
            run_id=run_id,
            safe_rerun=payload.safe_rerun,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_discovery_run_parse_document_versions",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-discovery-runs/{int(run_id)}/parse-document-versions",
        method="POST",
        status_code=200,
        meta={
            "count": result["count"],
            "run_id": int(run_id),
            "changed": bool(result.get("changed")),
            "parsed_versions": int(result.get("parsed_versions") or 0),
            "failed_versions": int(result.get("failed_versions") or 0),
        },
    )
    return result


@router.post("/api/admin/runtime-servers/{server_code}/law-projection-runs")
async def admin_runtime_server_law_projection_preview(
    server_code: str,
    payload: AdminLawProjectionRunPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    source_sets_store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = preview_server_effective_law_projection_payload(
            source_sets_store=source_sets_store,
            versions_store=versions_store,
            projections_store=projections_store,
            server_code=server_code,
            trigger_mode=payload.trigger_mode,
            safe_rerun=payload.safe_rerun,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_runtime_server_law_projection_preview",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/runtime-servers/{str(server_code or '').strip().lower()}/law-projection-runs",
        method="POST",
        status_code=200,
        meta={
            "count": result["count"],
            "run_id": (result.get("run") or {}).get("id"),
            "reused_run": bool(result.get("reused_run")),
        },
    )
    return result


@router.post("/api/admin/law-projection-runs/{run_id}/approve")
async def admin_law_projection_run_approve(
    run_id: int,
    payload: AdminLawProjectionDecisionPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = decide_server_effective_law_projection_payload(
            projections_store=projections_store,
            run_id=run_id,
            status="approved",
            decided_by=user.username,
            reason=payload.reason,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_projection_run_approve",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-projection-runs/{int(run_id)}/approve",
        method="POST",
        status_code=200,
        meta={"run_id": int(run_id), "status": "approved"},
    )
    return result


@router.post("/api/admin/law-projection-runs/{run_id}/hold")
async def admin_law_projection_run_hold(
    run_id: int,
    payload: AdminLawProjectionDecisionPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = decide_server_effective_law_projection_payload(
            projections_store=projections_store,
            run_id=run_id,
            status="held",
            decided_by=user.username,
            reason=payload.reason,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_projection_run_hold",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-projection-runs/{int(run_id)}/hold",
        method="POST",
        status_code=200,
        meta={"run_id": int(run_id), "status": "held"},
    )
    return result


@router.post("/api/admin/law-projection-runs/{run_id}/materialize-law-set")
async def admin_law_projection_run_materialize_law_set(
    run_id: int,
    payload: AdminLawProjectionMaterializePayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    runtime_law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = materialize_server_effective_law_projection_payload(
            projections_store=projections_store,
            runtime_law_sets_store=runtime_law_sets_store,
            run_id=run_id,
            materialized_by=user.username,
            safe_rerun=payload.safe_rerun,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_projection_run_materialize_law_set",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-projection-runs/{int(run_id)}/materialize-law-set",
        method="POST",
        status_code=200,
        meta={
            "run_id": int(run_id),
            "changed": bool(result.get("changed")),
            "law_set_id": int((result.get("materialization") or {}).get("law_set_id") or 0),
            "item_count": int(result.get("count") or 0),
        },
    )
    return result


@router.post("/api/admin/law-projection-runs/{run_id}/activate-runtime")
async def admin_law_projection_run_activate_runtime(
    run_id: int,
    payload: AdminLawProjectionActivatePayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("publish_law_sets")),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    runtime_law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    versions_store: CanonicalLawDocumentVersionsStore = Depends(get_canonical_law_document_versions_store),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = activate_server_effective_law_projection_payload(
            projections_store=projections_store,
            runtime_law_sets_store=runtime_law_sets_store,
            versions_store=versions_store,
            law_admin_service=LawAdminService(workflow_service),
            run_id=run_id,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            activated_by=user.username,
            safe_rerun=payload.safe_rerun,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_projection_run_activate_runtime",
        username=user.username,
        server_code=str((result.get("activation") or {}).get("server_code") or user.server_code),
        path=f"/api/admin/law-projection-runs/{int(run_id)}/activate-runtime",
        method="POST",
        status_code=200,
        meta={
            "run_id": int(run_id),
            "changed": bool(result.get("changed")),
            "law_set_id": int((result.get("activation") or {}).get("law_set_id") or 0),
            "law_version_id": int((result.get("activation") or {}).get("law_version_id") or 0),
        },
    )
    return result


@router.post("/api/admin/runtime-servers/{server_code}/law-bindings")
async def admin_runtime_server_law_bindings_add(
    server_code: str,
    payload: AdminServerLawBindingPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = add_runtime_server_law_binding_payload(
            store=store,
            server_code=server_code,
            law_code=payload.law_code,
            source_id=payload.source_id,
            effective_from=payload.effective_from,
            priority=payload.priority,
            law_set_id=payload.law_set_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    normalized_code = result["server_code"]
    item = result["item"]
    metrics_store.log_event(
        event_type="admin_server_law_binding_add",
        username=user.username,
        server_code=normalized_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/law-bindings",
        method="POST",
        status_code=200,
        meta={"law_set_id": item.get("law_set_id"), "law_code": item.get("law_code")},
    )
    return _admin_ok(item=item)


@router.post("/api/admin/runtime-servers/{server_code}/source-set-bindings")
async def admin_runtime_server_source_set_bindings_add(
    server_code: str,
    payload: AdminServerSourceSetBindingPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    normalized_code = _normalize_code(server_code)
    try:
        result = create_server_source_set_binding_payload(
            store=store,
            server_code=normalized_code,
            source_set_key=payload.source_set_key,
            priority=payload.priority,
            is_active=payload.is_active,
            include_law_keys=payload.include_law_keys,
            exclude_law_keys=payload.exclude_law_keys,
            pin_policy_json=payload.pin_policy_json,
            metadata_json=payload.metadata_json,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    item = result["item"]
    metrics_store.log_event(
        event_type="admin_server_source_set_binding_add",
        username=user.username,
        server_code=normalized_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/source-set-bindings",
        method="POST",
        status_code=200,
        meta={"binding_id": item.get("id"), "source_set_key": item.get("source_set_key")},
    )
    return _admin_ok(**result)


@router.put("/api/admin/runtime-servers/{server_code}/source-set-bindings/{binding_id}")
async def admin_runtime_server_source_set_bindings_update(
    server_code: str,
    binding_id: int,
    payload: AdminServerSourceSetBindingPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    normalized_code = _normalize_code(server_code)
    try:
        result = update_server_source_set_binding_payload(
            store=store,
            server_code=normalized_code,
            binding_id=binding_id,
            source_set_key=payload.source_set_key,
            priority=payload.priority,
            is_active=payload.is_active,
            include_law_keys=payload.include_law_keys,
            exclude_law_keys=payload.exclude_law_keys,
            pin_policy_json=payload.pin_policy_json,
            metadata_json=payload.metadata_json,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    item = result["item"]
    metrics_store.log_event(
        event_type="admin_server_source_set_binding_update",
        username=user.username,
        server_code=normalized_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/source-set-bindings/{binding_id}",
        method="PUT",
        status_code=200,
        meta={"binding_id": item.get("id"), "source_set_key": item.get("source_set_key")},
    )
    return _admin_ok(**result)


@router.post("/api/admin/runtime-servers/{server_code}/law-sets")
async def admin_runtime_server_law_sets_create(
    server_code: str,
    payload: AdminLawSetPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = create_runtime_server_law_set_payload(
            store=store,
            server_code=server_code,
            name=payload.name,
            items=[item.model_dump() for item in payload.items],
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    normalized_code = result["server_code"]
    law_set = result["law_set"]
    items = result["items"]
    metrics_store.log_event(
        event_type="admin_law_set_create",
        username=user.username,
        server_code=normalized_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/law-sets",
        method="POST",
        status_code=200,
        meta={"law_set_id": law_set.get("id"), "items_count": len(items)},
    )
    return _admin_ok(law_set=law_set, items=items)


@router.put("/api/admin/law-sets/{law_set_id}")
async def admin_law_set_update(
    law_set_id: int,
    payload: AdminLawSetPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = update_law_set_payload(
            store=store,
            law_set_id=law_set_id,
            name=payload.name,
            is_active=payload.is_active,
            items=[item.model_dump() for item in payload.items],
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    law_set = result["law_set"]
    items = result["items"]
    metrics_store.log_event(
        event_type="admin_law_set_update",
        username=user.username,
        server_code=str(law_set.get("server_code") or user.server_code),
        path=f"/api/admin/law-sets/{law_set_id}",
        method="PUT",
        status_code=200,
        meta={"law_set_id": law_set_id, "items_count": len(items)},
    )
    return _admin_ok(law_set=law_set, items=items)


@router.post("/api/admin/law-sets/{law_set_id}/publish")
async def admin_law_set_publish(
    law_set_id: int,
    user: AuthUser = Depends(requires_permission("publish_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = publish_law_set_payload(store=store, law_set_id=law_set_id)
    except KeyError as exc:
        _raise_not_found(exc)
    law_set = result["law_set"]
    metrics_store.log_event(
        event_type="admin_law_set_publish",
        username=user.username,
        server_code=str(law_set.get("server_code") or user.server_code),
        path=f"/api/admin/law-sets/{law_set_id}/publish",
        method="POST",
        status_code=200,
        meta={"law_set_id": law_set_id},
    )
    return _admin_ok(law_set=law_set)


@router.post("/api/admin/law-sets/{law_set_id}/rebuild")
async def admin_law_set_rebuild(
    law_set_id: int,
    payload: AdminLawSetRebuildPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        context = resolve_law_set_rebuild_context(store=store, law_set_id=law_set_id)
    except KeyError as exc:
        _raise_not_found(exc)
    except ValueError as exc:
        _raise_bad_request(exc)
    service = LawAdminService(workflow_service)
    result = service.rebuild_index(
        server_code=context["server_code"],
        source_urls=context["source_urls"],
        actor_user_id=actor_user_id,
        request_id=getattr(request.state, "request_id", ""),
        persist_sources=True,
        dry_run=bool(payload.dry_run),
    )
    metrics_store.log_event(
        event_type="admin_law_set_rebuild",
        username=user.username,
        server_code=context["server_code"],
        path=f"/api/admin/law-sets/{law_set_id}/rebuild",
        method="POST",
        status_code=200,
        meta={"law_set_id": law_set_id, "law_version_id": result.get("law_version_id")},
    )
    return _admin_ok(
        law_set_id=law_set_id,
        server_code=context["server_code"],
        source_urls=context["source_urls"],
        result=result,
    )


@router.post("/api/admin/law-sets/{law_set_id}/rollback")
async def admin_law_set_rollback(
    law_set_id: int,
    payload: AdminLawSetRollbackPayload,
    user: AuthUser = Depends(requires_permission("publish_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        context = resolve_law_set_rollback_context(store=store, law_set_id=law_set_id)
    except KeyError as exc:
        _raise_not_found(exc)
    service = LawAdminService(workflow_service)
    try:
        result = service.rollback_active_version(
            server_code=context["server_code"],
            law_version_id=payload.law_version_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_law_set_rollback",
        username=user.username,
        server_code=context["server_code"],
        path=f"/api/admin/law-sets/{law_set_id}/rollback",
        method="POST",
        status_code=200,
        meta={"law_set_id": law_set_id, "law_version_id": payload.law_version_id},
    )
    return _admin_ok(law_set_id=law_set_id, result=result)


@router.get("/api/admin/law-source-registry")
async def admin_law_source_registry_list(
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
):
    _ = user
    return list_law_source_registry_payload(store=store)


@router.post("/api/admin/law-source-registry")
async def admin_law_source_registry_create(
    payload: AdminLawSourceRegistryPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = create_law_source_registry_payload(store=store, name=payload.name, kind=payload.kind, url=payload.url)
    except ValueError as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_law_source_registry_create",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/law-source-registry",
        method="POST",
        status_code=200,
        meta={"source_id": result["item"]["id"]},
    )
    return _admin_ok(**result)


@router.get("/api/admin/law-jobs/overview")
async def admin_law_jobs_overview(
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    admin_task_ops_service: AdminTaskOpsService = Depends(get_admin_task_ops_service),
):
    _ = user
    return build_law_jobs_overview_payload(tasks=admin_task_ops_service.load_tasks())


@router.get("/api/admin/async-jobs/overview")
async def admin_async_jobs_overview(
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    user_store: UserStore = Depends(get_user_store),
):
    _ = user
    service = _get_async_job_service(request, user_store)
    items = [
        enrich_job_status(item, subsystem="async_job")
        for item in service.list_jobs(server_id=user.server_code, limit=100)
    ]
    return build_async_jobs_overview_payload(items=items)


@router.get("/api/admin/exam-import/overview")
async def admin_exam_import_overview(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    exam_store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    payload = build_exam_import_overview_payload(exam_store=exam_store, metrics_store=metrics_store)
    return {
        "ok": True,
        "summary": payload["summary"],
        "last_sync": payload.get("last_sync"),
        "last_score": payload.get("last_score"),
        "recent_failures": list(payload.get("recent_failures") or [])[:5],
        "recent_row_failures": list(payload.get("recent_row_failures") or [])[:5],
        "failed_entries": list(payload.get("failed_entries") or [])[:5],
    }


@router.get("/api/admin/generated-documents/{document_id}/provenance", response_model=DocumentVersionProvenanceResponse)
async def admin_generated_document_provenance(
    document_id: int,
    _: AuthUser = Depends(requires_permission("view_analytics")),
    store: UserStore = Depends(get_user_store),
) -> DocumentVersionProvenanceResponse:
    bundle = require_admin_generated_document_trace_bundle(store=store, document_id=document_id)
    payload = resolve_generated_document_provenance_payload_from_bundle(store=store, bundle=bundle)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Provenance trace not found."])
    return DocumentVersionProvenanceResponse(**payload)


@router.get("/api/admin/generated-documents/recent")
async def admin_recent_generated_documents(
    limit: int = Query(default=8, ge=1, le=20),
    _: AuthUser = Depends(requires_permission("view_analytics")),
    store: UserStore = Depends(get_user_store),
):
    return {
        "items": list_admin_recent_generated_documents(store=store, limit=limit),
    }


@router.get("/api/admin/generated-documents/{document_id}/review-context")
async def admin_generated_document_review_context(
    document_id: int,
    _: AuthUser = Depends(requires_permission("view_analytics")),
    store: UserStore = Depends(get_user_store),
):
    bundle = require_admin_generated_document_trace_bundle(store=store, document_id=document_id)
    return resolve_generated_document_review_context_payload_from_bundle(store=store, bundle=bundle)


@router.put("/api/admin/law-source-registry/{source_id}")
async def admin_law_source_registry_update(
    source_id: int,
    payload: AdminLawSourceRegistryPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = update_law_source_registry_payload(
            store=store,
            source_id=source_id,
            name=payload.name,
            kind=payload.kind,
            url=payload.url,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_registry_update",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-registry/{source_id}",
        method="PUT",
        status_code=200,
        meta={"source_id": result["item"]["id"]},
    )
    return _admin_ok(**result)


def _resolve_actor_user_id(user_store: UserStore, username: str) -> int:
    actor_user_id = user_store.get_user_id(username)
    if actor_user_id is None:
        _raise_bad_request("actor_not_found")
    return int(actor_user_id)


def _resolve_law_sources_server_code(
    user: AuthUser,
    user_store: UserStore,
    requested_server_code: str = "",
) -> str:
    return resolve_law_sources_target_server_code(
        user=user,
        user_store=user_store,
        requested_server_code=requested_server_code,
    )


@router.get("/api/admin/platform-blueprint/status")
async def admin_platform_blueprint_status(user: AuthUser = Depends(require_admin_user)):
    stage = _resolve_admin_platform_stage()
    return {
        "ok": True,
        "stage": stage,
        "server_code": user.server_code,
    }


@router.get("/api/admin/catalog/audit")
async def admin_catalog_audit(
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    limit: int = Query(100, ge=1, le=500),
    entity_type: str = Query(""),
    entity_id: str = Query(""),
):
    try:
        return build_catalog_audit_payload(
            workflow_service=workflow_service,
            server_code=user.server_code,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )
    except ValueError as exc:
        _raise_admin_http_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="admin_catalog_audit_bad_request",
            message=str(exc) or "invalid_audit_filter",
        )
    except (KeyError, PermissionError) as exc:
        _raise_admin_http_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="admin_catalog_audit_not_found",
            message=str(exc) or "audit_scope_not_found",
        )


@router.get("/api/admin/catalog/{entity_type}")
async def admin_catalog_list(
    entity_type: str,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    try:
        return build_catalog_list_payload(
            workflow_service=workflow_service,
            server_code=user.server_code,
            entity_type=entity_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc


@router.get("/api/admin/catalog/{entity_type}/{item_id}")
async def admin_catalog_get_item(
    entity_type: str,
    item_id: str,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    try:
        return build_catalog_item_payload(
            workflow_service=workflow_service,
            server_code=user.server_code,
            item_id=int(item_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except (KeyError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc


@router.get("/api/admin/catalog/{entity_type}/{item_id}/versions")
async def admin_catalog_versions(
    entity_type: str,
    item_id: str,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    try:
        return build_catalog_versions_payload(
            workflow_service=workflow_service,
            server_code=user.server_code,
            item_id=int(item_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except (KeyError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc


@router.post("/api/admin/change-requests/{change_request_id}/review")
async def admin_catalog_review_action(
    change_request_id: int,
    request: Request,
    decision: str = Query("approve"),
    comment: str = Query(""),
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        return review_catalog_change_request_payload(
            workflow_service=workflow_service,
            server_code=user.server_code,
            change_request_id=change_request_id,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            decision=decision,
            comment=comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except (KeyError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc


@router.get("/api/admin/change-requests/{change_request_id}/validate")
async def admin_catalog_validate_change_request(
    change_request_id: int,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    try:
        return validate_catalog_change_request_payload(
            workflow_service=workflow_service,
            server_code=user.server_code,
            change_request_id=change_request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except (KeyError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc




@router.post("/api/admin/catalog/{entity_type}")
async def admin_catalog_create(
    entity_type: str,
    payload: AdminCatalogItemPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = create_catalog_item_payload(
            workflow_service=workflow_service,
            server_code=user.server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            entity_type=entity_type,
            payload=payload,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(event_type=f"admin_catalog_{entity_type}_create", username=user.username, server_code=user.server_code, path=f"/api/admin/catalog/{entity_type}", method="POST", status_code=200, meta={"entity_id": result['item'].get("id"), "author": user.username})
    return result


@router.put("/api/admin/catalog/{entity_type}/{item_id}")
async def admin_catalog_update(
    entity_type: str,
    item_id: str,
    payload: AdminCatalogItemPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = update_catalog_item_payload(
            workflow_service=workflow_service,
            server_code=user.server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            item_id=int(item_id),
            payload=payload,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    metrics_store.log_event(event_type=f"admin_catalog_{entity_type}_update", username=user.username, server_code=user.server_code, path=f"/api/admin/catalog/{entity_type}/{item_id}", method="PUT", status_code=200, meta={"entity_id": item_id, "author": user.username})
    return result


@router.delete("/api/admin/catalog/{entity_type}/{item_id}")
async def admin_catalog_delete(
    entity_type: str,
    item_id: str,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    metrics_store.log_event(event_type=f"admin_catalog_{entity_type}_delete_blocked", username=user.username, server_code=user.server_code, path=f"/api/admin/catalog/{entity_type}/{item_id}", method="DELETE", status_code=405, meta={"entity_id": item_id, "author": user.username})
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail=["delete_not_supported_in_versioned_workflow"])


@router.post("/api/admin/catalog/{entity_type}/{item_id}/workflow")
async def admin_catalog_workflow(
    entity_type: str,
    item_id: str,
    payload: AdminCatalogWorkflowPayload,
    request: Request,
    cr_id: int = Query(0),
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = execute_catalog_workflow_payload(
            workflow_service=workflow_service,
            server_code=user.server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            payload=payload,
            query_change_request_id=cr_id,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    metrics_store.log_event(event_type=f"admin_catalog_{entity_type}_workflow", username=user.username, server_code=user.server_code, path=f"/api/admin/catalog/{entity_type}/{item_id}/workflow", method="POST", status_code=200, meta={"entity_id": item_id, "author": user.username, "action": payload.action, "change_request_id": payload.change_request_id or cr_id})
    return result


@router.post("/api/admin/catalog/{entity_type}/{item_id}/rollback")
async def admin_catalog_rollback(
    entity_type: str,
    item_id: str,
    payload: AdminCatalogRollbackPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = rollback_catalog_payload(
            workflow_service=workflow_service,
            server_code=user.server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            payload=payload,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    metrics_store.log_event(event_type=f"admin_catalog_{entity_type}_rollback", username=user.username, server_code=user.server_code, path=f"/api/admin/catalog/{entity_type}/{item_id}/rollback", method="POST", status_code=200, meta={"entity_id": item_id, "author": user.username, "rollback_batch": payload.version})
    return result


@router.get("/api/admin/law-sources")
async def admin_law_sources_status(
    server_code: str = Query(default="", description="Runtime server code override"),
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    projections_store: ServerEffectiveLawProjectionsStore = Depends(get_server_effective_law_projections_store),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, server_code)
    metrics_store.log_event(
        event_type="admin_law_sources_status",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources",
        method="GET",
        status_code=200,
    )
    return build_law_sources_status_payload(
        workflow_service=workflow_service,
        server_code=target_server_code,
        projections_store=projections_store,
    )


@router.post("/api/admin/law-sources/sync")
async def admin_law_sources_sync(
    request: Request,
    server_code: str = Query(default="", description="Runtime server code override"),
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, server_code)
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = sync_law_sources_payload(
            workflow_service=workflow_service,
            server_code=target_server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_law_sources_sync",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/sync",
        method="POST",
        status_code=200,
        meta={"changed": bool(result.get("changed"))},
    )
    return result


@router.post("/api/admin/law-sources/backfill-source-set")
async def admin_law_sources_backfill_source_set(
    payload: AdminLawSourceSetBackfillPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    source_sets_store: LawSourceSetsStore = Depends(get_law_source_sets_store),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, payload.server_code)
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = backfill_law_sources_source_set_payload(
            workflow_service=workflow_service,
            source_sets_store=source_sets_store,
            server_code=target_server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_law_sources_backfill_source_set",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/backfill-source-set",
        method="POST",
        status_code=200,
        meta={
            "source_set_key": result.get("source_set_key"),
            "changed": bool(result.get("changed")),
            "revision_created": bool(result.get("revision_created")),
            "binding_created": bool(result.get("binding_created")),
        },
    )
    return result


@router.post("/api/admin/law-sources/rebuild")
async def admin_law_sources_rebuild(
    payload: AdminLawSourcesPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, payload.server_code)
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = rebuild_law_sources_payload(
            workflow_service=workflow_service,
            server_code=target_server_code,
            source_urls=payload.source_urls,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            persist_sources=bool(payload.persist_sources),
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_law_sources_rebuild",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/rebuild",
        method="POST",
        status_code=200,
        meta={"law_version_id": result.get("law_version_id"), "article_count": result.get("article_count")},
    )
    return result


@router.post("/api/admin/law-sources/rebuild-async")
async def admin_law_sources_rebuild_async(
    payload: AdminLawSourcesPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    admin_task_ops_service: AdminTaskOpsService = Depends(get_admin_task_ops_service),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, payload.server_code)
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    request_id = getattr(request.state, "request_id", "")
    return admin_task_ops_service.start_law_sources_rebuild_task(
        server_code=target_server_code,
        user=user,
        metrics_store=metrics_store,
        rebuild_callback=lambda: rebuild_law_sources_payload(
            workflow_service=_get_content_workflow_service_for_request(request),
            server_code=target_server_code,
            source_urls=payload.source_urls,
            actor_user_id=actor_user_id,
            request_id=request_id,
            persist_sources=bool(payload.persist_sources),
        ),
    )


@router.post("/api/admin/law-sources/save")
async def admin_law_sources_save(
    payload: AdminLawSourcesPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, payload.server_code)
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = save_law_sources_payload(
            workflow_service=workflow_service,
            server_code=target_server_code,
            source_urls=payload.source_urls,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_law_sources_save",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/save",
        method="POST",
        status_code=200,
        meta={"sources_count": len(result.get("source_urls") or [])},
    )
    return result


@router.post("/api/admin/law-sources/preview")
async def admin_law_sources_preview(
    payload: AdminLawSourcesPayload,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, payload.server_code)
    result = preview_law_sources_payload(source_urls=payload.source_urls)
    metrics_store.log_event(
        event_type="admin_law_sources_preview",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/preview",
        method="POST",
        status_code=200,
        meta={
            "accepted_count": result.get("accepted_count"),
            "invalid_count": result.get("invalid_count"),
            "duplicate_count": result.get("duplicate_count"),
        },
    )
    return result


@router.get("/api/admin/law-sources/history")
async def admin_law_sources_history(
    server_code: str = Query(default="", description="Runtime server code override"),
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    limit: int = Query(default=10, ge=1, le=100),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, server_code)
    result = list_law_sources_history_payload(
        workflow_service=workflow_service,
        server_code=target_server_code,
        limit=limit,
    )
    metrics_store.log_event(
        event_type="admin_law_sources_history",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/history",
        method="GET",
        status_code=200,
        meta={"count": result.get("count", 0), "limit": limit},
    )
    return result


@router.get("/api/admin/law-sources/dependencies")
async def admin_law_sources_dependencies(
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    result = describe_law_sources_dependencies_payload(workflow_service=workflow_service)
    metrics_store.log_event(
        event_type="admin_law_sources_dependencies",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/law-sources/dependencies",
        method="GET",
        status_code=200,
        meta={"server_count": result.get("server_count"), "source_count": result.get("source_count")},
    )
    return result


@router.get("/api/admin/law-sources/tasks/{task_id}")
async def admin_law_sources_task_status(
    task_id: str,
    server_code: str = Query(default="", description="Runtime server code override"),
    user: AuthUser = Depends(requires_permission("manage_laws")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    admin_task_ops_service: AdminTaskOpsService = Depends(get_admin_task_ops_service),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, server_code)
    payload = require_law_sources_task_status_payload(
        task_id=task_id,
        target_server_code=target_server_code,
        task_loader=admin_task_ops_service.load_task,
    )
    metrics_store.log_event(
        event_type="admin_law_sources_task_status",
        username=user.username,
        server_code=target_server_code,
        path=f"/api/admin/law-sources/tasks/{task_id}",
        method="GET",
        status_code=200,
        meta={"status": payload.get("status")},
    )
    return payload


@router.get("/api/admin/dashboard")
async def admin_dashboard_data(
    user: AuthUser = Depends(requires_permission("view_analytics")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    exam_store: ExamAnswersStore = Depends(get_exam_answers_store),
    user_store: UserStore = Depends(get_user_store),
    analytics_service: AdminAnalyticsService = Depends(get_admin_analytics_service),
):
    _ = user
    return analytics_service.build_dashboard_payload(
        metrics_store=metrics_store,
        exam_store=exam_store,
        user_store=user_store,
    )


@router.get("/api/admin/dashboard/sections/{section}")
async def admin_dashboard_section_data(
    section: str,
    user: AuthUser = Depends(requires_permission("view_analytics")),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
):
    normalized = str(section or "").strip().lower()
    try:
        payload = dashboard_service.get_section(section=normalized, username=user.username, server_id=user.server_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=[f"Unknown dashboard section: {normalized}"]) from exc
    return {"section": normalized, "data": payload}


@router.get("/api/admin/dashboard/v2")
async def admin_dashboard_v2_data(
    user: AuthUser = Depends(requires_permission("view_analytics")),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
):
    return dashboard_service.get_dashboard(username=user.username, server_id=user.server_code)


@router.get("/api/admin/ai-pipeline")
async def admin_ai_pipeline_data(
    flow: str = Query(default="", max_length=32),
    issue_type: str = Query(default="", max_length=64),
    retrieval_context_mode: str = Query(default="", max_length=64),
    guard_warning: str = Query(default="", max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthUser = Depends(requires_permission("view_analytics")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    ai_pipeline_service: AdminAiPipelineService = Depends(get_admin_ai_pipeline_service),
):
    _ = user
    try:
        return ai_pipeline_service.build_payload(
            metrics_store=metrics_store,
            flow=flow,
            issue_type=issue_type,
            retrieval_context_mode=retrieval_context_mode,
            guard_warning=guard_warning,
            limit=limit,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=[str(exc) or "Не удалось загрузить AI Pipeline: все блоки недоступны."],
        )


@router.get("/api/admin/users")
async def admin_users_data(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    user_sort: str = "complaints",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    _ = user
    return build_admin_users_payload(
        metrics_store=metrics_store,
        user_store=user_store,
        search=search,
        blocked_only=blocked_only,
        tester_only=tester_only,
        gka_only=gka_only,
        unverified_only=unverified_only,
        user_sort=user_sort,
        limit=limit,
        offset=offset,
    )


@router.get("/api/admin/users/{username}")
async def admin_user_details(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    _ = user
    return build_admin_user_details_payload(
        metrics_store=metrics_store,
        user_store=user_store,
        username=username,
    )


@router.get("/api/admin/roles")
async def admin_roles_list(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    payload = list_roles_payload(user_store=user_store)
    metrics_store.log_event(
        event_type="admin_roles_list",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/roles",
        method="GET",
        status_code=200,
        meta={"count": payload["count"]},
    )
    return payload


@router.get("/api/admin/permissions")
async def admin_permissions_list(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    payload = list_permissions_payload(user_store=user_store)
    metrics_store.log_event(
        event_type="admin_permissions_list",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/permissions",
        method="GET",
        status_code=200,
        meta={"count": payload["count"]},
    )
    return payload


@router.get("/api/admin/runtime-servers/{server_code}/access-summary")
async def admin_runtime_server_access_summary(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        payload = build_server_access_summary_payload(user_store=user_store, server_code=server_code)
    except ValueError as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_runtime_server_access_summary",
        username=user.username,
        server_code=str(server_code or "").strip().lower(),
        path=f"/api/admin/runtime-servers/{str(server_code or '').strip().lower()}/access-summary",
        method="GET",
        status_code=200,
        meta={"count": payload["count"]},
    )
    return payload


@router.get("/api/admin/users/{username}/role-assignments")
async def admin_user_role_assignments(
    username: str,
    server_code: str = Query(default=""),
    user: AuthUser = Depends(requires_permission("manage_servers")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        payload = list_user_role_assignments_payload(
            user_store=user_store,
            username=username,
            server_code=server_code,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_user_role_assignments",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{str(username or '').strip().lower()}/role-assignments",
        method="GET",
        status_code=200,
        meta={"count": payload["count"], "scope_server_code": payload["server_code"]},
    )
    return payload


@router.post("/api/admin/users/{username}/role-assignments")
async def admin_assign_user_role(
    username: str,
    payload: AdminUserRoleAssignmentPayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = assign_user_role_payload(
            user_store=user_store,
            username=username,
            role_code=payload.role_code,
            server_code=payload.server_code,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    except AuthError as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_assign_user_role",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{str(username or '').strip().lower()}/role-assignments",
        method="POST",
        status_code=200,
        meta={"role_code": payload.role_code, "scope_server_code": payload.server_code or ""},
    )
    return result


@router.post("/api/admin/users/{username}/role-assignments/{assignment_id}/revoke")
async def admin_revoke_user_role_assignment(
    username: str,
    assignment_id: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = revoke_user_role_assignment_payload(
            user_store=user_store,
            username=username,
            assignment_id=assignment_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    except AuthError as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_revoke_user_role_assignment",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{str(username or '').strip().lower()}/role-assignments/{str(assignment_id or '').strip().lower()}/revoke",
        method="POST",
        status_code=200,
        meta={"assignment_id": assignment_id},
    )
    return result


@router.get("/api/admin/role-history")
async def admin_role_history(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    limit: int = Query(default=100, ge=1, le=1000),
):
    _ = user
    return build_admin_role_history_payload(
        metrics_store=metrics_store,
        user_store=user_store,
        limit=limit,
    )


@router.get("/api/admin/overview")
async def admin_overview(
    user: AuthUser = Depends(requires_permission("view_analytics")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    exam_store: ExamAnswersStore = Depends(get_exam_answers_store),
    user_store: UserStore = Depends(get_user_store),
    analytics_service: AdminAnalyticsService = Depends(get_admin_analytics_service),
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    event_search: str = "",
    event_type: str = "",
    failed_events_only: bool = False,
    users_limit: int = 0,
    user_sort: str = "complaints",
):
    _ = user
    return analytics_service.build_overview_payload(
        metrics_store=metrics_store,
        exam_store=exam_store,
        user_store=user_store,
        search=search,
        blocked_only=blocked_only,
        tester_only=tester_only,
        gka_only=gka_only,
        unverified_only=unverified_only,
        event_search=event_search,
        event_type=event_type,
        failed_events_only=failed_events_only,
        users_limit=users_limit,
        user_sort=user_sort,
    )


@router.post("/api/admin/synthetic/run")
async def run_synthetic_suite(
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    body = await request.json()
    suite = str((body or {}).get("suite") or "").strip().lower()
    trigger = str((body or {}).get("trigger") or "manual").strip().lower() or "manual"
    app_server = getattr(getattr(request.app, "state", None), "server_config", None)
    server_code = resolve_default_server_code(
        explicit_server_code=str((body or {}).get("server_code") or ""),
        user_server_code=user.server_code,
        app_server_code=getattr(app_server, "code", ""),
    )
    if suite not in {"smoke", "nightly", "load", "fault"}:
        raise HTTPException(status_code=400, detail=["suite must be one of smoke|nightly|load|fault"])
    runner = SyntheticRunnerService(metrics_store)
    return runner.run_suite(suite=suite, server_code=server_code, trigger=trigger)


@router.get("/api/admin/performance")
async def admin_performance(
    user: AuthUser = Depends(requires_permission("view_analytics")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    analytics_service: AdminAnalyticsService = Depends(get_admin_analytics_service),
    window_minutes: int = 15,
    top_endpoints: int = 10,
):
    _ = user
    return analytics_service.build_performance_payload(
        metrics_store=metrics_store,
        window_minutes=window_minutes,
        top_endpoints=top_endpoints,
    )


@router.get("/api/admin/users.csv")
async def admin_users_csv(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    users_limit: int = 0,
    user_sort: str = "complaints",
) -> Response:
    _ = user
    content = build_admin_users_csv_content(
        metrics_store=metrics_store,
        user_store=user_store,
        search=search,
        blocked_only=blocked_only,
        tester_only=tester_only,
        gka_only=gka_only,
        unverified_only=unverified_only,
        users_limit=users_limit,
        user_sort=user_sort,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="admin-users.csv"'},
    )


@router.get("/api/admin/events.csv")
async def admin_events_csv(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    event_search: str = "",
    event_type: str = "",
    failed_events_only: bool = False,
) -> Response:
    _ = user
    content = metrics_store.export_events_csv(
        event_search=event_search,
        event_type=event_type,
        failed_events_only=failed_events_only,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="admin-events.csv"'},
    )


@router.post("/api/admin/users/{username}/verify-email")
async def admin_verify_email(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: verify_admin_user_email_payload(user_store=user_store, username=username)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_verify_email",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/verify-email",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return result


@router.post("/api/admin/users/{username}/block")
async def admin_block_user(
    username: str,
    payload: AdminBlockPayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: block_admin_user_payload(user_store=user_store, username=username, reason=payload.reason)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_block_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/block",
        method="POST",
        status_code=200,
        meta={"target_username": username, "reason": payload.reason},
    )
    return result


@router.post("/api/admin/users/{username}/unblock")
async def admin_unblock_user(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: unblock_admin_user_payload(user_store=user_store, username=username)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_unblock_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/unblock",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return result


@router.post("/api/admin/users/{username}/grant-tester")
async def admin_grant_tester(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: grant_tester_payload(user_store=user_store, username=username)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_grant_tester",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/grant-tester",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return result


@router.post("/api/admin/users/{username}/revoke-tester")
async def admin_revoke_tester(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: revoke_tester_payload(user_store=user_store, username=username)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_revoke_tester",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/revoke-tester",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return result


@router.post("/api/admin/users/{username}/grant-gka")
async def admin_grant_gka(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: grant_gka_payload(user_store=user_store, username=username)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_grant_gka",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/grant-gka",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return result


@router.post("/api/admin/users/{username}/revoke-gka")
async def admin_revoke_gka(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: revoke_gka_payload(user_store=user_store, username=username)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_revoke_gka",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/revoke-gka",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return result


@router.post("/api/admin/users/{username}/email")
async def admin_update_email(
    username: str,
    payload: AdminEmailUpdatePayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: update_admin_user_email_payload(user_store=user_store, username=username, email=payload.email)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_update_email",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/email",
        method="POST",
        status_code=200,
        meta={"target_username": username, "email": payload.email},
    )
    return result


@router.post("/api/admin/users/{username}/reset-password")
async def admin_reset_password(
    username: str,
    payload: AdminPasswordResetPayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: reset_admin_user_password_payload(user_store=user_store, username=username, password=payload.password)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_reset_password",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/reset-password",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return result


@router.post("/api/admin/users/{username}/deactivate")
async def admin_deactivate_user(
    username: str,
    payload: AdminDeactivatePayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: deactivate_admin_user_payload(user_store=user_store, username=username, reason=payload.reason)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_deactivate_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/deactivate",
        method="POST",
        status_code=200,
        meta={"target_username": username, "reason": payload.reason},
    )
    return result


@router.post("/api/admin/users/{username}/reactivate")
async def admin_reactivate_user(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: reactivate_admin_user_payload(user_store=user_store, username=username)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_reactivate_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/reactivate",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return result


@router.post("/api/admin/users/{username}/daily-quota")
async def admin_set_daily_quota(
    username: str,
    payload: AdminQuotaPayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = run_admin_user_mutation(
            lambda: set_admin_user_daily_quota_payload(
                user_store=user_store,
                username=username,
                daily_limit=payload.daily_limit,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_set_daily_quota",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/daily-quota",
        method="POST",
        status_code=200,
        meta={"target_username": username, "daily_limit": payload.daily_limit},
    )
    return result


@router.post("/api/admin/exam-import/reset-scores")
async def admin_reset_exam_scores_for_user(
    payload: AdminExamScoreResetPayload,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    exam_store: ExamAnswersStore = Depends(get_exam_answers_store),
):
    if not any([payload.full_name, payload.discord_tag, payload.passport]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Нужно указать хотя бы один фильтр: full_name, discord_tag или passport."],
        )
    reset_count = exam_store.reset_scores_for_user(
        full_name=payload.full_name,
        discord_tag=payload.discord_tag,
        passport=payload.passport,
    )
    metrics_store.log_event(
        event_type="admin_reset_exam_scores",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/exam-import/reset-scores",
        method="POST",
        status_code=200,
        meta={
            "full_name": payload.full_name,
            "discord_tag": payload.discord_tag,
            "passport": payload.passport,
            "reset_count": reset_count,
        },
    )
    return {"ok": True, "reset_count": reset_count}


@router.post("/api/admin/users/bulk-actions")
async def admin_bulk_actions(
    payload: AdminBulkActionPayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    admin_task_ops_service: AdminTaskOpsService = Depends(get_admin_task_ops_service),
):
    if payload.run_async:
        return admin_task_ops_service.start_bulk_action_task(
            payload=payload,
            user=user,
            metrics_store=metrics_store,
            user_store=user_store,
        )

    result = admin_task_ops_service.execute_bulk_action(
        payload=payload,
        user=user,
        metrics_store=metrics_store,
        user_store=user_store,
    )
    return {"ok": True, "status": "finished", "result": result}


@router.get("/api/admin/tasks/{task_id}")
async def admin_task_status(
    task_id: str,
    _: AuthUser = Depends(requires_permission("manage_servers")),
    admin_task_ops_service: AdminTaskOpsService = Depends(get_admin_task_ops_service),
):
    return admin_task_ops_service.require_task_status_payload(task_id=task_id)
