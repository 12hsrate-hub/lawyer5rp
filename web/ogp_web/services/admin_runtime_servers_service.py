from __future__ import annotations

from typing import Any

from ogp_web.server_config import registry as server_config_registry
from ogp_web.server_config import effective_server_pack
from ogp_web.services.law_bundle_service import load_law_bundle_meta
from ogp_web.services.law_version_service import resolve_active_law_version
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.runtime_servers_store import RuntimeServerRecord, RuntimeServersStore
from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore

ONBOARDING_STATES = (
    "bootstrap-ready",
    "workflow-ready",
    "rollout-ready",
    "production-ready",
)

_RESOLUTION_MODE_LABELS = {
    "published_pack": "published pack",
    "bootstrap_pack": "bootstrap pack",
    "neutral_fallback": "neutral fallback",
}


def normalize_runtime_server_code(value: str) -> str:
    return str(value or "").strip().lower()


def _pack_resolution_mode(pack: dict[str, Any], metadata: dict[str, Any]) -> str:
    if pack.get("id") is not None:
        return "published_pack"
    if metadata:
        return "bootstrap_pack"
    return "neutral_fallback"


def _next_required_state(highest_completed_state: str) -> str:
    if highest_completed_state not in ONBOARDING_STATES:
        return ONBOARDING_STATES[0]
    index = ONBOARDING_STATES.index(highest_completed_state)
    if index >= len(ONBOARDING_STATES) - 1:
        return ""
    return ONBOARDING_STATES[index + 1]


def _build_state_entry(*, ok: bool, detail: str) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "detail": str(detail or "").strip(),
    }


def _build_projection_bridge_summary(
    *,
    server_code: str,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    active_law_version: Any | None,
) -> dict[str, Any] | None:
    if projections_store is None:
        return None
    runs = projections_store.list_runs(server_code=server_code)
    if not runs:
        return None
    active_version_id = int(active_law_version.id) if active_law_version else 0
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


def _build_runtime_server_onboarding_payload(
    *,
    server: RuntimeServerRecord | None,
    resolution_mode: str,
    runtime_config: Any | None,
    pack_metadata: dict[str, Any],
    active_law_set: dict[str, Any] | None,
    bindings: list[dict[str, Any]],
    smoke_tests_passed: bool,
    smoke_tests_checked: bool,
) -> dict[str, Any]:
    resolution_label = _RESOLUTION_MODE_LABELS.get(resolution_mode, resolution_mode.replace("_", " "))
    rollback_reference = (
        f"/api/admin/runtime-servers/{server.code}/deactivate"
        if server
        else "/api/admin/runtime-servers/{server_code}/deactivate"
    )
    identity_defined = bool(runtime_config) and bool(
        tuple(getattr(runtime_config, "organizations", ()) or ())
        or tuple(getattr(runtime_config, "procedure_types", ()) or ())
        or frozenset(getattr(runtime_config, "enabled_pages", frozenset()) or frozenset())
    )
    law_sources_defined = bool(
        tuple(getattr(runtime_config, "law_qa_sources", ()) or ())
        or str(getattr(runtime_config, "law_qa_bundle_path", "") or "").strip()
        or active_law_set
    )
    law_set_defined = bool(active_law_set)
    bindings_defined = bool(bindings)
    template_bindings_defined = bool(dict(getattr(runtime_config, "template_bindings", {}) or {}))
    validation_profiles_defined = bool(dict(getattr(runtime_config, "validation_profiles", {}) or {}))
    feature_flags_defined = bool(frozenset(getattr(runtime_config, "feature_flags", frozenset()) or frozenset()))
    admin_visibility_defined = bool(server)

    bootstrap_ok = bool(server) and identity_defined
    if not server:
        bootstrap_detail = "runtime server record is missing"
    elif not identity_defined:
        bootstrap_detail = f"server resolves through {resolution_label}, but identity/capabilities are still undefined"
    else:
        bootstrap_detail = f"server identity and capabilities resolve through {resolution_label}"

    workflow_missing: list[str] = []
    if not law_sources_defined:
        workflow_missing.append("law source configuration")
    if not law_set_defined:
        workflow_missing.append("law set")
    if not bindings_defined:
        workflow_missing.append("law bindings")
    if not template_bindings_defined:
        workflow_missing.append("template bindings")
    if not validation_profiles_defined:
        workflow_missing.append("validation rules")
    workflow_ok = bootstrap_ok and not workflow_missing
    workflow_detail = (
        "law sources, bindings, templates, and validation rules are defined"
        if workflow_ok
        else f"missing: {', '.join(workflow_missing)}"
    )

    rollout_missing: list[str] = []
    if not feature_flags_defined:
        rollout_missing.append("feature flags / rollout defaults")
    if not admin_visibility_defined:
        rollout_missing.append("admin visibility")
    if smoke_tests_checked and not smoke_tests_passed:
        rollout_missing.append("smoke verification")
    if not smoke_tests_checked:
        rollout_missing.append("health-backed smoke verification")
    rollout_ok = workflow_ok and not rollout_missing
    rollout_detail = (
        "workflow-ready, feature flags are defined, and health-backed smoke verification passed"
        if rollout_ok
        else f"missing: {', '.join(rollout_missing)}"
    )

    production_ok = False
    production_detail = "docs/rollback validation evidence is not tracked automatically yet; manual review is still required"

    states = {
        "bootstrap-ready": _build_state_entry(ok=bootstrap_ok, detail=bootstrap_detail),
        "workflow-ready": _build_state_entry(ok=workflow_ok, detail=workflow_detail),
        "rollout-ready": _build_state_entry(ok=rollout_ok, detail=rollout_detail),
        "production-ready": _build_state_entry(ok=production_ok, detail=production_detail),
    }

    highest_completed_state = "not-ready"
    for state_code in ONBOARDING_STATES:
        if states[state_code]["ok"]:
            highest_completed_state = state_code

    return {
        "highest_completed_state": highest_completed_state,
        "next_required_state": _next_required_state(highest_completed_state),
        "resolution_mode": resolution_mode,
        "resolution_label": resolution_label,
        "uses_transitional_fallback": resolution_mode != "published_pack",
        "rollback_reference": rollback_reference,
        "smoke_tests_checked": smoke_tests_checked,
        "states": states,
    }


def _collect_runtime_server_context(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    server: RuntimeServerRecord | None = None,
    include_health: bool = True,
) -> dict[str, Any]:
    normalized_code = normalize_runtime_server_code(server_code)
    server_row = server if server is not None else runtime_servers_store.get_server(code=normalized_code)
    law_sets = law_sets_store.list_law_sets(server_code=normalized_code)
    active_law_set = next((item for item in law_sets if item.get("is_published")), None)
    if active_law_set is None:
        active_law_set = next((item for item in law_sets if item.get("is_active")), None)
    bindings = law_sets_store.list_server_law_bindings(server_code=normalized_code)
    active_law_version = resolve_active_law_version(server_code=normalized_code) if include_health else None
    bundle_meta = load_law_bundle_meta(normalized_code) if include_health else None
    chunk_count = int(
        (bundle_meta.chunk_count if bundle_meta and bundle_meta.chunk_count is not None else None)
        or (active_law_version.chunk_count if active_law_version and active_law_version.chunk_count is not None else 0)
        or 0
    )
    pack = effective_server_pack(normalized_code)
    pack_metadata = dict(pack.get("metadata") or {}) if isinstance(pack, dict) else {}
    resolution_mode = _pack_resolution_mode(pack if isinstance(pack, dict) else {}, pack_metadata)
    base_config = server_config_registry._BASE_SERVER_CONFIGS.get(normalized_code)
    runtime_config = server_config_registry._build_server_config_from_pack_or_base(
        code=normalized_code,
        title=str(server_row.title if server_row else normalized_code),
        base_config=base_config,
    )
    return {
        "server_code": normalized_code,
        "server": server_row,
        "law_sets": law_sets,
        "active_law_set": active_law_set,
        "bindings": bindings,
        "active_law_version": active_law_version,
        "bundle_meta": bundle_meta,
        "chunk_count": chunk_count,
        "pack": pack,
        "pack_metadata": pack_metadata,
        "resolution_mode": resolution_mode,
        "runtime_config": runtime_config,
    }


def _build_runtime_server_item_payload(
    *,
    record: RuntimeServerRecord,
    law_sets_store: RuntimeLawSetsStore,
    store: RuntimeServersStore,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
) -> dict[str, Any]:
    payload = store.to_payload(record)
    context = _collect_runtime_server_context(
        server_code=record.code,
        runtime_servers_store=store,
        law_sets_store=law_sets_store,
        server=record,
        include_health=False,
    )
    payload["onboarding"] = _build_runtime_server_onboarding_payload(
        server=record,
        resolution_mode=context["resolution_mode"],
        runtime_config=context["runtime_config"],
        pack_metadata=context["pack_metadata"],
        active_law_set=context["active_law_set"],
        bindings=context["bindings"],
        smoke_tests_passed=False,
        smoke_tests_checked=False,
    )
    payload["projection_bridge"] = _build_projection_bridge_summary(
        server_code=record.code,
        projections_store=projections_store,
        active_law_version=context["active_law_version"],
    )
    return payload


def list_runtime_servers_payload(
    *,
    store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
) -> dict[str, Any]:
    items = [
        _build_runtime_server_item_payload(
            record=record,
            law_sets_store=law_sets_store,
            store=store,
            projections_store=projections_store,
        )
        for record in store.list_servers()
    ]
    return {"items": items, "count": len(items)}


def create_runtime_server_payload(
    *,
    store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
    code: str,
    title: str,
) -> dict[str, Any]:
    row = store.create_server(code=code, title=title)
    return {
        "item": _build_runtime_server_item_payload(
            record=row,
            law_sets_store=law_sets_store,
            store=store,
            projections_store=projections_store,
        )
    }


def update_runtime_server_payload(
    *,
    store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
    code: str,
    title: str,
) -> dict[str, Any]:
    row = store.update_server(code=code, title=title)
    return {
        "item": _build_runtime_server_item_payload(
            record=row,
            law_sets_store=law_sets_store,
            store=store,
            projections_store=projections_store,
        )
    }


def set_runtime_server_active_payload(
    *,
    store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
    code: str,
    is_active: bool,
) -> dict[str, Any]:
    row = store.set_active(code=code, is_active=is_active)
    return {
        "item": _build_runtime_server_item_payload(
            record=row,
            law_sets_store=law_sets_store,
            store=store,
            projections_store=projections_store,
        )
    }


def build_runtime_server_health_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
) -> dict[str, Any]:
    context = _collect_runtime_server_context(
        server_code=server_code,
        runtime_servers_store=runtime_servers_store,
        law_sets_store=law_sets_store,
    )
    normalized_code = context["server_code"]
    server = context["server"]
    active_law_set = context["active_law_set"]
    bindings = context["bindings"]
    active_law_version = context["active_law_version"]
    chunk_count = context["chunk_count"]
    onboarding = _build_runtime_server_onboarding_payload(
        server=server,
        resolution_mode=context["resolution_mode"],
        runtime_config=context["runtime_config"],
        pack_metadata=context["pack_metadata"],
        active_law_set=active_law_set,
        bindings=bindings,
        smoke_tests_passed=bool(server and server.is_active and active_law_version and chunk_count > 0),
        smoke_tests_checked=True,
    )

    checks = {
        "server": {
            "ok": bool(server),
            "detail": f"server:{normalized_code}" if server else "server_missing",
        },
        "law_set": {
            "ok": bool(active_law_set),
            "detail": str(active_law_set.get("name") or "") if active_law_set else "law_set_missing",
            "law_set_id": int(active_law_set.get("id")) if active_law_set and active_law_set.get("id") is not None else None,
        },
        "bindings": {
            "ok": bool(bindings),
            "detail": f"bindings:{len(bindings)}",
            "count": len(bindings),
        },
        "activation": {
            "ok": bool(server and server.is_active),
            "detail": "active" if server and server.is_active else "inactive",
        },
        "health": {
            "ok": bool(active_law_version and chunk_count > 0),
            "detail": (
                f"active_law_version:{active_law_version.id}, chunks:{chunk_count}"
                if active_law_version and chunk_count > 0
                else "active_law_version_missing"
            ),
            "active_law_version_id": int(active_law_version.id) if active_law_version else None,
            "chunk_count": chunk_count,
        },
    }
    ready_count = sum(1 for item in checks.values() if item.get("ok"))
    projection_bridge = _build_projection_bridge_summary(
        server_code=normalized_code,
        projections_store=projections_store,
        active_law_version=active_law_version,
    )
    return {
        "server_code": normalized_code,
        "checks": checks,
        "onboarding": onboarding,
        "projection_bridge": projection_bridge,
        "summary": {
            "ready_count": ready_count,
            "total_count": len(checks),
            "is_ready": ready_count == len(checks),
        },
    }
