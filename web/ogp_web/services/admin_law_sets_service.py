from __future__ import annotations

from typing import Any

from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore


def list_runtime_server_law_sets_payload(*, store: RuntimeLawSetsStore, server_code: str) -> dict[str, Any]:
    normalized_code = _normalize_server_code(server_code)
    items = store.list_law_sets(server_code=normalized_code)
    return {"server_code": normalized_code, "items": items, "count": len(items)}


def list_runtime_server_law_bindings_payload(*, store: RuntimeLawSetsStore, server_code: str) -> dict[str, Any]:
    normalized_code = _normalize_server_code(server_code)
    items = store.list_server_law_bindings(server_code=normalized_code)
    return {"server_code": normalized_code, "items": items, "count": len(items)}


def add_runtime_server_law_binding_payload(
    *,
    store: RuntimeLawSetsStore,
    server_code: str,
    law_code: str,
    source_id: int,
    effective_from: str = "",
    priority: int = 100,
    law_set_id: int | None = None,
) -> dict[str, Any]:
    normalized_code = _normalize_server_code(server_code)
    item = store.add_server_law_binding(
        server_code=normalized_code,
        law_code=law_code,
        source_id=source_id,
        effective_from=effective_from,
        priority=priority,
        law_set_id=law_set_id,
    )
    return {"server_code": normalized_code, "item": item}


def create_runtime_server_law_set_payload(
    *,
    store: RuntimeLawSetsStore,
    server_code: str,
    name: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_code = _normalize_server_code(server_code)
    law_set = store.create_law_set(server_code=normalized_code, name=name)
    created_items = store.replace_law_set_items(
        law_set_id=int(law_set.get("id") or 0),
        items=items,
    )
    return {"server_code": normalized_code, "law_set": law_set, "items": created_items}


def update_law_set_payload(
    *,
    store: RuntimeLawSetsStore,
    law_set_id: int,
    name: str,
    is_active: bool,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    law_set = store.update_law_set(law_set_id=law_set_id, name=name, is_active=is_active)
    updated_items = store.replace_law_set_items(law_set_id=law_set_id, items=items)
    return {"law_set": law_set, "items": updated_items}


def publish_law_set_payload(*, store: RuntimeLawSetsStore, law_set_id: int) -> dict[str, Any]:
    law_set = store.publish_law_set(law_set_id=law_set_id)
    return {"law_set": law_set}


def resolve_law_set_rebuild_context(*, store: RuntimeLawSetsStore, law_set_id: int) -> dict[str, Any]:
    server_code, source_urls = store.list_source_urls_for_law_set(law_set_id=law_set_id)
    if not source_urls:
        raise ValueError("law_set_sources_empty")
    return {"law_set_id": law_set_id, "server_code": server_code, "source_urls": source_urls}


def resolve_law_set_rollback_context(*, store: RuntimeLawSetsStore, law_set_id: int) -> dict[str, Any]:
    server_code, _ = store.list_source_urls_for_law_set(law_set_id=law_set_id)
    return {"law_set_id": law_set_id, "server_code": server_code}


def list_law_source_registry_payload(*, store: RuntimeLawSetsStore) -> dict[str, Any]:
    items = [record.__dict__ for record in store.list_sources()]
    return {"items": items, "count": len(items)}


def create_law_source_registry_payload(
    *,
    store: RuntimeLawSetsStore,
    name: str,
    kind: str,
    url: str,
) -> dict[str, Any]:
    row = store.create_source(name=name, kind=kind, url=url)
    return {"item": row.__dict__}


def update_law_source_registry_payload(
    *,
    store: RuntimeLawSetsStore,
    source_id: int,
    name: str,
    kind: str,
    url: str,
    is_active: bool,
) -> dict[str, Any]:
    row = store.update_source(source_id=source_id, name=name, kind=kind, url=url, is_active=is_active)
    return {"item": row.__dict__}


def _normalize_server_code(value: str) -> str:
    return str(value or "").strip().lower()
