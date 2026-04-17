from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from ogp_web.server_config import build_runtime_resolution_snapshot
from ogp_web.services.admin_runtime_servers_service import build_runtime_server_health_payload
from ogp_web.services.admin_server_access_workspace_service import build_server_access_summary_payload
from ogp_web.services.admin_server_content_workspace_service import (
    list_server_features_payload,
    list_server_templates_payload,
)
from ogp_web.services.capability_registry_service import list_capability_definitions
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.published_artifact_resolution_service import (
    COMPLAINT_VALIDATION_CONTENT_KEY,
    COURT_CLAIM_VALIDATION_CONTENT_KEY,
)
from ogp_web.services.published_runtime_gate_service import resolve_published_runtime_requirement
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.runtime_server_packs_store import RuntimeServerPacksStore
from ogp_web.storage.runtime_servers_store import RuntimeServersStore
from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore
from ogp_web.storage.user_store import UserStore


_ALLOWED_METADATA_KEYS = {
    "organizations",
    "procedure_types",
    "complaint_bases",
    "form_schema",
    "validation_profiles",
    "template_bindings",
    "terminology",
    "document_builder",
    "law_qa_sources",
    "law_qa_bundle_path",
    "feature_flags",
    "enabled_pages",
    "runtime_pack_compiler",
}

_SECTION_EXPLICIT_ARTIFACT_REQUIREMENTS: dict[str, dict[str, str]] = {
    "complaint": {
        "template_binding_key": "complaint",
        "validation_profile_key": COMPLAINT_VALIDATION_CONTENT_KEY,
    },
    "court_claim": {
        "template_binding_key": "court_claim",
        "validation_profile_key": COURT_CLAIM_VALIDATION_CONTENT_KEY,
    },
}


def _normalize_server_code(value: str) -> str:
    return str(value or "").strip().lower()


def _normalized_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(metadata or {}), ensure_ascii=False))


def _validate_metadata_candidate(metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise ValueError("server_pack_metadata_must_be_object")
    unknown_keys = sorted(str(key) for key in metadata.keys() if str(key) not in _ALLOWED_METADATA_KEYS)
    if unknown_keys:
        raise ValueError(f"server_pack_metadata_keys_invalid:{','.join(unknown_keys)}")
    return _normalized_metadata(metadata)


def _build_compiler_metadata(
    *,
    server_code: str,
    server_title: str,
    server_is_active: bool,
    metadata: dict[str, Any],
    resolution_snapshot: dict[str, Any],
    health_payload: dict[str, Any],
    features_payload: dict[str, Any],
    templates_payload: dict[str, Any],
    access_payload: dict[str, Any],
) -> dict[str, Any]:
    compiled = _normalized_metadata(metadata)
    compiled["runtime_pack_compiler"] = {
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "compiler_version": "v1",
        "server": {
            "code": server_code,
            "title": server_title,
            "is_active": bool(server_is_active),
        },
        "source_resolution": {
            "mode": str(resolution_snapshot.get("resolution_mode") or "neutral_fallback"),
            "label": str(resolution_snapshot.get("resolution_label") or ""),
            "pack_id": int((resolution_snapshot.get("pack") or {}).get("id") or 0) or None,
            "pack_version": int((resolution_snapshot.get("pack") or {}).get("version") or 0) or None,
        },
        "law_context": dict(health_payload.get("law_context_readiness") or {}),
        "features": {
            "effective_count": int((features_payload.get("counts") or {}).get("effective") or 0),
            "published_effective_count": int((features_payload.get("counts") or {}).get("published_effective") or 0),
            "keys": [
                str(item.get("content_key") or "")
                for item in list(features_payload.get("effective_items") or [])
                if str(item.get("content_key") or "").strip()
            ],
        },
        "templates": {
            "effective_count": int((templates_payload.get("counts") or {}).get("effective") or 0),
            "published_effective_count": int((templates_payload.get("counts") or {}).get("published_effective") or 0),
            "keys": [
                str(item.get("content_key") or "")
                for item in list(templates_payload.get("effective_items") or [])
                if str(item.get("content_key") or "").strip()
            ],
        },
        "access": {
            "active_users": int(((access_payload.get("summary") or {}).get("counts") or {}).get("active_users") or 0),
            "assignment_count": int(((access_payload.get("summary") or {}).get("counts") or {}).get("assignments") or 0),
        },
    }
    return compiled


def _build_publish_blockers(
    *,
    server_exists: bool,
    metadata: dict[str, Any],
    health_payload: dict[str, Any],
    features_payload: dict[str, Any],
    templates_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not server_exists:
        blockers.append({"code": "server_not_found", "detail": "Runtime server record is missing."})
        return blockers

    identity_defined = bool(
        list(metadata.get("organizations") or [])
        or list(metadata.get("procedure_types") or [])
        or list(metadata.get("enabled_pages") or [])
    )
    if not metadata:
        blockers.append(
            {
                "code": "runtime_metadata_missing",
                "detail": "No runtime metadata candidate exists yet; save a server pack draft first.",
            }
        )
    if not identity_defined:
        blockers.append(
            {
                "code": "identity_capabilities_missing",
                "detail": "Candidate metadata does not define organizations, procedure types, or enabled pages.",
            }
        )
    if not dict(metadata.get("template_bindings") or {}):
        blockers.append(
            {
                "code": "template_bindings_missing",
                "detail": "Candidate metadata does not declare template bindings.",
            }
        )
    if not dict(metadata.get("validation_profiles") or {}):
        blockers.append(
            {
                "code": "validation_profiles_missing",
                "detail": "Candidate metadata does not declare validation profiles.",
            }
        )
    if int((features_payload.get("counts") or {}).get("effective") or 0) <= 0:
        blockers.append({"code": "features_missing", "detail": "No effective feature definitions are available."})
    if int((templates_payload.get("counts") or {}).get("effective") or 0) <= 0:
        blockers.append({"code": "templates_missing", "detail": "No effective templates are available."})

    law_context = dict(health_payload.get("law_context_readiness") or {})
    law_required = bool(
        list(metadata.get("law_qa_sources") or [])
        or str(metadata.get("law_qa_bundle_path") or "").strip()
        or int(((health_payload.get("checks") or {}).get("bindings") or {}).get("count") or 0) > 0
    )
    if law_required and str(law_context.get("status") or "").strip().lower() != "ready":
        blockers.append(
            {
                "code": str(law_context.get("reason_code") or "law_context_not_ready"),
                "detail": str(law_context.get("reason_detail") or "Selected server law context is not ready for publish."),
            }
        )
    return blockers


def _resolve_candidate_artifact_gap(
    *,
    section_code: str,
    metadata: dict[str, Any],
) -> tuple[str, str] | None:
    rules = _SECTION_EXPLICIT_ARTIFACT_REQUIREMENTS.get(str(section_code or "").strip().lower())
    if not rules:
        return None
    template_binding_key = str(rules.get("template_binding_key") or "").strip()
    validation_profile_key = str(rules.get("validation_profile_key") or "").strip()
    template_bindings = dict(metadata.get("template_bindings") or {})
    validation_profiles = dict(metadata.get("validation_profiles") or {})

    binding = dict(template_bindings.get(template_binding_key) or {})
    if not str(binding.get("template_key") or "").strip():
        return (
            f"{section_code}_template_binding_missing",
            f"Candidate metadata does not declare template_bindings.{template_binding_key}.template_key for published runtime.",
        )
    if validation_profile_key and validation_profile_key not in validation_profiles:
        return (
            f"{section_code}_validation_profile_missing",
            f"Candidate metadata does not declare validation_profiles.{validation_profile_key} for published runtime.",
        )
    return None


def _build_candidate_runtime_requirements(
    *,
    server_exists: bool,
    metadata: dict[str, Any],
    health_payload: dict[str, Any],
) -> dict[str, Any]:
    identity_defined = bool(
        list(metadata.get("organizations") or [])
        or list(metadata.get("procedure_types") or [])
        or list(metadata.get("enabled_pages") or [])
    )
    simulated_resolution = {
        "resolution_mode": "published_pack",
        "requires_explicit_runtime_pack": not (server_exists and identity_defined),
        "has_published_pack": bool(server_exists and identity_defined),
        "is_runtime_addressable": bool(server_exists and identity_defined),
        "uses_transitional_fallback": False,
    }
    law_context = dict(health_payload.get("law_context_readiness") or {})
    law_context_ready = str(law_context.get("status") or "").strip().lower() == "ready"
    items: list[dict[str, Any]] = []
    blocked_count = 0
    compatibility_count = 0
    for capability in list_capability_definitions():
        requirement = resolve_published_runtime_requirement(
            capability=capability,
            runtime_resolution_snapshot=simulated_resolution,
        )
        if capability.requires_law_context and not law_context_ready:
            route_ready = False
            route_status = "blocked"
            route_reason_code = str(law_context.get("reason_code") or "law_context_not_ready")
            route_reason_detail = str(
                law_context.get("reason_detail") or "Selected server law context is not ready for this capability."
            )
        else:
            route_ready = requirement.is_ready
            route_status = "ready_with_compatibility" if requirement.compatibility_mode else ("ready" if route_ready else "blocked")
            route_reason_code = requirement.reason_code
            route_reason_detail = requirement.reason_detail
        artifact_gap = _resolve_candidate_artifact_gap(
            section_code=capability.section_code,
            metadata=metadata,
        )
        if artifact_gap is not None:
            route_ready = False
            route_status = "blocked"
            route_reason_code, route_reason_detail = artifact_gap
        if route_status == "ready_with_compatibility":
            compatibility_count += 1
        if not route_ready:
            blocked_count += 1
        items.append(
            {
                "section_code": capability.section_code,
                "capability_code": capability.capability_code,
                "route_ready": route_ready,
                "route_status": route_status,
                "route_reason_code": route_reason_code,
                "route_reason_detail": route_reason_detail,
                "runtime_requirement": requirement.to_payload(),
            }
        )
    status = "blocked"
    if blocked_count == 0:
        status = "ready_with_compatibility" if compatibility_count > 0 else "ready"
    return {
        "status": status,
        "is_ready": blocked_count == 0,
        "blocked_count": blocked_count,
        "compatibility_count": compatibility_count,
        "items": items,
    }


def _build_pack_context(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    runtime_server_packs_store: RuntimeServerPacksStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    workflow_service: ContentWorkflowService,
    user_store: UserStore,
) -> dict[str, Any]:
    normalized_server = _normalize_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    resolution_snapshot = build_runtime_resolution_snapshot(
        server_code=normalized_server,
        title=str(server.title or normalized_server),
    )
    published_pack = runtime_server_packs_store.get_latest_published_pack(server_code=normalized_server)
    draft_pack = runtime_server_packs_store.get_latest_draft_pack(server_code=normalized_server)
    rollback_target = runtime_server_packs_store.get_previous_published_pack(server_code=normalized_server)
    features_payload = list_server_features_payload(
        workflow_service=workflow_service,
        server_code=normalized_server,
    )
    templates_payload = list_server_templates_payload(
        workflow_service=workflow_service,
        server_code=normalized_server,
    )
    access_payload = build_server_access_summary_payload(user_store=user_store, server_code=normalized_server)
    health_payload = build_runtime_server_health_payload(
        server_code=normalized_server,
        runtime_servers_store=runtime_servers_store,
        law_sets_store=law_sets_store,
        source_sets_store=source_sets_store,
        projections_store=projections_store,
    )
    base_metadata = (
        dict((draft_pack.metadata_json if draft_pack is not None else None) or {})
        or dict((published_pack.metadata_json if published_pack is not None else None) or {})
        or dict((resolution_snapshot.get("pack_metadata") or {}) or {})
    )
    compiled_metadata = _build_compiler_metadata(
        server_code=normalized_server,
        server_title=str(server.title or normalized_server),
        server_is_active=bool(server.is_active),
        metadata=base_metadata,
        resolution_snapshot=resolution_snapshot,
        health_payload=health_payload,
        features_payload=features_payload,
        templates_payload=templates_payload,
        access_payload=access_payload,
    )
    blockers = _build_publish_blockers(
        server_exists=True,
        metadata=compiled_metadata,
        health_payload=health_payload,
        features_payload=features_payload,
        templates_payload=templates_payload,
    )
    candidate_runtime_requirements = _build_candidate_runtime_requirements(
        server_exists=True,
        metadata=compiled_metadata,
        health_payload=health_payload,
    )
    if not bool(candidate_runtime_requirements.get("is_ready")):
        for item in list(candidate_runtime_requirements.get("items") or []):
            if bool(item.get("route_ready")):
                continue
            blockers.append(
                {
                    "code": f"runtime_requirement:{item.get('section_code')}",
                    "detail": str(item.get("route_reason_detail") or item.get("route_reason_code") or "Runtime requirement blocked."),
                    "section_code": str(item.get("section_code") or ""),
                    "reason_code": str(item.get("route_reason_code") or ""),
                }
            )
    next_version = (
        int(draft_pack.version)
        if draft_pack is not None
        else (int(published_pack.version) + 1 if published_pack is not None else 1)
    )
    return {
        "server_code": normalized_server,
        "server": server,
        "resolution_snapshot": resolution_snapshot,
        "published_pack": published_pack,
        "draft_pack": draft_pack,
        "rollback_target": rollback_target,
        "features_payload": features_payload,
        "templates_payload": templates_payload,
        "access_payload": access_payload,
        "health_payload": health_payload,
        "compiled_metadata": compiled_metadata,
        "candidate_runtime_requirements": candidate_runtime_requirements,
        "blockers": blockers,
        "next_version": next_version,
    }


def _build_draft_payload_from_context(context: dict[str, Any]) -> dict[str, Any]:
    published_pack = context["published_pack"]
    draft_pack = context["draft_pack"]
    rollback_target = context.get("rollback_target")
    compiled_metadata = dict(context["compiled_metadata"] or {})
    blockers = list(context["blockers"] or [])
    return {
        "server_code": context["server_code"],
        "draft": RuntimeServerPacksStore.to_payload(draft_pack)
        or {
            "id": None,
            "server_code": context["server_code"],
            "version": int(context["next_version"] or 1),
            "status": "draft",
            "metadata": compiled_metadata,
            "created_at": "",
            "published_at": None,
        },
        "draft_source": "stored" if draft_pack is not None else "compiled_preview",
        "published_pack": RuntimeServerPacksStore.to_payload(published_pack),
        "rollback": {
            "current_published_version": int((published_pack.version if published_pack is not None else 0) or 0),
            "available": rollback_target is not None,
            "target_version": int((rollback_target.version if rollback_target is not None else 0) or 0) or None,
            "target_pack": RuntimeServerPacksStore.to_payload(rollback_target),
        },
        "compiler": {
            "status": "ready" if not blockers else "blocked",
            "blocker_count": len(blockers),
            "blockers": blockers,
            "source_resolution_mode": str((context["resolution_snapshot"] or {}).get("resolution_mode") or "neutral_fallback"),
            "candidate_runtime_requirements": dict(context.get("candidate_runtime_requirements") or {}),
        },
    }


def build_runtime_server_pack_draft_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    runtime_server_packs_store: RuntimeServerPacksStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    workflow_service: ContentWorkflowService,
    user_store: UserStore,
) -> dict[str, Any]:
    context = _build_pack_context(
        server_code=server_code,
        runtime_servers_store=runtime_servers_store,
        runtime_server_packs_store=runtime_server_packs_store,
        law_sets_store=law_sets_store,
        source_sets_store=source_sets_store,
        projections_store=projections_store,
        workflow_service=workflow_service,
        user_store=user_store,
    )
    return _build_draft_payload_from_context(context)


def update_runtime_server_pack_draft_payload(
    *,
    server_code: str,
    metadata: dict[str, Any],
    runtime_servers_store: RuntimeServersStore,
    runtime_server_packs_store: RuntimeServerPacksStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    workflow_service: ContentWorkflowService,
    user_store: UserStore,
) -> dict[str, Any]:
    context = _build_pack_context(
        server_code=server_code,
        runtime_servers_store=runtime_servers_store,
        runtime_server_packs_store=runtime_server_packs_store,
        law_sets_store=law_sets_store,
        source_sets_store=source_sets_store,
        projections_store=projections_store,
        workflow_service=workflow_service,
        user_store=user_store,
    )
    validated_metadata = _validate_metadata_candidate(metadata)
    compiled_metadata = _build_compiler_metadata(
        server_code=context["server_code"],
        server_title=str(context["server"].title or context["server_code"]),
        server_is_active=bool(context["server"].is_active),
        metadata=validated_metadata,
        resolution_snapshot=context["resolution_snapshot"],
        health_payload=context["health_payload"],
        features_payload=context["features_payload"],
        templates_payload=context["templates_payload"],
        access_payload=context["access_payload"],
    )
    saved = runtime_server_packs_store.save_draft_pack(
        server_code=context["server_code"],
        metadata_json=compiled_metadata,
    )
    context["draft_pack"] = saved
    context["compiled_metadata"] = compiled_metadata
    context["blockers"] = _build_publish_blockers(
        server_exists=True,
        metadata=compiled_metadata,
        health_payload=context["health_payload"],
        features_payload=context["features_payload"],
        templates_payload=context["templates_payload"],
    )
    return _build_draft_payload_from_context(context)


def build_runtime_server_pack_publish_blockers_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    runtime_server_packs_store: RuntimeServerPacksStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    workflow_service: ContentWorkflowService,
    user_store: UserStore,
) -> dict[str, Any]:
    context = _build_pack_context(
        server_code=server_code,
        runtime_servers_store=runtime_servers_store,
        runtime_server_packs_store=runtime_server_packs_store,
        law_sets_store=law_sets_store,
        source_sets_store=source_sets_store,
        projections_store=projections_store,
        workflow_service=workflow_service,
        user_store=user_store,
    )
    blockers = list(context["blockers"] or [])
    return {
        "server_code": context["server_code"],
        "status": "ready" if not blockers else "blocked",
        "can_publish": not blockers,
        "count": len(blockers),
        "items": blockers,
        "candidate_runtime_requirements": dict(context.get("candidate_runtime_requirements") or {}),
        "draft_version": int((context["draft_pack"].version if context["draft_pack"] is not None else context["next_version"]) or 1),
        "published_version": int((context["published_pack"].version if context["published_pack"] is not None else 0) or 0),
        "rollback": {
            "available": context.get("rollback_target") is not None,
            "target_version": int((((context.get("rollback_target") or {}).version) if context.get("rollback_target") is not None else 0) or 0)
            or None,
        },
    }


def publish_runtime_server_pack_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    runtime_server_packs_store: RuntimeServerPacksStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    workflow_service: ContentWorkflowService,
    user_store: UserStore,
) -> dict[str, Any]:
    context = _build_pack_context(
        server_code=server_code,
        runtime_servers_store=runtime_servers_store,
        runtime_server_packs_store=runtime_server_packs_store,
        law_sets_store=law_sets_store,
        source_sets_store=source_sets_store,
        projections_store=projections_store,
        workflow_service=workflow_service,
        user_store=user_store,
    )
    blockers = list(context["blockers"] or [])
    if blockers:
        raise ValueError("server_pack_publish_blocked")
    compiled_metadata = dict(context["compiled_metadata"] or {})
    published_pack = context["published_pack"]
    if published_pack is not None and _normalized_metadata(published_pack.metadata_json) == _normalized_metadata(compiled_metadata):
        return {
            "server_code": context["server_code"],
            "published_pack": RuntimeServerPacksStore.to_payload(published_pack),
            "changed": False,
            "reason": "already_published",
        }
    runtime_server_packs_store.save_draft_pack(
        server_code=context["server_code"],
        metadata_json=compiled_metadata,
    )
    published = runtime_server_packs_store.publish_latest_draft_pack(server_code=context["server_code"])
    return {
        "server_code": context["server_code"],
        "published_pack": RuntimeServerPacksStore.to_payload(published),
        "changed": True,
        "reason": "published",
    }


def rollback_runtime_server_pack_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    runtime_server_packs_store: RuntimeServerPacksStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore | None,
    workflow_service: ContentWorkflowService,
    user_store: UserStore,
    target_version: int | None = None,
) -> dict[str, Any]:
    context = _build_pack_context(
        server_code=server_code,
        runtime_servers_store=runtime_servers_store,
        runtime_server_packs_store=runtime_server_packs_store,
        law_sets_store=law_sets_store,
        source_sets_store=source_sets_store,
        projections_store=projections_store,
        workflow_service=workflow_service,
        user_store=user_store,
    )
    current_published = context["published_pack"]
    if current_published is None:
        raise KeyError("server_pack_published_not_found")
    rollback_target = (
        runtime_server_packs_store.get_published_pack_by_version(
            server_code=context["server_code"],
            version=int(target_version or 0),
        )
        if int(target_version or 0) > 0
        else context.get("rollback_target")
    )
    if rollback_target is None:
        raise KeyError("server_pack_rollback_target_not_found")
    if _normalized_metadata(current_published.metadata_json) == _normalized_metadata(rollback_target.metadata_json):
        return {
            "server_code": context["server_code"],
            "changed": False,
            "reason": "already_matches_target",
            "published_pack": RuntimeServerPacksStore.to_payload(current_published),
            "rollback_target": RuntimeServerPacksStore.to_payload(rollback_target),
        }
    rolled_back = runtime_server_packs_store.rollback_to_published_pack(
        server_code=context["server_code"],
        target_version=int(target_version or 0) or None,
    )
    return {
        "server_code": context["server_code"],
        "changed": True,
        "reason": "rolled_back",
        "published_pack": RuntimeServerPacksStore.to_payload(rolled_back),
        "rollback_target": RuntimeServerPacksStore.to_payload(rollback_target),
    }
