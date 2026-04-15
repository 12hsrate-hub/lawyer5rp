from __future__ import annotations

from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalized_snapshot_ref(value: Any, *, preferred_keys: tuple[str, ...] = ()) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in preferred_keys:
            candidate = str(value.get(key) or "").strip()
            if candidate:
                return candidate
        for key in ("id", "key", "code", "hash", "version"):
            candidate = str(value.get(key) or "").strip()
            if candidate:
                return candidate
        parts = []
        for key in ("id", "hash"):
            candidate = str(value.get(key) or "").strip()
            if candidate:
                parts.append(f"{key}={candidate}")
        if parts:
            return ", ".join(parts)
    return ""


def extract_snapshot_blocks(snapshot_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    context_snapshot = as_dict(snapshot_payload.get("context_snapshot"))
    effective_config = as_dict(snapshot_payload.get("effective_config_snapshot"))
    workflow_ref = as_dict(snapshot_payload.get("content_workflow_ref"))
    return context_snapshot, effective_config, workflow_ref


def build_snapshot_summary(snapshot_payload: dict[str, Any]) -> dict[str, str]:
    context_snapshot, effective_config, workflow_ref = extract_snapshot_blocks(snapshot_payload)
    return {
        "template_version": normalized_snapshot_ref(
            context_snapshot.get("template_version") or workflow_ref.get("template"),
            preferred_keys=("template_code", "id"),
        ),
        "law_version_set": normalized_snapshot_ref(
            context_snapshot.get("law_version_set") or effective_config.get("law_set_version"),
            preferred_keys=("law_set_key", "hash", "id"),
        ),
        "validation_rules_version": normalized_snapshot_ref(
            context_snapshot.get("validation_rules_version"),
            preferred_keys=("rule_set_key", "hash", "id"),
        ),
        "procedure": normalized_snapshot_ref(
            workflow_ref.get("procedure"),
            preferred_keys=("procedure_code", "id"),
        ),
        "prompt_version": normalized_snapshot_ref(workflow_ref.get("prompt_version")),
    }


def build_workflow_linkage(
    snapshot_payload: dict[str, Any],
    *,
    document_version_id: int,
    generation_snapshot_id: int,
    latest_validation_run_id: int | None,
) -> dict[str, Any]:
    _, effective_config, workflow_ref = extract_snapshot_blocks(snapshot_payload)
    return {
        "direct_catalog_mapping_available": False,
        "linkage_mode": "snapshot_refs_only",
        "procedure_ref": normalized_snapshot_ref(
            workflow_ref.get("procedure"),
            preferred_keys=("procedure_code", "id"),
        ),
        "template_ref": normalized_snapshot_ref(
            workflow_ref.get("template"),
            preferred_keys=("template_code", "id"),
        ),
        "prompt_version": normalized_snapshot_ref(workflow_ref.get("prompt_version")),
        "server_config_version": normalized_snapshot_ref(effective_config.get("server_config_version")),
        "law_set_version": normalized_snapshot_ref(
            effective_config.get("law_set_version"),
            preferred_keys=("law_set_key", "hash", "id"),
        ),
        "document_version_id": int(document_version_id),
        "generation_snapshot_id": int(generation_snapshot_id),
        "latest_validation_run_id": latest_validation_run_id,
    }


def extract_provenance_config(snapshot_payload: dict[str, Any], *, fallback_law_version_id: int | None = None) -> dict[str, Any]:
    context_snapshot, effective_config, workflow_ref = extract_snapshot_blocks(snapshot_payload)
    effective_versions = as_dict(context_snapshot.get("effective_versions"))
    config = {
        "server_config_version": str(effective_config.get("server_config_version") or ""),
        "procedure_version": str(
            workflow_ref.get("procedure") or as_dict(context_snapshot.get("content_workflow")).get("procedure") or ""
        ),
        "template_version": str(
            workflow_ref.get("template") or as_dict(context_snapshot.get("content_workflow")).get("template") or ""
        ),
        "law_set_version": str(effective_config.get("law_set_version") or ""),
        "law_version_id": effective_versions.get("law_version_id"),
    }
    if fallback_law_version_id and not config.get("law_version_id"):
        config["law_version_id"] = fallback_law_version_id
    return config


def extract_provenance_ai(snapshot_payload: dict[str, Any]) -> dict[str, Any]:
    context_snapshot, _, workflow_ref = extract_snapshot_blocks(snapshot_payload)
    ai = as_dict(context_snapshot.get("ai"))
    content_workflow = as_dict(context_snapshot.get("content_workflow"))
    return {
        "provider": str(ai.get("provider") or ""),
        "model_id": str(ai.get("model") or ""),
        "prompt_version": str(workflow_ref.get("prompt_version") or content_workflow.get("prompt_version") or ""),
    }
