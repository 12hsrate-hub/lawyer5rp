from __future__ import annotations

from typing import Any

from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_server_health_payload,
    normalize_runtime_server_code,
)
from ogp_web.services.admin_server_laws_workspace_service import (
    build_projection_bridge_readiness_summary,
    build_promotion_candidate_summary,
    build_server_laws_recheck_payload,
)
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.synthetic_runner_service import SyntheticRunnerService
from ogp_web.services.admin_dashboard_service import AdminDashboardService
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.canonical_law_document_versions_store import CanonicalLawDocumentVersionsStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.runtime_servers_store import RuntimeServersStore
from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore


def _build_runtime_provenance_issue(runtime_provenance: dict[str, Any]) -> dict[str, Any] | None:
    runtime_mode = str((runtime_provenance or {}).get("mode") or "").strip().lower()
    if runtime_mode not in {"projection_drift", "legacy_runtime_shell", "materialized_shell_only"}:
        return None
    title = {
        "projection_drift": "Runtime law shell расходится с projection bridge",
        "legacy_runtime_shell": "Runtime law shell ещё не переведён на projection-backed provenance",
        "materialized_shell_only": "Materialized law shell ещё не активирован в runtime",
    }.get(runtime_mode, "Runtime law shell требует внимания")
    return {
        "issue_id": "laws_runtime_provenance",
        "severity": "warn",
        "source": "laws",
        "title": title,
        "detail": str(
            runtime_provenance.get("detail")
            or "Current runtime law shell still depends on the compatibility promotion bridge."
        ),
        "available_actions": [
            {"kind": "recheck", "label": "Проверить наполнение"},
        ],
    }


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
    status = "aligned" if runtime_keys and projection_keys and not runtime_only and not projection_only else ("drift" if runtime_keys or projection_keys else "uninitialized")
    return {
        "status": status,
        "runtime_only_count": len(runtime_only),
        "projection_only_count": len(projection_only),
        "shared_count": len(shared),
        "runtime_only_keys": runtime_only_keys,
        "projection_only_keys": projection_only_keys,
        "runtime_only_sample": runtime_only_sample,
        "projection_only_sample": projection_only_sample,
        "drift_summary": "; ".join(drift_parts),
    }


def _build_runtime_item_parity_issue(runtime_item_parity: dict[str, Any]) -> dict[str, Any] | None:
    if str((runtime_item_parity or {}).get("status") or "").strip().lower() != "drift":
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
        "available_actions": [
            {"kind": "recheck", "label": "Проверить наполнение"},
        ],
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
        "available_actions": [
            {"kind": "recheck", "label": "Проверить наполнение"},
        ],
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
        "available_actions": [
            {"kind": "recheck", "label": "Проверить наполнение"},
        ],
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
        "available_actions": [
            {"kind": "recheck", "label": "Проверить наполнение"},
        ],
    }


def _build_promotion_candidate_issue(promotion_candidate: dict[str, Any]) -> dict[str, Any] | None:
    status = str((promotion_candidate or {}).get("status") or "").strip().lower()
    if status in {"", "ready"}:
        return None
    counts = dict((promotion_candidate or {}).get("counts") or {})
    next_step = str((promotion_candidate or {}).get("next_step") or "").strip()
    detail = str((promotion_candidate or {}).get("detail") or "").strip()
    detail = (
        f"{detail} selected={int(counts.get('selected_count') or 0)}, "
        f"changed={int(counts.get('changed') or 0)}, "
        f"missing={int(counts.get('missing_content') or 0)}, "
        f"errors={int(counts.get('error_count') or 0)}. {next_step}"
    ).strip()
    return {
        "issue_id": "laws_promotion_candidate",
        "severity": "warn",
        "source": "laws",
        "title": "Promotion candidate требует внимания",
        "detail": detail,
        "available_actions": [
            {"kind": "recheck", "label": "Проверить наполнение"},
        ],
    }


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
    onboarding = dict(health_payload.get("onboarding") or {})
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
    projection_bridge_readiness = build_projection_bridge_readiness_summary(
        binding_count=int((checks.get("bindings") or {}).get("count") or 0),
        projection_bridge_lifecycle=projection_bridge_lifecycle,
        runtime_version_parity=runtime_version_parity,
        fill_summary={},
        latest_projection_run={},
    )
    promotion_candidate = build_promotion_candidate_summary(
        diff_summary={},
        fill_summary={},
        projection_bridge_readiness=projection_bridge_readiness,
        runtime_version_parity=runtime_version_parity,
        latest_projection_run={},
    )
    items: list[dict[str, Any]] = []
    if bool(onboarding.get("requires_explicit_runtime_pack")):
        items.append(
            {
                "issue_id": "runtime_config_fallback",
                "severity": "warn",
                "source": "runtime_config",
                "title": "Сервер ещё работает через neutral fallback",
                "detail": "Опубликуйте runtime/server pack или закрепите bootstrap pack, чтобы сервер перестал зависеть от нейтрального fallback-конфига.",
                "available_actions": [],
            }
        )
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
    runtime_provenance_issue = _build_runtime_provenance_issue(runtime_provenance)
    if runtime_provenance_issue is not None:
        items.append(runtime_provenance_issue)
    runtime_item_parity_issue = _build_runtime_item_parity_issue(runtime_item_parity)
    if runtime_item_parity_issue is not None:
        items.append(runtime_item_parity_issue)
    runtime_version_parity_issue = _build_runtime_version_parity_issue(runtime_version_parity)
    if runtime_version_parity_issue is not None:
        items.append(runtime_version_parity_issue)
    projection_bridge_lifecycle_issue = _build_projection_bridge_lifecycle_issue(projection_bridge_lifecycle)
    if projection_bridge_lifecycle_issue is not None:
        items.append(projection_bridge_lifecycle_issue)
    projection_bridge_readiness_issue = _build_projection_bridge_readiness_issue(projection_bridge_readiness)
    if projection_bridge_readiness_issue is not None:
        items.append(projection_bridge_readiness_issue)
    promotion_candidate_issue = _build_promotion_candidate_issue(promotion_candidate)
    if promotion_candidate_issue is not None:
        items.append(promotion_candidate_issue)
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
    if normalized_issue in {"laws_runtime_health", "laws_runtime_provenance", "laws_runtime_item_parity", "laws_runtime_version_parity", "laws_projection_bridge_lifecycle", "laws_projection_bridge_readiness", "laws_promotion_candidate"} and normalized_action == "recheck":
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
