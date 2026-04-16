from __future__ import annotations

from typing import Any

from ogp_web.storage.law_source_sets_store import LawSourceSetsStore


def list_source_sets_payload(*, store: LawSourceSetsStore) -> dict[str, Any]:
    items = [
        {
            "source_set_key": item.source_set_key,
            "title": item.title,
            "description": item.description,
            "scope": item.scope,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in store.list_source_sets()
    ]
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
    revisions = [
        {
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
        for item in store.list_revisions(source_set_key=normalized_key)
    ]
    return {
        "source_set": {
            "source_set_key": source_set.source_set_key,
            "title": source_set.title,
            "description": source_set.description,
            "scope": source_set.scope,
            "created_at": source_set.created_at,
            "updated_at": source_set.updated_at,
        },
        "items": revisions,
        "count": len(revisions),
    }


def list_server_source_set_bindings_payload(*, store: LawSourceSetsStore, server_code: str) -> dict[str, Any]:
    normalized_server = str(server_code or "").strip().lower()
    if not normalized_server:
        raise ValueError("server_code_required")
    items = [
        {
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
        for item in store.list_bindings(server_code=normalized_server)
    ]
    return {
        "server_code": normalized_server,
        "items": items,
        "count": len(items),
    }
