from __future__ import annotations

from typing import Any

from ogp_web.storage.law_source_discovery_store import LawSourceDiscoveryStore
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore


def list_source_set_discovery_runs_payload(
    *,
    source_sets_store: LawSourceSetsStore,
    discovery_store: LawSourceDiscoveryStore,
    source_set_key: str,
) -> dict[str, Any]:
    normalized_key = str(source_set_key or "").strip().lower()
    if not normalized_key:
        raise ValueError("source_set_key_required")
    source_set = source_sets_store.get_source_set(source_set_key=normalized_key)
    if source_set is None:
        raise KeyError("source_set_not_found")
    items = [
        {
            "id": item.id,
            "source_set_revision_id": item.source_set_revision_id,
            "source_set_key": item.source_set_key,
            "revision": item.revision,
            "trigger_mode": item.trigger_mode,
            "status": item.status,
            "summary_json": dict(item.summary_json),
            "error_summary": item.error_summary,
            "created_at": item.created_at,
            "started_at": item.started_at,
            "finished_at": item.finished_at,
        }
        for item in discovery_store.list_runs(source_set_key=normalized_key)
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
        "items": items,
        "count": len(items),
    }


def list_discovery_run_links_payload(
    *,
    discovery_store: LawSourceDiscoveryStore,
    run_id: int,
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("source_discovery_run_id_required")
    run = discovery_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("source_discovery_run_not_found")
    items = [
        {
            "id": item.id,
            "source_discovery_run_id": item.source_discovery_run_id,
            "source_set_revision_id": item.source_set_revision_id,
            "normalized_url": item.normalized_url,
            "source_container_url": item.source_container_url,
            "discovery_status": item.discovery_status,
            "alias_hints_json": dict(item.alias_hints_json),
            "metadata_json": dict(item.metadata_json),
            "first_seen_at": item.first_seen_at,
            "last_seen_at": item.last_seen_at,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in discovery_store.list_links(source_discovery_run_id=int(run_id))
    ]
    return {
        "run": {
            "id": run.id,
            "source_set_revision_id": run.source_set_revision_id,
            "source_set_key": run.source_set_key,
            "revision": run.revision,
            "trigger_mode": run.trigger_mode,
            "status": run.status,
            "summary_json": dict(run.summary_json),
            "error_summary": run.error_summary,
            "created_at": run.created_at,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        },
        "items": items,
        "count": len(items),
    }
