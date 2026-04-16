from __future__ import annotations

from typing import Any

from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_server_health_payload,
    normalize_runtime_server_code,
)
from ogp_web.services.admin_server_laws_workspace_service import build_server_laws_recheck_payload
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.synthetic_runner_service import SyntheticRunnerService
from ogp_web.services.admin_dashboard_service import AdminDashboardService
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.canonical_law_document_versions_store import CanonicalLawDocumentVersionsStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.runtime_servers_store import RuntimeServersStore
from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore


def build_server_audit_payload(
    *,
    server_code: str,
    workflow_service: ContentWorkflowService,
    dashboard_service: AdminDashboardService,
    metrics_store: AdminMetricsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    username: str,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    items: list[dict[str, Any]] = []
    try:
        recent_events = metrics_store.list_error_events(limit=80)
    except Exception:
        recent_events = []
    for row in recent_events:
        item = dict(row or {})
        event_server = str(item.get("server_code") or "").strip().lower()
        if event_server not in {"", normalized_server}:
            continue
        items.append(
            {
                "kind": "metric_event",
                "created_at": str(item.get("created_at") or ""),
                "title": str(item.get("event_type") or "event"),
                "description": str(item.get("path") or ""),
                "severity": "error" if int(item.get("status_code") or 0) >= 400 else "info",
            }
        )
    try:
        dashboard_payload = dashboard_service.get_dashboard(username=username, server_id=normalized_server)
    except Exception:
        dashboard_payload = {}
    for row in list((dashboard_payload.get("content") or {}).get("recent_audit_activity") or [])[:20]:
        items.append(
            {
                "kind": "workflow_audit",
                "created_at": str(row.get("created_at") or ""),
                "title": str(row.get("action") or "audit"),
                "description": f"{row.get('entity_type') or 'entity'} #{row.get('entity_id') or ''}".strip(),
                "severity": "info",
            }
        )
    try:
        trail = workflow_service.list_audit_trail(
            server_scope="server",
            server_id=normalized_server,
            limit=20,
        )
    except Exception:
        trail = []
    for row in trail or []:
        item = dict(row or {})
        items.append(
            {
                "kind": "content_audit",
                "created_at": str(item.get("created_at") or ""),
                "title": str(item.get("action") or "content_change"),
                "description": f"{item.get('entity_type') or 'entity'} #{item.get('entity_id') or ''}".strip(),
                "severity": "info",
            }
        )
    if projections_store is not None:
        try:
            runs = projections_store.list_runs(server_code=normalized_server)
        except Exception:
            runs = []
        for run in runs[:10]:
            items.append(
                {
                    "kind": "law_projection",
                    "created_at": str(getattr(run, "created_at", "") or ""),
                    "title": f"projection {str(getattr(run, 'status', 'preview') or 'preview')}",
                    "description": f"run #{int(getattr(run, 'id', 0) or 0)}",
                    "severity": "info",
                }
            )
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {
        "ok": True,
        "server_code": normalized_server,
        "items": items[:60],
        "count": len(items[:60]),
    }


def build_server_issues_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    dashboard_service: AdminDashboardService,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    username: str,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    try:
        health_payload = build_runtime_server_health_payload(
            server_code=normalized_server,
            runtime_servers_store=runtime_servers_store,
            law_sets_store=law_sets_store,
            projections_store=projections_store,
        )
    except Exception:
        bindings = law_sets_store.list_server_law_bindings(server_code=normalized_server)
        law_sets = law_sets_store.list_law_sets(server_code=normalized_server)
        active_law_set = next((item for item in law_sets if item.get("is_published")), None)
        if active_law_set is None:
            active_law_set = next((item for item in law_sets if item.get("is_active")), None)
        health_payload = {
            "checks": {
                "bindings": {
                    "ok": bool(bindings),
                    "detail": f"bindings:{len(bindings)}",
                    "count": len(bindings),
                },
                "health": {
                    "ok": False,
                    "detail": (
                        str(active_law_set.get("name") or "active_law_set_present")
                        if active_law_set
                        else "active_law_version_missing"
                    ),
                    "active_law_version_id": None,
                    "chunk_count": 0,
                },
            }
        }
    dashboard_payload = dashboard_service.get_dashboard(username=username, server_id=normalized_server)
    checks = dict(health_payload.get("checks") or {})
    items: list[dict[str, Any]] = []
    if not bool((checks.get("health") or {}).get("ok")):
        items.append(
            {
                "issue_id": "laws_runtime_health",
                "severity": "error",
                "source": "laws",
                "title": "Законы не готовы к runtime",
                "detail": str((checks.get("health") or {}).get("detail") or "active law version is missing"),
                "available_actions": [
                    {"kind": "recheck", "label": "Проверить наполнение"},
                ],
            }
        )
    if not bool((checks.get("bindings") or {}).get("ok")):
        items.append(
            {
                "issue_id": "laws_bindings_missing",
                "severity": "warn",
                "source": "laws",
                "title": "Нет привязок законов",
                "detail": str((checks.get("bindings") or {}).get("detail") or "law bindings are missing"),
                "available_actions": [],
            }
        )
    integrity = dict(dashboard_payload.get("integrity") or {})
    if str(integrity.get("status") or "") in {"warn", "critical"}:
        items.append(
            {
                "issue_id": "integrity_checks",
                "severity": "error" if str(integrity.get("status")) == "critical" else "warn",
                "source": "integrity",
                "title": "Есть проблемы целостности",
                "detail": (
                    f"orphans={int(integrity.get('orphan_broken_entities') or 0)}, "
                    f"no_snapshot={int(integrity.get('versions_without_snapshot_or_citations') or 0)}, "
                    f"artifacts={int(integrity.get('exports_without_artifact') or 0)}"
                ),
                "available_actions": [],
            }
        )
    synthetic = dict(dashboard_payload.get("synthetic") or {})
    failed_scenarios = list(synthetic.get("failed_scenarios") or [])
    if failed_scenarios:
        items.append(
            {
                "issue_id": "synthetic_failures",
                "severity": "warn" if len(failed_scenarios) < 3 else "error",
                "source": "synthetic",
                "title": "Есть падения synthetic monitoring",
                "detail": f"failed scenarios: {len(failed_scenarios)}",
                "available_actions": [
                    {"kind": "retry", "label": "Перезапустить smoke"},
                ],
            }
        )
    jobs = dict(dashboard_payload.get("jobs") or {})
    if int(jobs.get("dlq_count") or 0) > 0:
        items.append(
            {
                "issue_id": "jobs_dlq",
                "severity": "error",
                "source": "jobs",
                "title": "Есть задачи в dead-letter queue",
                "detail": f"dlq_count={int(jobs.get('dlq_count') or 0)}",
                "available_actions": [],
            }
        )
    unresolved = [item for item in items if str(item.get("severity") or "") in {"warn", "error"}]
    return {
        "ok": True,
        "server_code": normalized_server,
        "items": items,
        "count": len(items),
        "unresolved_count": len(unresolved),
        "error_count": sum(1 for item in items if item["severity"] == "error"),
        "warning_count": sum(1 for item in items if item["severity"] == "warn"),
    }


def execute_server_issue_action_payload(
    *,
    server_code: str,
    issue_id: str,
    action: str,
    runtime_servers_store: RuntimeServersStore,
    versions_store: CanonicalLawDocumentVersionsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    metrics_store: AdminMetricsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    normalized_issue = str(issue_id or "").strip().lower()
    normalized_action = str(action or "").strip().lower()
    if normalized_issue == "laws_runtime_health" and normalized_action == "recheck":
        result = build_server_laws_recheck_payload(
            server_code=normalized_server,
            runtime_servers_store=runtime_servers_store,
            projections_store=projections_store,
            versions_store=versions_store,
        )
        return {
            "ok": True,
            "issue_id": normalized_issue,
            "action": normalized_action,
            "result": result,
        }
    if normalized_issue == "synthetic_failures" and normalized_action == "retry":
        runner = SyntheticRunnerService(metrics_store)
        result = runner.run_suite(suite="smoke", server_code=normalized_server, trigger="admin_issue_retry")
        return {
            "ok": True,
            "issue_id": normalized_issue,
            "action": normalized_action,
            "result": result,
        }
    raise ValueError("unsupported_issue_action")
