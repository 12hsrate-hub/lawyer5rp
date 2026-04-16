from __future__ import annotations

from typing import Any

from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_server_health_payload,
    normalize_runtime_server_code,
)
from ogp_web.services.admin_server_laws_workspace_service import build_projection_bridge_readiness_summary
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


def _build_runtime_item_parity(
    *,
    law_sets_store: RuntimeLawSetsStore,
    active_law_set_id: int | None,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    server_code: str,
) -> dict[str, Any]:
    runtime_items: list[dict[str, Any]] = []
    if active_law_set_id:
        try:
            detail = law_sets_store.get_law_set_detail(law_set_id=int(active_law_set_id))
        except Exception:
            detail = {}
        runtime_items = [dict(item) for item in list((detail or {}).get("items") or []) if isinstance(item, dict)]

    projection_items = []
    if projections_store is not None:
        try:
            runs = projections_store.list_runs(server_code=server_code)
        except Exception:
            runs = []
        current_run = runs[0] if runs else None
        if current_run is not None:
            try:
                projection_items = list(projections_store.list_items(projection_run_id=int(current_run.id)) or [])
            except Exception:
                projection_items = []

    runtime_keys = {
        str(item.get("law_code") or "").strip().lower()
        for item in runtime_items
        if str(item.get("law_code") or "").strip()
    }
    projection_keys = {
        str(getattr(item, "canonical_identity_key", "") or "").strip().lower()
        for item in projection_items
        if str(getattr(item, "canonical_identity_key", "") or "").strip()
    }
    shared = runtime_keys & projection_keys
    runtime_only = runtime_keys - projection_keys
    projection_only = projection_keys - runtime_keys
    runtime_only_keys = sorted(runtime_only)
    projection_only_keys = sorted(projection_only)
    runtime_only_sample = runtime_only_keys[:3]
    projection_only_sample = projection_only_keys[:3]
    drift_parts: list[str] = []
    if runtime_only_sample:
        drift_parts.append(f"runtime_only: {', '.join(runtime_only_sample)}")
    if projection_only_sample:
        drift_parts.append(f"projection_only: {', '.join(projection_only_sample)}")
    if runtime_keys and projection_keys and not runtime_only and not projection_only:
        status = "aligned"
        detail = "Active runtime law shell matches the latest projection by law identity."
    elif runtime_keys or projection_keys:
        status = "drift"
        detail = "Active runtime law shell and latest projection differ by law identity."
    else:
        status = "uninitialized"
        detail = "There is not enough runtime or projection data to compare law identity sets."
    return {
        "status": status,
        "detail": detail,
        "runtime_count": len(runtime_keys),
        "projection_count": len(projection_keys),
        "shared_count": len(shared),
        "runtime_only_count": len(runtime_only),
        "projection_only_count": len(projection_only),
        "runtime_only_keys": runtime_only_keys,
        "projection_only_keys": projection_only_keys,
        "runtime_only_sample": runtime_only_sample,
        "projection_only_sample": projection_only_sample,
        "drift_summary": "; ".join(drift_parts),
    }


def _build_runtime_version_parity(*, health_payload: dict[str, Any]) -> dict[str, Any]:
    runtime_alignment = dict((health_payload or {}).get("runtime_alignment") or {})
    projection_bridge = dict((health_payload or {}).get("projection_bridge") or {})
    active_law_set_id = int(runtime_alignment.get("active_law_set_id") or 0)
    active_law_version_id = int(runtime_alignment.get("active_law_version_id") or 0)
    projected_law_set_id = int(runtime_alignment.get("projected_law_set_id") or 0)
    projected_law_version_id = int(runtime_alignment.get("projected_law_version_id") or 0)
    projection_run_id = int(runtime_alignment.get("projection_run_id") or projection_bridge.get("run_id") or 0)

    if projected_law_version_id > 0 and active_law_version_id > 0 and projected_law_version_id == active_law_version_id:
        status = "aligned"
        detail = "Promoted projection law_version matches the current active runtime law_version."
    elif projected_law_version_id > 0 and active_law_version_id > 0:
        status = "drift"
        detail = "Promoted projection law_version and active runtime law_version differ."
    elif active_law_version_id > 0:
        status = "legacy_only"
        detail = "Active runtime law_version exists without a promoted projection law_version."
    elif projected_law_version_id > 0 or projected_law_set_id > 0 or projection_run_id > 0:
        status = "pending_activation"
        detail = "Promoted projection exists, but there is no active runtime law_version yet."
    else:
        status = "uninitialized"
        detail = "There is not enough runtime/projection version data to compare law_version parity."

    drift_summary = ""
    if status in {"drift", "legacy_only", "pending_activation"}:
        drift_parts: list[str] = []
        if active_law_version_id > 0:
            drift_parts.append(f"active_version={active_law_version_id}")
        if projected_law_version_id > 0:
            drift_parts.append(f"projected_version={projected_law_version_id}")
        if active_law_set_id > 0:
            drift_parts.append(f"active_law_set={active_law_set_id}")
        if projected_law_set_id > 0:
            drift_parts.append(f"projected_law_set={projected_law_set_id}")
        drift_summary = "; ".join(drift_parts)

    return {
        "status": status,
        "detail": detail,
        "active_law_set_id": active_law_set_id or None,
        "active_law_version_id": active_law_version_id or None,
        "projected_law_set_id": projected_law_set_id or None,
        "projected_law_version_id": projected_law_version_id or None,
        "projection_run_id": projection_run_id or None,
        "matches_active_law_version": (
            projected_law_version_id > 0 and active_law_version_id > 0 and projected_law_version_id == active_law_version_id
        ),
        "matches_active_law_set": (
            projected_law_set_id > 0 and active_law_set_id > 0 and projected_law_set_id == active_law_set_id
        ),
        "drift_summary": drift_summary,
    }


def _build_projection_bridge_lifecycle(*, health_payload: dict[str, Any]) -> dict[str, Any]:
    projection_bridge = dict((health_payload or {}).get("projection_bridge") or {})
    runtime_alignment = dict((health_payload or {}).get("runtime_alignment") or {})
    runtime_provenance = dict((health_payload or {}).get("runtime_provenance") or {})
    run_id = int(projection_bridge.get("run_id") or 0)
    law_set_id = int(projection_bridge.get("law_set_id") or 0)
    law_version_id = int(projection_bridge.get("law_version_id") or 0)
    matches_active = bool(projection_bridge.get("matches_active_law_version"))
    active_law_version_id = int(runtime_alignment.get("active_law_version_id") or 0)
    runtime_mode = str(runtime_provenance.get("mode") or "").strip().lower()

    if run_id <= 0:
        status = "uninitialized"
        detail = "No promoted projection lifecycle is available for this server yet."
    elif law_version_id > 0 and matches_active:
        status = "activated"
        detail = "Projection bridge is activated and matches the current runtime law_version."
    elif law_version_id > 0:
        status = "drifted"
        detail = "Projection bridge has an activation record, but it no longer matches the current runtime law_version."
    elif law_set_id > 0:
        status = "materialized"
        detail = "Projection bridge materialized a runtime law_set shell, but no active runtime law_version is aligned yet."
    else:
        status = "preview_only"
        detail = "Projection bridge currently exists only as a preview/decision run without materialization."

    if runtime_mode == "materialized_shell_only" and law_set_id > 0 and law_version_id <= 0:
        status = "materialized"
    elif runtime_mode == "projection_drift" and law_version_id > 0 and active_law_version_id > 0 and law_version_id != active_law_version_id:
        status = "drifted"

    return {
        "status": status,
        "detail": detail,
        "run_id": run_id or None,
        "law_set_id": law_set_id or None,
        "law_version_id": law_version_id or None,
        "active_law_version_id": active_law_version_id or None,
        "matches_active_law_version": matches_active if law_version_id > 0 else None,
    }


def _build_runtime_item_parity_issue(runtime_item_parity: dict[str, Any]) -> dict[str, Any] | None:
    status = str((runtime_item_parity or {}).get("status") or "").strip().lower()
    if status != "drift":
        return None
    runtime_only_count = int((runtime_item_parity or {}).get("runtime_only_count") or 0)
    projection_only_count = int((runtime_item_parity or {}).get("projection_only_count") or 0)
    drift_summary = str((runtime_item_parity or {}).get("drift_summary") or "").strip()
    detail = f"runtime_only={runtime_only_count}, projection_only={projection_only_count}."
    if drift_summary:
        detail = f"{detail} {drift_summary}."
    return {
        "issue_id": "laws_runtime_item_parity",
        "severity": "warn",
        "source": "laws",
        "title": "Состав runtime law shell расходится с latest projection",
        "detail": f"{detail} Откройте вкладку «Законы», чтобы увидеть item parity и понять, какие law identities расходятся.",
    }


def _build_runtime_version_parity_issue(runtime_version_parity: dict[str, Any]) -> dict[str, Any] | None:
    status = str((runtime_version_parity or {}).get("status") or "").strip().lower()
    if status not in {"drift", "legacy_only", "pending_activation"}:
        return None
    drift_summary = str((runtime_version_parity or {}).get("drift_summary") or "").strip()
    detail = drift_summary or str((runtime_version_parity or {}).get("detail") or "").strip()
    if not detail:
        detail = "Runtime and promoted projection law_version parity requires attention."
    return {
        "issue_id": "laws_runtime_version_parity",
        "severity": "warn",
        "source": "laws",
        "title": "Runtime law_version parity требует внимания",
        "detail": f"{detail}. Откройте вкладку «Законы», чтобы проверить version/projection parity перед дальнейшими действиями.",
    }


def _build_projection_bridge_lifecycle_issue(projection_bridge_lifecycle: dict[str, Any]) -> dict[str, Any] | None:
    status = str((projection_bridge_lifecycle or {}).get("status") or "").strip().lower()
    if status not in {"preview_only", "materialized", "drifted"}:
        return None
    return {
        "issue_id": "laws_projection_bridge_lifecycle",
        "severity": "warn",
        "source": "laws",
        "title": "Projection bridge lifecycle требует внимания",
        "detail": (
            f"{str((projection_bridge_lifecycle or {}).get('detail') or '').strip()} "
            "Это не меняет runtime автоматически, но показывает, на каком шаге bridge остановился."
        ).strip(),
    }


def _build_projection_bridge_readiness_issue(projection_bridge_readiness: dict[str, Any]) -> dict[str, Any] | None:
    status = str((projection_bridge_readiness or {}).get("status") or "").strip().lower()
    if status in {"", "ready"}:
        return None
    blockers = ", ".join(str(item) for item in list((projection_bridge_readiness or {}).get("blockers") or []) if str(item).strip())
    detail = str((projection_bridge_readiness or {}).get("detail") or "").strip()
    next_step = str((projection_bridge_readiness or {}).get("next_step") or "").strip()
    composed = detail
    if blockers:
        composed = f"{composed} blockers={blockers}."
    if next_step:
        composed = f"{composed} {next_step}".strip()
    return {
        "issue_id": "laws_projection_bridge_readiness",
        "severity": "warn",
        "source": "laws",
        "title": "Projection bridge readiness требует внимания",
        "detail": composed,
    }


def _build_issues_payload(
    *,
    health_payload: dict[str, Any],
    dashboard_payload: dict[str, Any],
    runtime_item_parity: dict[str, Any] | None = None,
    runtime_version_parity: dict[str, Any] | None = None,
    projection_bridge_lifecycle: dict[str, Any] | None = None,
    projection_bridge_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    checks = dict(health_payload.get("checks") or {})
    onboarding = dict(health_payload.get("onboarding") or {})
    runtime_provenance = dict(health_payload.get("runtime_provenance") or {})
    if bool(onboarding.get("requires_explicit_runtime_pack")):
        items.append(
            {
                "issue_id": "runtime_config_fallback",
                "severity": "warn",
                "source": "runtime_config",
                "title": "Сервер ещё работает через neutral fallback",
                "detail": "Опубликуйте runtime/server pack или закрепите bootstrap pack, чтобы сервер перестал зависеть от нейтрального fallback-конфига.",
            }
        )
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
                "issue_id": "laws_bindings_missing",
                "severity": "warn",
                "source": "laws",
                "title": "Нет привязок законов",
                "detail": str((checks.get("bindings") or {}).get("detail") or "law bindings are missing"),
            }
        )
    runtime_mode = str(runtime_provenance.get("mode") or "").strip().lower()
    if runtime_mode in {"projection_drift", "legacy_runtime_shell", "materialized_shell_only"}:
        title = {
            "projection_drift": "Runtime law shell расходится с projection bridge",
            "legacy_runtime_shell": "Runtime law shell ещё не переведён на projection-backed provenance",
            "materialized_shell_only": "Materialized law shell ещё не активирован в runtime",
        }.get(runtime_mode, "Runtime law shell требует внимания")
        items.append(
            {
                "issue_id": "laws_runtime_provenance",
                "severity": "warn",
                "source": "laws",
                "title": title,
                "detail": str(
                    runtime_provenance.get("detail")
                    or "Current runtime law shell still depends on the compatibility promotion bridge."
                ),
            }
        )
    runtime_item_parity_issue = _build_runtime_item_parity_issue(dict(runtime_item_parity or {}))
    if runtime_item_parity_issue is not None:
        items.append(runtime_item_parity_issue)
    runtime_version_parity_issue = _build_runtime_version_parity_issue(dict(runtime_version_parity or {}))
    if runtime_version_parity_issue is not None:
        items.append(runtime_version_parity_issue)
    projection_bridge_lifecycle_issue = _build_projection_bridge_lifecycle_issue(dict(projection_bridge_lifecycle or {}))
    if projection_bridge_lifecycle_issue is not None:
        items.append(projection_bridge_lifecycle_issue)
    projection_bridge_readiness_issue = _build_projection_bridge_readiness_issue(dict(projection_bridge_readiness or {}))
    if projection_bridge_readiness_issue is not None:
        items.append(projection_bridge_readiness_issue)
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
    runtime_provenance: dict[str, Any],
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
    runtime_mode = str((runtime_provenance or {}).get("mode") or "").strip().lower()
    stale_changes = 1 if runtime_mode in {"projection_drift", "legacy_runtime_shell", "materialized_shell_only"} else 0
    return {
        "overall_status": overall_status,
        "blocks": blocks,
        "counters": {
            "errors": int(issues_payload.get("error_count") or 0),
            "warnings": int(issues_payload.get("warning_count") or 0),
            "pending_actions": sum(1 for block in blocks.values() if block["status"] != "ready"),
            "stale_changes": stale_changes,
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
    runtime_provenance = dict(health_payload.get("runtime_provenance") or {})
    runtime_alignment = dict(health_payload.get("runtime_alignment") or {})
    runtime_item_parity = _build_runtime_item_parity(
        law_sets_store=law_sets_store,
        active_law_set_id=int(runtime_alignment.get("active_law_set_id") or 0) or None,
        projections_store=projections_store,
        server_code=normalized_server,
    )
    runtime_version_parity = _build_runtime_version_parity(health_payload=health_payload)
    projection_bridge_lifecycle = _build_projection_bridge_lifecycle(health_payload=health_payload)
    bridge_binding_count = len(source_set_bindings)
    if bridge_binding_count <= 0:
        bridge_binding_count = int(((health_payload.get("checks") or {}).get("bindings") or {}).get("count") or 0)
    projection_bridge_readiness = build_projection_bridge_readiness_summary(
        binding_count=bridge_binding_count,
        projection_bridge_lifecycle=projection_bridge_lifecycle,
        runtime_version_parity=runtime_version_parity,
        fill_summary={},
        latest_projection_run={},
    )
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
        "runtime_provenance": runtime_provenance,
        "runtime_alignment": runtime_alignment,
        "runtime_item_parity": runtime_item_parity,
        "runtime_version_parity": runtime_version_parity,
        "projection_bridge_lifecycle": projection_bridge_lifecycle,
        "projection_bridge_readiness": projection_bridge_readiness,
        "health": (health_payload.get("checks") or {}).get("health", {}),
    }
    issues_payload = _build_issues_payload(
        health_payload=health_payload,
        dashboard_payload=dashboard_payload,
        runtime_item_parity=runtime_item_parity,
        runtime_version_parity=runtime_version_parity,
        projection_bridge_lifecycle=projection_bridge_lifecycle,
        projection_bridge_readiness=projection_bridge_readiness,
    )
    readiness_payload = _build_readiness_payload(
        laws_ready=bool((health_payload.get("checks") or {}).get("health", {}).get("ok")),
        features_ready=int(features_payload["counts"]["effective"]) > 0,
        templates_ready=int(templates_payload["counts"]["effective"]) > 0,
        issues_payload=issues_payload,
        runtime_provenance=runtime_provenance,
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
