from __future__ import annotations

from typing import Any

from ogp_web.services.admin_law_projection_service import (
    preview_server_effective_law_projection_payload,
)
from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_server_health_payload,
    normalize_runtime_server_code,
)
from ogp_web.storage.canonical_law_document_versions_store import (
    CanonicalLawDocumentVersionsStore,
)
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.runtime_servers_store import RuntimeServersStore
from ogp_web.storage.server_effective_law_projections_store import (
    ServerEffectiveLawProjectionItemRecord,
    ServerEffectiveLawProjectionRunRecord,
    ServerEffectiveLawProjectionsStore,
)


def _serialize_binding(binding: Any) -> dict[str, Any]:
    include_law_keys = getattr(binding, "include_law_keys", [])
    exclude_law_keys = getattr(binding, "exclude_law_keys", [])
    pin_policy_json = getattr(binding, "pin_policy_json", {})
    metadata_json = getattr(binding, "metadata_json", {})
    return {
        "id": int(binding.id),
        "server_code": str(binding.server_code or ""),
        "source_set_key": str(binding.source_set_key or ""),
        "priority": int(binding.priority or 0),
        "is_active": bool(binding.is_active),
        "include_law_keys": [str(item or "") for item in list(include_law_keys or []) if str(item or "").strip()],
        "exclude_law_keys": [str(item or "") for item in list(exclude_law_keys or []) if str(item or "").strip()],
        "pin_policy_json": dict(pin_policy_json or {}),
        "metadata_json": dict(metadata_json or {}),
        "created_at": str(getattr(binding, "created_at", "") or ""),
        "updated_at": str(getattr(binding, "updated_at", "") or ""),
    }


def _serialize_run(run: ServerEffectiveLawProjectionRunRecord | None) -> dict[str, Any] | None:
    if run is None:
        return None
    summary_json = dict(run.summary_json or {})
    return {
        "id": int(run.id),
        "server_code": str(run.server_code or ""),
        "trigger_mode": str(run.trigger_mode or "manual"),
        "status": str(run.status or "preview"),
        "summary_json": summary_json,
        "decision_status": str(summary_json.get("decision_status") or ""),
        "selected_count": int(summary_json.get("selected_count") or 0),
        "candidate_count": int(summary_json.get("candidate_count") or 0),
        "created_at": str(run.created_at or ""),
    }


def _latest_projection_runs(
    projections_store: ServerEffectiveLawProjectionsStore,
    *,
    server_code: str,
) -> tuple[ServerEffectiveLawProjectionRunRecord | None, ServerEffectiveLawProjectionRunRecord | None]:
    runs = projections_store.list_runs(server_code=server_code)
    current = runs[0] if runs else None
    previous = runs[1] if len(runs) > 1 else None
    return current, previous


def _safe_excerpt(text: str, *, limit: int = 220) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _diff_summary(
    current_items: list[ServerEffectiveLawProjectionItemRecord],
    previous_items: list[ServerEffectiveLawProjectionItemRecord],
) -> dict[str, Any]:
    current_map = {
        str(item.canonical_identity_key or "").strip().lower(): int(item.selected_document_version_id)
        for item in current_items
        if str(item.canonical_identity_key or "").strip()
    }
    previous_map = {
        str(item.canonical_identity_key or "").strip().lower(): int(item.selected_document_version_id)
        for item in previous_items
        if str(item.canonical_identity_key or "").strip()
    }
    current_keys = set(current_map)
    previous_keys = set(previous_map)
    shared = current_keys & previous_keys
    added = current_keys - previous_keys
    removed = previous_keys - current_keys
    changed = {key for key in shared if current_map.get(key) != previous_map.get(key)}
    unchanged = shared - changed
    errored = sum(1 for item in current_items if str(item.status or "").strip().lower() != "candidate")
    return {
        "baseline_run_id": None,
        "current_run_id": None,
        "added": len(added),
        "removed": len(removed),
        "changed": len(changed),
        "unchanged": len(unchanged),
        "errored": int(errored),
    }


def _effective_items_payload(
    *,
    projections_store: ServerEffectiveLawProjectionsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
    run: ServerEffectiveLawProjectionRunRecord | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if run is None:
        return [], {
            "run": None,
            "count": 0,
            "with_content": 0,
            "missing_content": 0,
            "error_count": 0,
            "last_updated_at": "",
        }
    items = projections_store.list_items(projection_run_id=int(run.id))
    payload_items: list[dict[str, Any]] = []
    with_content = 0
    missing_content = 0
    error_count = 0
    last_updated_at = ""
    for item in items:
        version = versions_store.get_version(version_id=int(item.selected_document_version_id))
        title = ""
        preview_text = ""
        updated_at = ""
        fetch_status = "missing"
        parse_status = "missing"
        has_content = False
        if version is not None:
            title = str(
                version.parsed_title
                or version.raw_title
                or version.display_title
                or item.canonical_identity_key
                or item.normalized_url
                or ""
            ).strip()
            preview_text = _safe_excerpt(version.body_text)
            updated_at = str(version.updated_at or "")
            fetch_status = str(version.fetch_status or "missing")
            parse_status = str(version.parse_status or "missing")
            has_content = bool(str(version.body_text or "").strip())
            if updated_at and updated_at > last_updated_at:
                last_updated_at = updated_at
        if has_content:
            with_content += 1
        else:
            missing_content += 1
        if fetch_status == "failed" or parse_status == "failed" or version is None:
            error_count += 1
        payload_items.append(
            {
                "projection_item_id": int(item.id),
                "canonical_identity_key": str(item.canonical_identity_key or ""),
                "title": title or str(item.canonical_identity_key or item.normalized_url or "—"),
                "normalized_url": str(item.normalized_url or ""),
                "selected_document_version_id": int(item.selected_document_version_id or 0),
                "selected_source_set_key": str(item.selected_source_set_key or ""),
                "selected_revision": int(item.selected_revision or 0),
                "precedence_rank": int(item.precedence_rank or 0),
                "status": str(item.status or "candidate"),
                "has_content": has_content,
                "preview_excerpt": preview_text,
                "updated_at": updated_at,
                "fetch_status": fetch_status,
                "parse_status": parse_status,
                "contributor_count": int(item.contributor_count or 0),
                "provenance_json": dict(item.provenance_json or {}),
            }
        )
    return payload_items, {
        "run": _serialize_run(run),
        "count": len(payload_items),
        "with_content": with_content,
        "missing_content": missing_content,
        "error_count": error_count,
        "last_updated_at": last_updated_at,
    }


def build_server_laws_summary_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    health_payload = build_runtime_server_health_payload(
        server_code=normalized_server,
        runtime_servers_store=runtime_servers_store,
        law_sets_store=law_sets_store,
        projections_store=projections_store,
    )
    bindings = [
        _serialize_binding(item)
        for item in source_sets_store.list_bindings(server_code=normalized_server)
    ]
    current_run, previous_run = _latest_projection_runs(projections_store, server_code=normalized_server)
    _, fill_summary = _effective_items_payload(
        projections_store=projections_store,
        versions_store=versions_store,
        run=current_run,
    )
    current_items = projections_store.list_items(projection_run_id=int(current_run.id)) if current_run is not None else []
    previous_items = projections_store.list_items(projection_run_id=int(previous_run.id)) if previous_run is not None else []
    diff_summary = _diff_summary(current_items, previous_items)
    diff_summary["current_run_id"] = int(current_run.id) if current_run is not None else None
    diff_summary["baseline_run_id"] = int(previous_run.id) if previous_run is not None else None
    return {
        "server_code": normalized_server,
        "bindings": bindings,
        "binding_count": len(bindings),
        "health": dict((health_payload.get("checks") or {}).get("health") or {}),
        "projection_bridge": dict(health_payload.get("projection_bridge") or {}),
        "runtime_provenance": dict(health_payload.get("runtime_provenance") or {}),
        "latest_projection_run": _serialize_run(current_run),
        "fill_check": fill_summary,
        "diff": diff_summary,
    }


def build_server_effective_laws_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    projections_store: ServerEffectiveLawProjectionsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    current_run, _ = _latest_projection_runs(projections_store, server_code=normalized_server)
    items, summary = _effective_items_payload(
        projections_store=projections_store,
        versions_store=versions_store,
        run=current_run,
    )
    return {
        "server_code": normalized_server,
        "run": summary.get("run"),
        "items": items,
        "count": int(summary.get("count") or 0),
        "summary": {
            "with_content": int(summary.get("with_content") or 0),
            "missing_content": int(summary.get("missing_content") or 0),
            "error_count": int(summary.get("error_count") or 0),
            "last_updated_at": str(summary.get("last_updated_at") or ""),
        },
    }


def run_server_laws_refresh_preview_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
    trigger_mode: str = "manual",
    safe_rerun: bool = True,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    previous_run, _ = _latest_projection_runs(projections_store, server_code=normalized_server)
    result = preview_server_effective_law_projection_payload(
        source_sets_store=source_sets_store,
        versions_store=versions_store,
        projections_store=projections_store,
        server_code=normalized_server,
        trigger_mode=trigger_mode,
        safe_rerun=safe_rerun,
    )
    current_run_id = int(((result.get("run") or {}).get("id") or 0))
    current_items = projections_store.list_items(projection_run_id=current_run_id) if current_run_id > 0 else []
    previous_items = (
        projections_store.list_items(projection_run_id=int(previous_run.id))
        if previous_run is not None and int(previous_run.id) != current_run_id
        else []
    )
    diff_summary = _diff_summary(current_items, previous_items)
    diff_summary["current_run_id"] = current_run_id or None
    diff_summary["baseline_run_id"] = int(previous_run.id) if previous_run is not None and int(previous_run.id) != current_run_id else None
    return {
        **result,
        "server_code": normalized_server,
        "diff": diff_summary,
    }


def build_server_laws_recheck_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    projections_store: ServerEffectiveLawProjectionsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    current_run, _ = _latest_projection_runs(projections_store, server_code=normalized_server)
    items, summary = _effective_items_payload(
        projections_store=projections_store,
        versions_store=versions_store,
        run=current_run,
    )
    return {
        "server_code": normalized_server,
        "run": summary.get("run"),
        "summary": {
            "count": int(summary.get("count") or 0),
            "with_content": int(summary.get("with_content") or 0),
            "missing_content": int(summary.get("missing_content") or 0),
            "error_count": int(summary.get("error_count") or 0),
            "last_updated_at": str(summary.get("last_updated_at") or ""),
        },
        "items": items,
    }


def build_server_laws_diff_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    projections_store: ServerEffectiveLawProjectionsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    current_run, previous_run = _latest_projection_runs(projections_store, server_code=normalized_server)
    current_items = projections_store.list_items(projection_run_id=int(current_run.id)) if current_run is not None else []
    previous_items = projections_store.list_items(projection_run_id=int(previous_run.id)) if previous_run is not None else []
    diff_summary = _diff_summary(current_items, previous_items)
    diff_summary["current_run_id"] = int(current_run.id) if current_run is not None else None
    diff_summary["baseline_run_id"] = int(previous_run.id) if previous_run is not None else None
    return {
        "server_code": normalized_server,
        "current_run": _serialize_run(current_run),
        "baseline_run": _serialize_run(previous_run),
        "summary": diff_summary,
    }
