from __future__ import annotations

from typing import Any

from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_server_health_payload,
    normalize_runtime_server_code,
)
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.runtime_servers_store import RuntimeServersStore
from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore
from ogp_web.storage.user_store import UserStore
from ogp_web.services.admin_dashboard_service import AdminDashboardService


def _safe_content_items(
    workflow_service: ContentWorkflowService,
    *,
    server_scope: str,
    server_id: str | None,
    content_type: str,
) -> list[dict[str, Any]]:
    try:
        payload = workflow_service.list_content_items(
            server_scope=server_scope,
            server_id=server_id,
            content_type=content_type,
            include_legacy_fallback=False,
        )
    except Exception:
        return []
    items = payload.get("items") if isinstance(payload, dict) else []
    return [dict(item) for item in items or [] if isinstance(item, dict)]


def _build_effective_content_items(
    workflow_service: ContentWorkflowService,
    *,
    server_code: str,
    content_type: str,
) -> dict[str, Any]:
    global_items = _safe_content_items(
        workflow_service,
        server_scope="global",
        server_id=None,
        content_type=content_type,
    )
    server_items = _safe_content_items(
        workflow_service,
        server_scope="server",
        server_id=server_code,
        content_type=content_type,
    )
    effective_map: dict[str, dict[str, Any]] = {}
    for item in global_items:
        content_key = str(item.get("content_key") or item.get("title") or item.get("id") or "").strip().lower()
        if not content_key:
            continue
        effective_map[content_key] = {
            "content_key": content_key,
            "title": str(item.get("title") or content_key),
            "status": str(item.get("status") or "draft"),
            "source_scope": "global",
            "item_id": int(item.get("id") or 0) or None,
            "current_published_version_id": int(item.get("current_published_version_id") or 0) or None,
            "metadata_json": dict(item.get("metadata_json") or {}),
        }
    for item in server_items:
        content_key = str(item.get("content_key") or item.get("title") or item.get("id") or "").strip().lower()
        if not content_key:
            continue
        effective_map[content_key] = {
            "content_key": content_key,
            "title": str(item.get("title") or content_key),
            "status": str(item.get("status") or "draft"),
            "source_scope": "server",
            "item_id": int(item.get("id") or 0) or None,
            "current_published_version_id": int(item.get("current_published_version_id") or 0) or None,
            "metadata_json": dict(item.get("metadata_json") or {}),
        }
    effective_items = sorted(effective_map.values(), key=lambda item: (item["source_scope"] != "server", item["title"].lower()))
    published_count = sum(1 for item in effective_items if str(item.get("status") or "").strip().lower() == "published")
    return {
        "effective_items": effective_items,
        "counts": {
            "global": len(global_items),
            "server": len(server_items),
            "effective": len(effective_items),
            "published_effective": published_count,
        },
    }


def _filter_users_for_server(user_store: UserStore, *, server_code: str, limit: int = 200) -> list[dict[str, Any]]:
    users = user_store.list_users(limit=limit)
    items: list[dict[str, Any]] = []
    for row in users:
        item = dict(row or {})
        selected_server = str(item.get("selected_server_code") or item.get("server_code") or "").strip().lower()
        if selected_server != server_code:
            continue
        items.append(item)
    return items


def _build_access_summary(user_store: UserStore, *, server_code: str, users: list[dict[str, Any]]) -> dict[str, Any]:
    permission_totals: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    for row in users:
        username = str(row.get("username") or "").strip().lower()
        if not username:
            continue
        permission_codes = sorted(user_store.get_permission_codes(username, server_code=server_code))
        for code in permission_codes:
            permission_totals[code] = permission_totals.get(code, 0) + 1
        items.append(
            {
                "username": username,
                "display_name": str(row.get("username") or username),
                "permissions": permission_codes,
                "is_tester": bool(row.get("is_tester")),
                "is_gka": bool(row.get("is_gka")),
                "is_blocked": bool(row.get("access_blocked")),
                "is_deactivated": bool(row.get("deactivated_at")),
            }
        )
    return {
        "items": items,
        "permission_totals": [
            {"code": code, "count": count}
            for code, count in sorted(permission_totals.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def _build_recent_activity(
    *,
    metrics_store: AdminMetricsStore,
    server_code: str,
    dashboard_payload: dict[str, Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        recent_events = metrics_store.list_error_events(limit=80)
    except Exception:
        recent_events = []
    for row in recent_events:
        item = dict(row or {})
        event_server = str(item.get("server_code") or "").strip().lower()
        if event_server not in {"", server_code}:
            continue
        items.append(
            {
                "kind": "metric_event",
                "created_at": str(item.get("created_at") or ""),
                "title": str(item.get("event_type") or "event"),
                "description": str(item.get("path") or ""),
                "severity": "error" if int(item.get("status_code") or 0) >= 400 else "info",
                "meta": {
                    "status_code": int(item.get("status_code") or 0) or None,
                    "username": str(item.get("username") or ""),
                },
            }
        )
    for row in list((dashboard_payload.get("content") or {}).get("recent_audit_activity") or [])[:10]:
        items.append(
            {
                "kind": "audit_log",
                "created_at": str(row.get("created_at") or ""),
                "title": str(row.get("action") or "audit"),
                "description": f"{row.get('entity_type') or 'entity'} #{row.get('entity_id') or ''}".strip(),
                "severity": "info",
                "meta": {"entity_type": str(row.get("entity_type") or "")},
            }
        )
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items[:limit]


def _build_issues_payload(
    *,
    health_payload: dict[str, Any],
    dashboard_payload: dict[str, Any],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    checks = dict(health_payload.get("checks") or {})
    if not bool((checks.get("health") or {}).get("ok")):
        items.append(
            {
                "severity": "error",
                "source": "laws",
                "title": "Законы не готовы к runtime",
                "detail": str((checks.get("health") or {}).get("detail") or "active law version is missing"),
            }
        )
    if not bool((checks.get("bindings") or {}).get("ok")):
        items.append(
            {
                "severity": "warn",
                "source": "laws",
                "title": "Нет привязок законов",
                "detail": str((checks.get("bindings") or {}).get("detail") or "law bindings are missing"),
            }
        )
    integrity = dict(dashboard_payload.get("integrity") or {})
    if str(integrity.get("status") or "") in {"warn", "critical"}:
        items.append(
            {
                "severity": "error" if str(integrity.get("status")) == "critical" else "warn",
                "source": "integrity",
                "title": "Есть проблемы целостности",
                "detail": (
                    f"orphans={int(integrity.get('orphan_broken_entities') or 0)}, "
                    f"no_snapshot={int(integrity.get('versions_without_snapshot_or_citations') or 0)}, "
                    f"artifacts={int(integrity.get('exports_without_artifact') or 0)}"
                ),
            }
        )
    synthetic = dict(dashboard_payload.get("synthetic") or {})
    failed_scenarios = list(synthetic.get("failed_scenarios") or [])
    if failed_scenarios:
        items.append(
            {
                "severity": "warn" if len(failed_scenarios) < 3 else "error",
                "source": "synthetic",
                "title": "Есть падения synthetic monitoring",
                "detail": f"failed scenarios: {len(failed_scenarios)}",
            }
        )
    jobs = dict(dashboard_payload.get("jobs") or {})
    if int(jobs.get("dlq_count") or 0) > 0:
        items.append(
            {
                "severity": "error",
                "source": "jobs",
                "title": "Есть задачи в dead-letter queue",
                "detail": f"dlq_count={int(jobs.get('dlq_count') or 0)}",
            }
        )
    unresolved = [item for item in items if item["severity"] in {"warn", "error"}]
    return {
        "items": items,
        "unresolved_count": len(unresolved),
        "error_count": sum(1 for item in items if item["severity"] == "error"),
        "warning_count": sum(1 for item in items if item["severity"] == "warn"),
    }


def _build_readiness_payload(
    *,
    laws_ready: bool,
    features_ready: bool,
    templates_ready: bool,
    issues_payload: dict[str, Any],
) -> dict[str, Any]:
    blocks = {
        "laws": {"status": "ready" if laws_ready else "partial"},
        "features": {"status": "ready" if features_ready else "partial"},
        "templates": {"status": "ready" if templates_ready else "partial"},
    }
    if int(issues_payload.get("error_count") or 0) > 0:
        overall_status = "error"
    elif all(block["status"] == "ready" for block in blocks.values()):
        overall_status = "ready"
    elif all(block["status"] == "partial" for block in blocks.values()):
        overall_status = "not_configured"
    else:
        overall_status = "partial"
    return {
        "overall_status": overall_status,
        "blocks": blocks,
        "counters": {
            "errors": int(issues_payload.get("error_count") or 0),
            "warnings": int(issues_payload.get("warning_count") or 0),
            "pending_actions": sum(1 for block in blocks.values() if block["status"] != "ready"),
            "stale_changes": 0,
        },
    }


def build_server_workspace_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    workflow_service: ContentWorkflowService,
    dashboard_service: AdminDashboardService,
    metrics_store: AdminMetricsStore,
    user_store: UserStore,
    source_sets_store: LawSourceSetsStore,
    username: str,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    health_payload = build_runtime_server_health_payload(
        server_code=normalized_server,
        runtime_servers_store=runtime_servers_store,
        law_sets_store=law_sets_store,
        projections_store=projections_store,
    )
    dashboard_payload = dashboard_service.get_dashboard(username=username, server_id=normalized_server)
    features_payload = _build_effective_content_items(workflow_service, server_code=normalized_server, content_type="features")
    templates_payload = _build_effective_content_items(workflow_service, server_code=normalized_server, content_type="templates")
    server_users = _filter_users_for_server(user_store, server_code=normalized_server)
    access_payload = _build_access_summary(user_store, server_code=normalized_server, users=server_users)
    source_set_bindings = source_sets_store.list_bindings(server_code=normalized_server)
    projection_bridge = dict(health_payload.get("projection_bridge") or {})
    laws_summary = {
        "active_source_set_bindings": [
            {
                "id": int(item.id),
                "source_set_key": item.source_set_key,
                "priority": int(item.priority),
                "is_active": bool(item.is_active),
            }
            for item in source_set_bindings
        ],
        "binding_count": len(source_set_bindings),
        "active_law_version_id": (health_payload.get("checks") or {}).get("health", {}).get("active_law_version_id"),
        "chunk_count": (health_payload.get("checks") or {}).get("health", {}).get("chunk_count"),
        "projection_bridge": projection_bridge,
        "health": (health_payload.get("checks") or {}).get("health", {}),
    }
    issues_payload = _build_issues_payload(health_payload=health_payload, dashboard_payload=dashboard_payload)
    readiness_payload = _build_readiness_payload(
        laws_ready=bool((health_payload.get("checks") or {}).get("health", {}).get("ok")),
        features_ready=int(features_payload["counts"]["effective"]) > 0,
        templates_ready=int(templates_payload["counts"]["effective"]) > 0,
        issues_payload=issues_payload,
    )
    activity = _build_recent_activity(
        metrics_store=metrics_store,
        server_code=normalized_server,
        dashboard_payload=dashboard_payload,
    )
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    return {
        "server": runtime_servers_store.to_payload(server),
        "health": health_payload,
        "readiness": readiness_payload,
        "overview": {
            "laws": laws_summary,
            "features": {
                **features_payload["counts"],
                "items": features_payload["effective_items"][:20],
            },
            "templates": {
                **templates_payload["counts"],
                "items": templates_payload["effective_items"][:20],
            },
            "users": {
                "count": len(server_users),
                "items": server_users[:20],
            },
            "access": access_payload,
            "dashboard": dashboard_payload,
        },
        "activity": activity,
        "issues": issues_payload,
    }


def build_server_activity_payload(
    *,
    server_code: str,
    metrics_store: AdminMetricsStore,
    dashboard_service: AdminDashboardService,
    username: str,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    dashboard_payload = dashboard_service.get_dashboard(username=username, server_id=normalized_server)
    items = _build_recent_activity(
        metrics_store=metrics_store,
        server_code=normalized_server,
        dashboard_payload=dashboard_payload,
        limit=50,
    )
    return {
        "server_code": normalized_server,
        "items": items,
        "count": len(items),
    }
