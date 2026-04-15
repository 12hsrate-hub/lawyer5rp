from __future__ import annotations

from typing import Any

from ogp_web.schemas import AdminCatalogItemPayload, AdminCatalogRollbackPayload, AdminCatalogWorkflowPayload
from ogp_web.services.content_contracts import normalize_content_type
from ogp_web.services.content_workflow_service import ContentWorkflowService


def normalize_admin_catalog_entity_type(entity_type: str) -> str:
    return normalize_content_type(entity_type, allow_legacy_import_alias=True)


def build_catalog_audit_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    entity_type: str,
    entity_id: str,
    limit: int,
) -> dict[str, Any]:
    normalized_entity_type = str(entity_type or "").strip().lower()
    normalized_entity_id = str(entity_id or "").strip()
    audit = workflow_service.list_audit_trail(
        server_scope="server",
        server_id=server_code,
        entity_type=normalized_entity_type,
        entity_id=normalized_entity_id,
        limit=limit,
    )
    return {
        "items": audit,
        "filters": {
            "entity_type": normalized_entity_type,
            "entity_id": normalized_entity_id,
            "limit": limit,
        },
    }


def build_catalog_list_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    entity_type: str,
) -> dict[str, Any]:
    normalized_entity_type = normalize_admin_catalog_entity_type(entity_type)
    result = workflow_service.list_content_items(
        server_scope="server",
        server_id=server_code,
        content_type=normalized_entity_type,
        include_legacy_fallback=False,
    )
    audit = workflow_service.list_audit_trail(
        server_scope="server",
        server_id=server_code,
        entity_type="",
        entity_id="",
        limit=100,
    )
    enriched_items: list[dict[str, Any]] = []
    for item in result["items"]:
        item_copy = dict(item)
        change_requests = workflow_service.list_change_requests(
            content_item_id=int(item_copy.get("id")),
            server_scope="server",
            server_id=server_code,
        )
        active_change_request = resolve_active_change_request(item_copy, change_requests)
        item_copy["active_change_request_id"] = (
            int(active_change_request.get("id")) if active_change_request and active_change_request.get("id") is not None else None
        )
        item_copy["active_change_request_status"] = (
            str(active_change_request.get("status") or "").strip().lower() if active_change_request else ""
        )
        enriched_items.append(item_copy)
    return {
        "entity_type": entity_type,
        "items": enriched_items,
        "legacy_fallback": result["legacy_fallback"],
        "audit": audit,
    }


def build_catalog_item_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    item_id: int,
) -> dict[str, Any]:
    item = workflow_service.get_content_item(
        content_item_id=item_id,
        server_scope="server",
        server_id=server_code,
    )
    versions = workflow_service.list_versions(
        content_item_id=item_id,
        server_scope="server",
        server_id=server_code,
    )
    change_requests = workflow_service.list_change_requests(
        content_item_id=item_id,
        server_scope="server",
        server_id=server_code,
    )
    versions_by_id = {
        int(version.get("id")): version
        for version in versions
        if isinstance(version, dict) and version.get("id") is not None
    }
    latest_change_request = change_requests[0] if change_requests else None
    effective_version = None
    effective_payload: dict[str, Any] = {}

    published_version_id = item.get("current_published_version_id")
    if published_version_id is not None:
        effective_version = versions_by_id.get(int(published_version_id))

    if not effective_version and latest_change_request:
        candidate_version_id = latest_change_request.get("candidate_version_id")
        if candidate_version_id is not None:
            effective_version = versions_by_id.get(int(candidate_version_id))

    if not effective_version and versions:
        effective_version = versions[-1]

    if effective_version:
        payload_candidate = effective_version.get("payload_json")
        if isinstance(payload_candidate, dict):
            effective_payload = payload_candidate

    return {
        "item": item,
        "versions": versions,
        "change_requests": change_requests,
        "effective_version": effective_version,
        "effective_payload": effective_payload,
        "latest_change_request": latest_change_request,
    }


def build_catalog_versions_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    item_id: int,
) -> dict[str, Any]:
    versions = workflow_service.list_versions(
        content_item_id=item_id,
        server_scope="server",
        server_id=server_code,
    )
    return {"versions": versions}


def review_catalog_change_request_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    change_request_id: int,
    actor_user_id: int,
    request_id: str,
    decision: str,
    comment: str,
) -> dict[str, Any]:
    result = workflow_service.review_change_request(
        change_request_id=change_request_id,
        reviewer_user_id=actor_user_id,
        decision=decision,
        comment=comment,
        diff_json={"review_via": "admin_api"},
        request_id=request_id,
        server_scope="server",
        server_id=server_code,
    )
    return {"ok": True, "result": result}


def validate_catalog_change_request_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    change_request_id: int,
) -> dict[str, Any]:
    result = workflow_service.validate_change_request(
        change_request_id=change_request_id,
        server_scope="server",
        server_id=server_code,
    )
    return {"ok": True, "result": result}


def create_catalog_item_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    actor_user_id: int,
    request_id: str,
    entity_type: str,
    payload: AdminCatalogItemPayload,
) -> dict[str, Any]:
    normalized_entity_type = normalize_admin_catalog_entity_type(entity_type)
    final_config = build_catalog_payload_config(payload)
    item = workflow_service.create_content_item(
        server_scope="server",
        server_id=server_code,
        content_type=normalized_entity_type,
        content_key=str(final_config.get("key") or payload.title or "").strip().lower().replace(" ", "_"),
        title=payload.title,
        metadata_json={"config": final_config},
        actor_user_id=actor_user_id,
        request_id=request_id,
    )
    return {"ok": True, "item": item}


def update_catalog_item_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    actor_user_id: int,
    request_id: str,
    item_id: int,
    payload: AdminCatalogItemPayload,
) -> dict[str, Any]:
    final_config = build_catalog_payload_config(payload)
    result = workflow_service.create_draft_version(
        content_item_id=item_id,
        payload_json=final_config,
        schema_version=1,
        actor_user_id=actor_user_id,
        request_id=request_id,
        server_scope="server",
        server_id=server_code,
        comment=f"update:{payload.title}",
    )
    item = result["content_item"]
    return {"ok": True, "item": item, "change_request": result["change_request"], "version": result["version"]}


def execute_catalog_workflow_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    actor_user_id: int,
    request_id: str,
    payload: AdminCatalogWorkflowPayload,
    query_change_request_id: int = 0,
) -> dict[str, Any]:
    action = str(payload.action or "").strip().lower()
    change_request_id = int(payload.change_request_id or query_change_request_id or 0)
    if change_request_id <= 0:
        raise ValueError("change_request_id_required")
    if action == "submit_for_review":
        response = workflow_service.submit_change_request(
            change_request_id=change_request_id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            server_scope="server",
            server_id=server_code,
        )
    elif action == "approve":
        response = workflow_service.review_change_request(
            change_request_id=change_request_id,
            reviewer_user_id=actor_user_id,
            decision="approve",
            comment="approved_via_admin_route",
            diff_json={"source": "admin_route"},
            request_id=request_id,
            server_scope="server",
            server_id=server_code,
        )
    elif action == "request_changes":
        response = workflow_service.review_change_request(
            change_request_id=change_request_id,
            reviewer_user_id=actor_user_id,
            decision="request_changes",
            comment="requested_changes_via_admin_route",
            diff_json={"source": "admin_route"},
            request_id=request_id,
            server_scope="server",
            server_id=server_code,
        )
    elif action == "publish":
        response = workflow_service.publish_change_request(
            change_request_id=change_request_id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            summary_json={"source": "admin_route"},
            server_scope="server",
            server_id=server_code,
        )
    else:
        raise ValueError("unsupported_workflow_action")
    return {"ok": True, "result": response}


def rollback_catalog_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    actor_user_id: int,
    request_id: str,
    payload: AdminCatalogRollbackPayload,
) -> dict[str, Any]:
    result = workflow_service.rollback_publish_batch(
        publish_batch_id=int(payload.version),
        actor_user_id=actor_user_id,
        request_id=request_id,
        reason="manual_admin_rollback",
        server_scope="server",
        server_id=server_code,
    )
    return {"ok": True, "result": result}


def resolve_active_change_request_id(item: dict[str, Any], change_requests: list[dict[str, Any]]) -> int | None:
    item_status = str(item.get("status") or "").strip().lower()
    if not change_requests:
        return None
    if item_status in {"draft", "in_review", "approved"}:
        for change_request in change_requests:
            if str(change_request.get("status") or "").strip().lower() == item_status:
                try:
                    return int(change_request.get("id"))
                except (TypeError, ValueError):
                    continue
    try:
        return int(change_requests[0].get("id"))
    except (TypeError, ValueError, IndexError):
        return None


def resolve_active_change_request(item: dict[str, Any], change_requests: list[dict[str, Any]]) -> dict[str, Any] | None:
    active_change_request_id = resolve_active_change_request_id(item, change_requests)
    if active_change_request_id is None:
        return None
    for change_request in change_requests:
        try:
            if int(change_request.get("id")) == active_change_request_id:
                return change_request
        except (TypeError, ValueError):
            continue
    return None


def build_catalog_payload_config(payload: AdminCatalogItemPayload) -> dict[str, Any]:
    typed_fields: dict[str, Any] = {
        "key": payload.key,
        "description": payload.description,
        "status": payload.status,
        "server_code": payload.server_code,
        "base_url": payload.base_url,
        "timeout_sec": payload.timeout_sec,
        "law_code": payload.law_code,
        "source": payload.source,
        "effective_from": payload.effective_from,
        "template_type": payload.template_type,
        "document_kind": payload.document_kind,
        "output_format": payload.output_format,
        "feature_flag": payload.feature_flag,
        "rollout_percent": payload.rollout_percent,
        "audience": payload.audience,
        "rule_type": payload.rule_type,
        "priority": payload.priority,
        "applies_to": payload.applies_to,
    }
    cleaned_typed = {
        key: value
        for key, value in typed_fields.items()
        if value not in (None, "", [], {})
    }
    merged = {
        key: value
        for key, value in (payload.config or {}).items()
        if value is not None
    }
    merged.update(cleaned_typed)
    if "key" not in merged:
        merged["key"] = str(payload.title or "").strip().lower().replace(" ", "_")
    if "status" not in merged:
        merged["status"] = payload.status or "draft"
    if not str(merged.get("key") or "").strip():
        raise ValueError("key_required")
    return merged
