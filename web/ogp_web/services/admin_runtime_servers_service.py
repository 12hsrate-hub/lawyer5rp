from __future__ import annotations

from typing import Any

from ogp_web.server_config import build_runtime_resolution_snapshot
from ogp_web.services.law_bundle_service import load_law_bundle_meta
from ogp_web.services.law_version_service import resolve_active_law_version
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.runtime_servers_store import RuntimeServerRecord, RuntimeServersStore
from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore

ONBOARDING_STATES = (
    "bootstrap-ready",
    "workflow-ready",
    "rollout-ready",
    "production-ready",
)

def normalize_runtime_server_code(value: str) -> str:
    return str(value or "").strip().lower()


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


def _build_runtime_laws_provenance_summary(
    *,
    active_law_set: dict[str, Any] | None,
    active_law_version: Any | None,
    projection_bridge: dict[str, Any] | None,
    bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    active_law_set_id = int(active_law_set.get("id") or 0) if active_law_set else 0
    active_law_version_id = int(active_law_version.id) if active_law_version else 0
    projection_run_id = int((projection_bridge or {}).get("run_id") or 0)
    projected_law_set_id = int((projection_bridge or {}).get("law_set_id") or 0)
    projected_law_version_id = int((projection_bridge or {}).get("law_version_id") or 0)
    matches_active = bool((projection_bridge or {}).get("matches_active_law_version"))
    binding_count = len(bindings or [])

    if matches_active and projection_run_id > 0:
        mode = "projection_backed"
        detail = "Current active runtime law_version is explained by a promoted projection run."
        shell_role = "projection_backed_runtime"
        shell_stage = "activated"
    elif projection_run_id > 0 and projected_law_version_id > 0 and active_law_version_id > 0:
        mode = "projection_drift"
        detail = "Projection activation exists, but it no longer matches the current active runtime law_version."
        shell_role = "runtime_shell_artifact"
        shell_stage = "drifted"
    elif active_law_version_id > 0:
        mode = "legacy_runtime_shell"
        detail = "Active runtime law_version shell exists, but no promoted projection currently explains it."
        shell_role = "runtime_shell_artifact"
        shell_stage = "active_without_projection"
    elif active_law_set_id > 0:
        mode = "materialized_shell_only"
        detail = "A runtime law_set shell exists, but there is no active runtime law_version yet."
        shell_role = "runtime_shell_artifact"
        shell_stage = "materialized_only"
    else:
        mode = "uninitialized"
        detail = "No runtime law shell is active yet."
        shell_role = "no_runtime_shell"
        shell_stage = "missing"

    return {
        "mode": mode,
        "detail": detail,
        "is_projection_backed": mode == "projection_backed",
        "projection_run_id": projection_run_id or None,
        "projected_law_set_id": projected_law_set_id or None,
        "projected_law_version_id": projected_law_version_id or None,
        "active_law_set_id": active_law_set_id or None,
        "active_law_version_id": active_law_version_id or None,
        "binding_count": int(binding_count),
        "law_set_observational_only": True,
        "runtime_shell_artifact_present": bool(active_law_set_id or active_law_version_id),
        "shell_role": shell_role,
        "shell_stage": shell_stage,
    }


def _build_runtime_alignment_summary(
    *,
    active_law_set: dict[str, Any] | None,
    active_law_version: Any | None,
    projection_bridge: dict[str, Any] | None,
) -> dict[str, Any]:
    active_law_set_id = int(active_law_set.get("id") or 0) if active_law_set else 0
    active_law_version_id = int(active_law_version.id) if active_law_version else 0
    projected_law_set_id = int((projection_bridge or {}).get("law_set_id") or 0)
    projected_law_version_id = int((projection_bridge or {}).get("law_version_id") or 0)
    projection_run_id = int((projection_bridge or {}).get("run_id") or 0)
    matches_active_law_version = bool((projection_bridge or {}).get("matches_active_law_version"))
    matches_active_law_set = (
        active_law_set_id > 0 and projected_law_set_id > 0 and active_law_set_id == projected_law_set_id
    )

    if projection_run_id > 0 and matches_active_law_version:
        status = "aligned"
        detail = "Promoted projection matches the current active runtime law_version."
        shell_role = "projection_backed_runtime"
        shell_stage = "activated"
    elif projection_run_id > 0 and active_law_version_id > 0 and (projected_law_version_id > 0 or projected_law_set_id > 0):
        status = "drift"
        detail = "Promoted projection exists, but the active runtime shell no longer matches it exactly."
        shell_role = "runtime_shell_artifact"
        shell_stage = "drifted"
    elif active_law_version_id > 0:
        status = "legacy_only"
        detail = "Active runtime law_version shell exists without an aligned promoted projection."
        shell_role = "runtime_shell_artifact"
        shell_stage = "active_without_projection"
    elif active_law_set_id > 0:
        status = "pending_activation"
        detail = "Runtime law_set shell exists, but there is no active runtime law_version yet."
        shell_role = "runtime_shell_artifact"
        shell_stage = "materialized_only"
    else:
        status = "uninitialized"
        detail = "Runtime alignment cannot be checked before a runtime shell exists."
        shell_role = "no_runtime_shell"
        shell_stage = "missing"

    return {
        "status": status,
        "detail": detail,
        "projection_run_id": projection_run_id or None,
        "projected_law_set_id": projected_law_set_id or None,
        "projected_law_version_id": projected_law_version_id or None,
        "active_law_set_id": active_law_set_id or None,
        "active_law_version_id": active_law_version_id or None,
        "matches_active_law_set": matches_active_law_set if projected_law_set_id > 0 else None,
        "matches_active_law_version": matches_active_law_version if projected_law_version_id > 0 else None,
        "law_set_observational_only": True,
        "runtime_shell_artifact_present": bool(active_law_set_id or active_law_version_id),
        "shell_role": shell_role,
        "shell_stage": shell_stage,
    }


def _build_runtime_server_onboarding_payload(
    *,
    server: RuntimeServerRecord | None,
    resolution: dict[str, Any],
    source_set_bindings: list[dict[str, Any]] | None,
    runtime_bindings: list[dict[str, Any]] | None,
    binding_source: str,
    smoke_tests_passed: bool,
    smoke_tests_checked: bool,
) -> dict[str, Any]:
    resolution_mode = str(resolution.get("resolution_mode") or "neutral_fallback")
    resolution_label = str(resolution.get("resolution_label") or resolution_mode.replace("_", " "))
    runtime_config = resolution.get("runtime_config")
    requires_explicit_runtime_pack = bool(resolution.get("requires_explicit_runtime_pack"))
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
    )
    canonical_bindings_defined = bool(source_set_bindings)
    runtime_bindings_defined = bool(runtime_bindings)
    template_bindings_defined = bool(dict(getattr(runtime_config, "template_bindings", {}) or {}))
    validation_profiles_defined = bool(dict(getattr(runtime_config, "validation_profiles", {}) or {}))
    feature_flags_defined = bool(frozenset(getattr(runtime_config, "feature_flags", frozenset()) or frozenset()))
    admin_visibility_defined = bool(server)

    bootstrap_ok = bool(server) and identity_defined and not requires_explicit_runtime_pack
    if not server:
        bootstrap_detail = "runtime server record is missing"
    elif requires_explicit_runtime_pack:
        bootstrap_detail = (
            "server currently resolves through neutral fallback; publish or attach a bootstrap/runtime pack "
            "before treating it as onboarding-ready"
        )
    elif not identity_defined:
        bootstrap_detail = f"server resolves through {resolution_label}, but identity/capabilities are still undefined"
    else:
        bootstrap_detail = f"server identity and capabilities resolve through {resolution_label}"

    workflow_missing: list[str] = []
    if requires_explicit_runtime_pack:
        workflow_missing.append("published/bootstrap runtime pack")
    if not law_sources_defined:
        workflow_missing.append("law source configuration")
    if not canonical_bindings_defined:
        workflow_missing.append("canonical source-set bindings")
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
        "uses_transitional_fallback": bool(resolution.get("uses_transitional_fallback")),
        "requires_explicit_runtime_pack": requires_explicit_runtime_pack,
        "rollback_reference": rollback_reference,
        "smoke_tests_checked": smoke_tests_checked,
        "resolution": {
            "is_runtime_addressable": bool(resolution.get("is_runtime_addressable")),
            "has_published_pack": bool(resolution.get("has_published_pack")),
            "has_bootstrap_pack": bool(resolution.get("has_bootstrap_pack")),
            "has_runtime_metadata": bool(resolution.get("has_runtime_metadata")),
            "has_identity_capabilities": bool(resolution.get("has_identity_capabilities")),
        },
        "states": states,
        "binding_source": str(binding_source or "runtime_bindings"),
        "canonical_binding_ready": canonical_bindings_defined,
        "source_set_binding_count": len(source_set_bindings or []),
        "runtime_binding_count": len(runtime_bindings or []),
        "uses_runtime_bindings_fallback": bool(runtime_bindings_defined and not canonical_bindings_defined),
    }


def _collect_runtime_server_context(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore | None = None,
    server: RuntimeServerRecord | None = None,
    include_health: bool = True,
) -> dict[str, Any]:
    normalized_code = normalize_runtime_server_code(server_code)
    server_row = server if server is not None else runtime_servers_store.get_server(code=normalized_code)
    law_sets = law_sets_store.list_law_sets(server_code=normalized_code)
    active_law_set = next((item for item in law_sets if item.get("is_published")), None)
    if active_law_set is None:
        active_law_set = next((item for item in law_sets if item.get("is_active")), None)
    runtime_bindings = law_sets_store.list_server_law_bindings(server_code=normalized_code)
    source_set_bindings = list(source_sets_store.list_bindings(server_code=normalized_code)) if source_sets_store is not None else []
    bindings = source_set_bindings
    binding_source = "source_set_bindings" if source_set_bindings else "runtime_bindings"
    if include_health:
        try:
            active_law_version = resolve_active_law_version(server_code=normalized_code)
        except Exception:
            active_law_version = None
    else:
        active_law_version = None
    if include_health:
        try:
            bundle_meta = load_law_bundle_meta(normalized_code)
        except Exception:
            bundle_meta = None
    else:
        bundle_meta = None
    chunk_count = int(
        (bundle_meta.chunk_count if bundle_meta and bundle_meta.chunk_count is not None else None)
        or (active_law_version.chunk_count if active_law_version and active_law_version.chunk_count is not None else 0)
        or 0
    )
    resolution = build_runtime_resolution_snapshot(
        server_code=normalized_code,
        title=str(server_row.title if server_row else normalized_code),
    )
    return {
        "server_code": normalized_code,
        "server": server_row,
        "law_sets": law_sets,
        "active_law_set": active_law_set,
        "bindings": bindings,
        "runtime_bindings": runtime_bindings,
        "source_set_bindings": source_set_bindings,
        "binding_source": binding_source,
        "active_law_version": active_law_version,
        "bundle_meta": bundle_meta,
        "chunk_count": chunk_count,
        "resolution": resolution,
        "pack": dict(resolution.get("pack") or {}),
        "pack_metadata": dict(resolution.get("pack_metadata") or {}),
        "resolution_mode": str(resolution.get("resolution_mode") or "neutral_fallback"),
        "runtime_config": resolution.get("runtime_config"),
    }


def _build_runtime_server_item_payload(
    *,
    record: RuntimeServerRecord,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore | None = None,
    store: RuntimeServersStore,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
) -> dict[str, Any]:
    payload = store.to_payload(record)
    context = _collect_runtime_server_context(
        server_code=record.code,
        runtime_servers_store=store,
        law_sets_store=law_sets_store,
        source_sets_store=source_sets_store,
        server=record,
        include_health=False,
    )
    payload["onboarding"] = _build_runtime_server_onboarding_payload(
        server=record,
        resolution=context["resolution"],
        source_set_bindings=context["source_set_bindings"],
        runtime_bindings=context["runtime_bindings"],
        binding_source=str(context["binding_source"] or "runtime_bindings"),
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
    source_sets_store: LawSourceSetsStore | None = None,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
) -> dict[str, Any]:
    items = [
        _build_runtime_server_item_payload(
            record=record,
            law_sets_store=law_sets_store,
            source_sets_store=source_sets_store,
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
    source_sets_store: LawSourceSetsStore | None = None,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
    code: str,
    title: str,
) -> dict[str, Any]:
    row = store.create_server(code=code, title=title)
    return {
        "item": _build_runtime_server_item_payload(
            record=row,
            law_sets_store=law_sets_store,
            source_sets_store=source_sets_store,
            store=store,
            projections_store=projections_store,
        )
    }


def update_runtime_server_payload(
    *,
    store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore | None = None,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
    code: str,
    title: str,
) -> dict[str, Any]:
    row = store.update_server(code=code, title=title)
    return {
        "item": _build_runtime_server_item_payload(
            record=row,
            law_sets_store=law_sets_store,
            source_sets_store=source_sets_store,
            store=store,
            projections_store=projections_store,
        )
    }


def set_runtime_server_active_payload(
    *,
    store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore | None = None,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
    code: str,
    is_active: bool,
) -> dict[str, Any]:
    row = store.set_active(code=code, is_active=is_active)
    return {
        "item": _build_runtime_server_item_payload(
            record=row,
            law_sets_store=law_sets_store,
            source_sets_store=source_sets_store,
            store=store,
            projections_store=projections_store,
        )
    }


def build_runtime_server_health_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore | None = None,
    projections_store: ServerEffectiveLawProjectionsStore | None = None,
) -> dict[str, Any]:
    context = _collect_runtime_server_context(
        server_code=server_code,
        runtime_servers_store=runtime_servers_store,
        law_sets_store=law_sets_store,
        source_sets_store=source_sets_store,
    )
    normalized_code = context["server_code"]
    server = context["server"]
    active_law_set = context["active_law_set"]
    bindings = context["bindings"]
    active_law_version = context["active_law_version"]
    chunk_count = context["chunk_count"]
    onboarding = _build_runtime_server_onboarding_payload(
        server=server,
        resolution=context["resolution"],
        source_set_bindings=context["source_set_bindings"],
        runtime_bindings=context["runtime_bindings"],
        binding_source=str(context["binding_source"] or "runtime_bindings"),
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
            "detail": "law_set_present" if active_law_set else "law_set_missing",
            "law_set_id": int(active_law_set.get("id")) if active_law_set and active_law_set.get("id") is not None else None,
            "observational_only": True,
        },
        "bindings": {
            "ok": bool(onboarding.get("canonical_binding_ready")),
            "detail": f"source_set_bindings:{len(context['source_set_bindings'] or [])}",
            "count": len(context["source_set_bindings"] or []),
            "binding_source": str(context["binding_source"] or "runtime_bindings"),
            "canonical_ready": str(context["binding_source"] or "runtime_bindings") == "source_set_bindings",
            "source_set_binding_count": len(context["source_set_bindings"] or []),
            "runtime_binding_count": len(context["runtime_bindings"] or []),
            "uses_runtime_bindings_fallback": bool(onboarding.get("uses_runtime_bindings_fallback")),
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
            "runtime_shell_artifact_present": bool(active_law_set or active_law_version),
        },
        "config_resolution": {
            "ok": not bool(onboarding.get("requires_explicit_runtime_pack")),
            "detail": (
                f"resolution:{onboarding.get('resolution_mode')}"
                if not bool(onboarding.get("requires_explicit_runtime_pack"))
                else "neutral_fallback_requires_pack_publication"
            ),
            "resolution_mode": str(onboarding.get("resolution_mode") or "neutral_fallback"),
            "requires_explicit_runtime_pack": bool(onboarding.get("requires_explicit_runtime_pack")),
        },
    }
    required_check_codes = ("server", "bindings", "activation", "health", "config_resolution")
    ready_count = sum(1 for code in required_check_codes if checks.get(code, {}).get("ok"))
    projection_bridge = _build_projection_bridge_summary(
        server_code=normalized_code,
        projections_store=projections_store,
        active_law_version=active_law_version,
    )
    runtime_provenance = _build_runtime_laws_provenance_summary(
        active_law_set=active_law_set,
        active_law_version=active_law_version,
        projection_bridge=projection_bridge,
        bindings=bindings,
    )
    runtime_alignment = _build_runtime_alignment_summary(
        active_law_set=active_law_set,
        active_law_version=active_law_version,
        projection_bridge=projection_bridge,
    )
    observational_checks: list[str] = []
    if not checks["law_set"]["ok"]:
        observational_checks.append("law_set")
    if bool(onboarding.get("uses_runtime_bindings_fallback")):
        observational_checks.append("runtime_bindings")
    return {
        "server_code": normalized_code,
        "checks": checks,
        "onboarding": onboarding,
        "projection_bridge": projection_bridge,
        "runtime_provenance": runtime_provenance,
        "runtime_alignment": runtime_alignment,
        "summary": {
            "ready_count": ready_count,
            "total_count": len(required_check_codes),
            "is_ready": ready_count == len(required_check_codes),
            "observed_check_count": len(checks),
            "observational_checks": observational_checks,
        },
    }


def build_runtime_config_posture_summary(*, health_payload: dict[str, Any]) -> dict[str, Any]:
    onboarding = dict((health_payload or {}).get("onboarding") or {})
    checks = dict((health_payload or {}).get("checks") or {})
    config_resolution = dict(checks.get("config_resolution") or {})
    resolution_mode = str(onboarding.get("resolution_mode") or config_resolution.get("resolution_mode") or "neutral_fallback").strip().lower()
    highest_completed_state = str(onboarding.get("highest_completed_state") or "not-ready").strip().lower()
    next_required_state = str(onboarding.get("next_required_state") or "").strip().lower()
    requires_explicit_runtime_pack = bool(
        onboarding.get("requires_explicit_runtime_pack")
        if "requires_explicit_runtime_pack" in onboarding
        else config_resolution.get("requires_explicit_runtime_pack")
    )

    if resolution_mode == "published_pack" and not requires_explicit_runtime_pack:
        status = "declared_ready"
        detail = "Runtime resolves through an explicit published pack."
        next_step = "Config resolution looks declared and stable."
    elif resolution_mode == "bootstrap_pack" and not requires_explicit_runtime_pack:
        status = "bootstrap_transition"
        detail = "Runtime still resolves through a bootstrap pack instead of a published runtime pack."
        next_step = "Опубликуйте runtime/server pack, когда сервер будет готов выйти из bootstrap path."
    else:
        status = "fallback_only"
        detail = "Runtime still depends on neutral fallback because no explicit published/bootstrap runtime pack is locked in."
        next_step = "Опубликуйте runtime/server pack или закрепите bootstrap pack, чтобы выйти из fallback path."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "resolution_mode": resolution_mode,
        "highest_completed_state": highest_completed_state,
        "next_required_state": next_required_state,
        "requires_explicit_runtime_pack": requires_explicit_runtime_pack,
    }


def build_runtime_config_debt_summary(*, health_payload: dict[str, Any]) -> dict[str, Any]:
    onboarding = dict((health_payload or {}).get("onboarding") or {})
    posture = build_runtime_config_posture_summary(health_payload=health_payload)
    resolution_mode = str(posture.get("resolution_mode") or "neutral_fallback").strip().lower()
    highest_completed_state = str(posture.get("highest_completed_state") or "not-ready").strip().lower()
    reasons: list[str] = []

    if resolution_mode == "neutral_fallback":
        reasons.append("neutral_fallback")
    elif resolution_mode == "bootstrap_pack":
        reasons.append("bootstrap_pack")

    if str(onboarding.get("highest_completed_state") or "").strip().lower() in {"", "not-ready", "bootstrap-ready"}:
        reasons.append("onboarding_early")

    if bool(posture.get("requires_explicit_runtime_pack")):
        status = "high"
        detail = "Runtime config debt is high because the server is still addressable only through neutral fallback."
        next_step = "Сначала дайте серверу explicit published/bootstrap runtime pack."
    elif resolution_mode == "bootstrap_pack":
        status = "medium"
        detail = "Runtime config debt is medium because the server still relies on bootstrap-pack resolution."
        next_step = "Постепенно переводите сервер на published runtime pack."
    else:
        status = "low"
        detail = "Runtime config debt looks low in the current read model."
        next_step = "Явного config-resolution debt не видно."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "reason_count": len(reasons),
        "reasons": reasons,
        "resolution_mode": resolution_mode,
        "highest_completed_state": highest_completed_state,
    }


def build_runtime_resolution_policy_summary(*, health_payload: dict[str, Any]) -> dict[str, Any]:
    posture = build_runtime_config_posture_summary(health_payload=health_payload)
    debt = build_runtime_config_debt_summary(health_payload=health_payload)
    posture_status = str(posture.get("status") or "").strip().lower()
    debt_status = str(debt.get("status") or "").strip().lower()

    if posture_status == "declared_ready" and debt_status == "low":
        status = "declared_runtime"
        detail = "Server resolves through a declared runtime config path."
        next_step = "Config resolution policy looks clean."
    elif posture_status == "bootstrap_transition" and debt_status in {"medium", "low"}:
        status = "transitional_bootstrap"
        detail = "Server still relies on bootstrap-pack resolution as a transitional runtime policy."
        next_step = "Продолжайте перевод сервера на published runtime pack."
    else:
        status = "compatibility_exception"
        detail = "Server is still runtime-addressable only through a compatibility-style config path."
        next_step = "Сведите server config resolution к published/bootstrap policy без neutral fallback."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "posture_status": posture_status,
        "debt_status": debt_status,
        "resolution_mode": str(posture.get("resolution_mode") or "").strip().lower(),
    }
