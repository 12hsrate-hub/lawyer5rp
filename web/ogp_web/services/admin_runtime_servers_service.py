from __future__ import annotations

from typing import Any

from ogp_web.services.law_bundle_service import load_law_bundle_meta
from ogp_web.services.law_version_service import resolve_active_law_version
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.runtime_servers_store import RuntimeServerRecord, RuntimeServersStore


def normalize_runtime_server_code(value: str) -> str:
    return str(value or "").strip().lower()


def list_runtime_servers_payload(*, store: RuntimeServersStore) -> dict[str, Any]:
    items = [store.to_payload(record) for record in store.list_servers()]
    return {"items": items, "count": len(items)}


def create_runtime_server_payload(*, store: RuntimeServersStore, code: str, title: str) -> dict[str, Any]:
    row = store.create_server(code=code, title=title)
    return {"item": store.to_payload(row)}


def update_runtime_server_payload(*, store: RuntimeServersStore, code: str, title: str) -> dict[str, Any]:
    row = store.update_server(code=code, title=title)
    return {"item": store.to_payload(row)}


def set_runtime_server_active_payload(*, store: RuntimeServersStore, code: str, is_active: bool) -> dict[str, Any]:
    row = store.set_active(code=code, is_active=is_active)
    return {"item": store.to_payload(row)}


def build_runtime_server_health_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
) -> dict[str, Any]:
    normalized_code = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_code)
    law_sets = law_sets_store.list_law_sets(server_code=normalized_code)
    active_law_set = next((item for item in law_sets if item.get("is_published")), None)
    if active_law_set is None:
        active_law_set = next((item for item in law_sets if item.get("is_active")), None)
    bindings = law_sets_store.list_server_law_bindings(server_code=normalized_code)
    active_law_version = resolve_active_law_version(server_code=normalized_code)
    bundle_meta = load_law_bundle_meta(normalized_code)
    chunk_count = int(
        (bundle_meta.chunk_count if bundle_meta and bundle_meta.chunk_count is not None else None)
        or (active_law_version.chunk_count if active_law_version and active_law_version.chunk_count is not None else 0)
        or 0
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
    return {
        "server_code": normalized_code,
        "checks": checks,
        "summary": {
            "ready_count": ready_count,
            "total_count": len(checks),
            "is_ready": ready_count == len(checks),
        },
    }
