from __future__ import annotations

from typing import Any

from ogp_web.schemas import AdminCatalogItemPayload, AdminCatalogWorkflowPayload
from ogp_web.services.admin_catalog_service import (
    execute_catalog_workflow_payload,
    resolve_active_change_request,
)
from ogp_web.services.content_contracts import normalize_content_type
from ogp_web.services.content_workflow_service import ContentWorkflowService


def _normalize_server_code(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_content_key(value: str) -> str:
    return str(value or "").strip().lower()


def _build_item_payload(
    workflow_service: ContentWorkflowService,
    *,
    item: dict[str, Any],
    server_scope: str,
    server_id: str | None,
) -> dict[str, Any]:
    item_id = int(item.get("id") or 0)
    versions = workflow_service.list_versions(
        content_item_id=item_id,
        server_scope=server_scope,
        server_id=server_id,
    )
    change_requests = workflow_service.list_change_requests(
        content_item_id=item_id,
        server_scope=server_scope,
        server_id=server_id,
    )
    versions_by_id = {
        int(version.get("id")): dict(version)
        for version in versions
        if isinstance(version, dict) and version.get("id") is not None
    }
    latest_change_request = change_requests[0] if change_requests else None
    active_change_request = resolve_active_change_request(item, change_requests)
    effective_version = None
    published_version_id = item.get("current_published_version_id")
    if published_version_id is not None:
        effective_version = versions_by_id.get(int(published_version_id))
    if not effective_version and latest_change_request:
        candidate_version_id = latest_change_request.get("candidate_version_id")
        if candidate_version_id is not None:
            effective_version = versions_by_id.get(int(candidate_version_id))
    if not effective_version and versions:
        effective_version = dict(versions[-1])
    effective_payload = dict((effective_version or {}).get("payload_json") or {})
    draft_payload = {}
    if active_change_request and active_change_request.get("candidate_version_id") is not None:
        draft_payload = dict(versions_by_id.get(int(active_change_request["candidate_version_id"]), {}).get("payload_json") or {})
    return {
        "id": item_id,
        "content_key": str(item.get("content_key") or ""),
        "title": str(item.get("title") or ""),
        "status": str(item.get("status") or "draft"),
        "server_scope": str(item.get("server_scope") or server_scope),
        "server_id": str(item.get("server_id") or server_id or ""),
        "current_published_version_id": int(item.get("current_published_version_id") or 0) or None,
        "metadata_json": dict(item.get("metadata_json") or {}),
        "effective_version": effective_version,
        "effective_payload": effective_payload,
        "draft_payload": draft_payload,
        "change_requests": [dict(row) for row in change_requests],
        "latest_change_request": dict(latest_change_request) if latest_change_request else None,
        "active_change_request": dict(active_change_request) if active_change_request else None,
    }


def _list_scoped_items(
    workflow_service: ContentWorkflowService,
    *,
    server_scope: str,
    server_id: str | None,
    content_type: str,
) -> list[dict[str, Any]]:
    result = workflow_service.list_content_items(
        server_scope=server_scope,
        server_id=server_id,
        content_type=content_type,
        include_legacy_fallback=False,
    )
    items = result.get("items") if isinstance(result, dict) else []
    return [dict(item) for item in items or [] if isinstance(item, dict)]


def build_content_workspace_summary(
    *,
    effective_items: list[dict[str, Any]],
    content_type: str,
) -> dict[str, Any]:
    normalized_type = normalize_content_type(content_type)
    items = [dict(item) for item in list(effective_items or []) if isinstance(item, dict)]
    server_override_count = sum(
        1
        for item in items
        if bool(item.get("has_server_override")) or str(item.get("source_scope") or "").strip().lower() == "server"
    )
    active_workflow = [
        dict(item.get("active_change_request") or {})
        for item in items
        if isinstance(item.get("active_change_request"), dict) and item.get("active_change_request")
    ]
    active_workflow_count = len(active_workflow)
    draft_count = sum(
        1 for row in active_workflow if str(row.get("status") or "").strip().lower() == "draft"
    )
    in_review_count = sum(
        1 for row in active_workflow if str(row.get("status") or "").strip().lower() in {"in_review", "review"}
    )
    published_effective_count = sum(
        1 for item in items if str(item.get("status") or "").strip().lower() in {"published", "active"}
    )

    if not items:
        status = "not_configured"
        if normalized_type == "features":
            detail = "No effective feature items are available for this server yet."
            next_step = "Create the first feature override or confirm that the needed global defaults already exist."
        else:
            detail = "No effective template items are available for this server yet."
            next_step = "Create the first template override or confirm that the needed global defaults already exist."
    elif active_workflow_count > 0:
        status = "workflow_pending"
        if normalized_type == "features":
            detail = "Feature overrides exist, but draft/review workflow is still pending."
        else:
            detail = "Template overrides exist, but draft/review workflow is still pending."
        next_step = "Finish submit/review/publish actions for the pending server overrides."
    elif server_override_count > 0:
        status = "ready"
        if normalized_type == "features":
            detail = "Server-specific feature overrides are already in place."
        else:
            detail = "Server-specific template overrides are already in place."
        next_step = "Use edit/preview/reset actions only when the server needs another local override."
    else:
        status = "ready"
        if normalized_type == "features":
            detail = "Global feature defaults are effective for this server."
        else:
            detail = "Global template defaults are effective for this server."
        next_step = "Create a server override only when the server needs a local deviation from global defaults."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "counts": {
            "effective": len(items),
            "server_overrides": server_override_count,
            "active_workflow": active_workflow_count,
            "draft_workflow": draft_count,
            "in_review_workflow": in_review_count,
            "published_effective": published_effective_count,
        },
    }


def _effective_items_payload(
    workflow_service: ContentWorkflowService,
    *,
    server_code: str,
    content_type: str,
) -> dict[str, Any]:
    global_items = _list_scoped_items(
        workflow_service,
        server_scope="global",
        server_id=None,
        content_type=content_type,
    )
    server_items = _list_scoped_items(
        workflow_service,
        server_scope="server",
        server_id=server_code,
        content_type=content_type,
    )
    global_payloads = [
        _build_item_payload(
            workflow_service,
            item=item,
            server_scope="global",
            server_id=None,
        )
        for item in global_items
    ]
    server_payloads = [
        _build_item_payload(
            workflow_service,
            item=item,
            server_scope="server",
            server_id=server_code,
        )
        for item in server_items
    ]
    effective_map: dict[str, dict[str, Any]] = {}
    for item in global_payloads:
        key = _normalize_content_key(item.get("content_key"))
        if not key:
            continue
        effective_map[key] = {
            **item,
            "source_scope": "global",
            "has_server_override": False,
            "global_item_id": int(item.get("id") or 0) or None,
            "server_item_id": None,
        }
    for item in server_payloads:
        key = _normalize_content_key(item.get("content_key"))
        if not key:
            continue
        base = effective_map.get(key) or {}
        effective_map[key] = {
            **base,
            **item,
            "source_scope": "server",
            "has_server_override": True,
            "global_item_id": base.get("id") if base.get("source_scope") == "global" else base.get("global_item_id"),
            "server_item_id": int(item.get("id") or 0) or None,
        }
    effective_items = sorted(
        effective_map.values(),
        key=lambda row: (row.get("source_scope") != "server", str(row.get("title") or row.get("content_key") or "").lower()),
    )
    summary = build_content_workspace_summary(
        effective_items=effective_items,
        content_type=content_type,
    )
    return {
        "server_code": server_code,
        "content_type": content_type,
        "global_items": global_payloads,
        "server_items": server_payloads,
        "effective_items": effective_items,
        "counts": {
            "global": len(global_payloads),
            "server": len(server_payloads),
            "effective": len(effective_items),
        },
        "summary": summary,
    }


def list_server_features_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
) -> dict[str, Any]:
    normalized_server = _normalize_server_code(server_code)
    return _effective_items_payload(
        workflow_service,
        server_code=normalized_server,
        content_type="features",
    )


def list_server_templates_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
) -> dict[str, Any]:
    normalized_server = _normalize_server_code(server_code)
    return _effective_items_payload(
        workflow_service,
        server_code=normalized_server,
        content_type="templates",
    )


def _feature_payload_from_admin_item(payload: AdminCatalogItemPayload, *, content_key: str) -> dict[str, Any]:
    config = dict(payload.config or {})
    enabled = config.get("enabled")
    if not isinstance(enabled, bool):
        enabled = str(payload.status or "").strip().lower() not in {"disabled", "archived"}
    title = str(payload.title or config.get("title") or content_key).strip()
    return {
        "feature_code": str(config.get("feature_code") or payload.key or content_key).strip().lower(),
        "title": title,
        "enabled": bool(enabled),
        "rollout": config.get("rollout") or payload.audience or "server_override",
        "owner": config.get("owner") or "admin",
        "notes": config.get("notes") or payload.description or "",
        "status": str(payload.status or config.get("status") or "draft").strip().lower() or "draft",
        "order": config.get("order"),
        "hidden": bool(config.get("hidden") or False),
    }


def _template_payload_from_admin_item(payload: AdminCatalogItemPayload, *, content_key: str) -> dict[str, Any]:
    config = dict(payload.config or {})
    title = str(payload.title or config.get("title") or content_key).strip()
    body = str(config.get("body") or "").strip()
    return {
        "template_code": str(config.get("template_code") or payload.key or content_key).strip().lower(),
        "title": title,
        "body": body,
        "format": str(config.get("format") or payload.output_format or "bbcode").strip().lower() or "bbcode",
        "status": str(payload.status or config.get("status") or "draft").strip().lower() or "draft",
        "notes": config.get("notes") or payload.description or "",
    }


def _upsert_server_override(
    workflow_service: ContentWorkflowService,
    *,
    server_code: str,
    actor_user_id: int,
    request_id: str,
    content_type: str,
    content_key: str,
    title: str,
    payload_json: dict[str, Any],
) -> dict[str, Any]:
    normalized_server = _normalize_server_code(server_code)
    normalized_type = normalize_content_type(content_type)
    normalized_key = _normalize_content_key(content_key)
    existing = workflow_service.repository.get_content_item_by_identity(
        server_scope="server",
        server_id=normalized_server,
        content_type=normalized_type,
        content_key=normalized_key,
    )
    created = False
    item = existing
    if item is None:
        item = workflow_service.create_content_item(
            server_scope="server",
            server_id=normalized_server,
            content_type=normalized_type,
            content_key=normalized_key,
            title=title,
            metadata_json={"workspace": "server-centric"},
            actor_user_id=actor_user_id,
            request_id=request_id,
        )
        created = True
    result = workflow_service.create_draft_version(
        content_item_id=int(item["id"]),
        payload_json=payload_json,
        schema_version=1,
        actor_user_id=actor_user_id,
        request_id=request_id,
        server_scope="server",
        server_id=normalized_server,
        comment=f"server_workspace:{normalized_type}:{normalized_key}",
    )
    current_item = workflow_service.get_content_item(
        content_item_id=int(item["id"]),
        server_scope="server",
        server_id=normalized_server,
    )
    return {
        "ok": True,
        "created_item": created,
        "item": current_item,
        "change_request": result["change_request"],
        "version": result["version"],
    }


def save_server_feature_override_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    actor_user_id: int,
    request_id: str,
    payload: AdminCatalogItemPayload,
    feature_key: str = "",
) -> dict[str, Any]:
    normalized_key = _normalize_content_key(feature_key or payload.key or payload.feature_flag or payload.config.get("feature_code"))
    if not normalized_key:
        raise ValueError("feature_key_required")
    feature_payload = _feature_payload_from_admin_item(payload, content_key=normalized_key)
    return _upsert_server_override(
        workflow_service,
        server_code=server_code,
        actor_user_id=actor_user_id,
        request_id=request_id,
        content_type="features",
        content_key=normalized_key,
        title=str(feature_payload.get("title") or normalized_key),
        payload_json=feature_payload,
    )


def save_server_template_override_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    actor_user_id: int,
    request_id: str,
    payload: AdminCatalogItemPayload,
    template_key: str = "",
) -> dict[str, Any]:
    normalized_key = _normalize_content_key(template_key or payload.key or payload.config.get("template_code"))
    if not normalized_key:
        raise ValueError("template_key_required")
    template_payload = _template_payload_from_admin_item(payload, content_key=normalized_key)
    if not str(template_payload.get("body") or "").strip():
        raise ValueError("template_body_required")
    return _upsert_server_override(
        workflow_service,
        server_code=server_code,
        actor_user_id=actor_user_id,
        request_id=request_id,
        content_type="templates",
        content_key=normalized_key,
        title=str(template_payload.get("title") or normalized_key),
        payload_json=template_payload,
    )


def execute_server_content_workflow_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    actor_user_id: int,
    request_id: str,
    content_type: str,
    content_key: str,
    payload: AdminCatalogWorkflowPayload,
) -> dict[str, Any]:
    normalized_server = _normalize_server_code(server_code)
    normalized_type = normalize_content_type(content_type)
    normalized_key = _normalize_content_key(content_key)
    item = workflow_service.repository.get_content_item_by_identity(
        server_scope="server",
        server_id=normalized_server,
        content_type=normalized_type,
        content_key=normalized_key,
    )
    if not item:
        raise KeyError("content_item_not_found")
    result = execute_catalog_workflow_payload(
        workflow_service=workflow_service,
        server_code=normalized_server,
        actor_user_id=actor_user_id,
        request_id=request_id,
        payload=payload,
        query_change_request_id=int(payload.change_request_id or 0),
    )
    return {
        **result,
        "item_id": int(item.get("id") or 0),
        "content_key": normalized_key,
        "content_type": normalized_type,
    }


def get_server_template_item_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    template_key: str,
) -> dict[str, Any]:
    normalized_server = _normalize_server_code(server_code)
    normalized_key = _normalize_content_key(template_key)
    payload = list_server_templates_payload(
        workflow_service=workflow_service,
        server_code=normalized_server,
    )
    for item in payload["effective_items"]:
        if _normalize_content_key(item.get("content_key")) == normalized_key:
            return item
    raise KeyError("template_not_found")


def build_server_template_placeholders_payload(*, template_key: str) -> dict[str, Any]:
    normalized_key = _normalize_content_key(template_key)
    placeholders = [
        {"name": "server_code", "example": "blackberry", "description": "Код сервера"},
        {"name": "server_title", "example": "BlackBerry", "description": "Название сервера"},
        {"name": "username", "example": "admin", "description": "Имя пользователя"},
        {"name": "today_date", "example": "16.04.2026", "description": "Текущая дата"},
        {"name": "document_title", "example": "Жалоба", "description": "Название документа"},
        {"name": "result", "example": "Итоговый текст", "description": "Основной текст результата"},
    ]
    if "complaint" in normalized_key:
        placeholders.extend(
            [
                {"name": "representative_name", "example": "John Doe", "description": "Представитель"},
                {"name": "victim_name", "example": "Jane Doe", "description": "Потерпевший"},
                {"name": "situation_description", "example": "Описание ситуации", "description": "Суть жалобы"},
            ]
        )
    if "rehab" in normalized_key:
        placeholders.extend(
            [
                {"name": "principal_name", "example": "John Doe", "description": "Заявитель"},
                {"name": "principal_passport", "example": "123456", "description": "Паспорт"},
            ]
        )
    return {
        "template_key": normalized_key,
        "items": placeholders,
        "count": len(placeholders),
    }


def build_server_template_preview_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    template_key: str,
    sample_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = get_server_template_item_payload(
        workflow_service=workflow_service,
        server_code=server_code,
        template_key=template_key,
    )
    payload_json = dict(item.get("draft_payload") or item.get("effective_payload") or {})
    body = str(payload_json.get("body") or "").strip()
    samples = {
        "server_code": _normalize_server_code(server_code),
        "server_title": str(sample_json.get("server_title") or "Server") if isinstance(sample_json, dict) else "Server",
        "username": str(sample_json.get("username") or "admin") if isinstance(sample_json, dict) else "admin",
        "today_date": str(sample_json.get("today_date") or "16.04.2026") if isinstance(sample_json, dict) else "16.04.2026",
        "document_title": str(sample_json.get("document_title") or item.get("title") or "Документ") if isinstance(sample_json, dict) else str(item.get("title") or "Документ"),
        "result": str(sample_json.get("result") or "BBCode result") if isinstance(sample_json, dict) else "BBCode result",
    }
    if isinstance(sample_json, dict):
        for key, value in sample_json.items():
            samples[str(key)] = str(value)
    rendered = body
    for key, value in samples.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        rendered = rendered.replace(f"[[{key}]]", str(value))
    return {
        "template_key": _normalize_content_key(template_key),
        "source_scope": str(item.get("source_scope") or ""),
        "title": str(payload_json.get("title") or item.get("title") or ""),
        "format": str(payload_json.get("format") or "bbcode"),
        "body": body,
        "preview": rendered,
        "sample_json": samples,
    }


def reset_server_template_to_default_payload(
    *,
    workflow_service: ContentWorkflowService,
    server_code: str,
    actor_user_id: int,
    request_id: str,
    template_key: str,
) -> dict[str, Any]:
    normalized_server = _normalize_server_code(server_code)
    normalized_key = _normalize_content_key(template_key)
    global_item = workflow_service.repository.get_content_item_by_identity(
        server_scope="global",
        server_id=None,
        content_type="templates",
        content_key=normalized_key,
    )
    if not global_item:
        raise KeyError("global_template_not_found")
    global_payload = _build_item_payload(
        workflow_service,
        item=dict(global_item),
        server_scope="global",
        server_id=None,
    )
    effective_payload = dict(global_payload.get("effective_payload") or {})
    if not effective_payload:
        raise ValueError("global_template_payload_missing")
    title = str(effective_payload.get("title") or global_payload.get("title") or normalized_key)
    result = _upsert_server_override(
        workflow_service,
        server_code=normalized_server,
        actor_user_id=actor_user_id,
        request_id=request_id,
        content_type="templates",
        content_key=normalized_key,
        title=title,
        payload_json={
            **effective_payload,
            "notes": "reset_to_global_default",
        },
    )
    result["reset_source_scope"] = "global"
    return result
