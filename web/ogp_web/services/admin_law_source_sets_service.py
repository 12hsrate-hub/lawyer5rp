from __future__ import annotations

from typing import Any

from ogp_web.storage.law_source_sets_store import LawSourceSetsStore


def _serialize_source_set(item: Any) -> dict[str, Any]:
    return {
        "source_set_key": item.source_set_key,
        "title": item.title,
        "description": item.description,
        "scope": item.scope,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _serialize_revision(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "source_set_key": item.source_set_key,
        "revision": item.revision,
        "status": item.status,
        "container_urls": list(item.container_urls),
        "adapter_policy_json": dict(item.adapter_policy_json),
        "metadata_json": dict(item.metadata_json),
        "created_at": item.created_at,
        "published_at": item.published_at,
    }


def _serialize_binding(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "server_code": item.server_code,
        "source_set_key": item.source_set_key,
        "priority": item.priority,
        "is_active": item.is_active,
        "include_law_keys": list(item.include_law_keys),
        "exclude_law_keys": list(item.exclude_law_keys),
        "pin_policy_json": dict(item.pin_policy_json),
        "metadata_json": dict(item.metadata_json),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def create_source_set_payload(
    *,
    store: LawSourceSetsStore,
    source_set_key: str,
    title: str,
    description: str = "",
    scope: str = "global",
) -> dict[str, Any]:
    item = store.create_source_set(
        source_set_key=source_set_key,
        title=title,
        description=description,
        scope=scope,
    )
    return {"item": _serialize_source_set(item)}


def update_source_set_payload(
    *,
    store: LawSourceSetsStore,
    source_set_key: str,
    title: str,
    description: str = "",
) -> dict[str, Any]:
    item = store.update_source_set(
        source_set_key=source_set_key,
        title=title,
        description=description,
    )
    return {"item": _serialize_source_set(item)}


def create_source_set_revision_payload(
    *,
    store: LawSourceSetsStore,
    source_set_key: str,
    container_urls: list[str],
    adapter_policy_json: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
    status: str = "draft",
) -> dict[str, Any]:
    item = store.create_revision(
        source_set_key=source_set_key,
        container_urls=container_urls,
        adapter_policy_json=adapter_policy_json,
        metadata_json=metadata_json,
        status=status,
    )
    return {"item": _serialize_revision(item)}


def create_server_source_set_binding_payload(
    *,
    store: LawSourceSetsStore,
    server_code: str,
    source_set_key: str,
    priority: int = 100,
    is_active: bool = True,
    include_law_keys: list[str] | None = None,
    exclude_law_keys: list[str] | None = None,
    pin_policy_json: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = store.create_binding(
        server_code=server_code,
        source_set_key=source_set_key,
        priority=priority,
        is_active=is_active,
        include_law_keys=include_law_keys,
        exclude_law_keys=exclude_law_keys,
        pin_policy_json=pin_policy_json,
        metadata_json=metadata_json,
    )
    return {"item": _serialize_binding(item)}


def update_server_source_set_binding_payload(
    *,
    store: LawSourceSetsStore,
    server_code: str,
    binding_id: int,
    source_set_key: str,
    priority: int = 100,
    is_active: bool = True,
    include_law_keys: list[str] | None = None,
    exclude_law_keys: list[str] | None = None,
    pin_policy_json: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = store.update_binding(
        binding_id=binding_id,
        server_code=server_code,
        source_set_key=source_set_key,
        priority=priority,
        is_active=is_active,
        include_law_keys=include_law_keys,
        exclude_law_keys=exclude_law_keys,
        pin_policy_json=pin_policy_json,
        metadata_json=metadata_json,
    )
    return {"item": _serialize_binding(item)}


def list_source_sets_payload(*, store: LawSourceSetsStore) -> dict[str, Any]:
    items = [_serialize_source_set(item) for item in store.list_source_sets()]
    return {
        "items": items,
        "count": len(items),
    }


def list_source_set_revisions_payload(*, store: LawSourceSetsStore, source_set_key: str) -> dict[str, Any]:
    normalized_key = str(source_set_key or "").strip().lower()
    if not normalized_key:
        raise ValueError("source_set_key_required")
    source_set = store.get_source_set(source_set_key=normalized_key)
    if source_set is None:
        raise KeyError("source_set_not_found")
    revisions = [_serialize_revision(item) for item in store.list_revisions(source_set_key=normalized_key)]
    return {
        "source_set": _serialize_source_set(source_set),
        "items": revisions,
        "count": len(revisions),
    }


def list_server_source_set_bindings_payload(*, store: LawSourceSetsStore, server_code: str) -> dict[str, Any]:
    normalized_server = str(server_code or "").strip().lower()
    if not normalized_server:
        raise ValueError("server_code_required")
    items = [_serialize_binding(item) for item in store.list_bindings(server_code=normalized_server)]
    return {
        "server_code": normalized_server,
        "items": items,
        "count": len(items),
    }
