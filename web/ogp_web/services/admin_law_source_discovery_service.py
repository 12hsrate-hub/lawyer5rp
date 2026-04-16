from __future__ import annotations

import hashlib
from typing import Any

from ogp_web.services.law_sources_validation import validate_source_urls
from ogp_web.storage.law_source_discovery_store import LawSourceDiscoveryStore
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore


def _resolve_target_revision(
    *,
    source_sets_store: LawSourceSetsStore,
    source_set_key: str,
    source_set_revision_id: int | None = None,
):
    normalized_key = str(source_set_key or "").strip().lower()
    if not normalized_key:
        raise ValueError("source_set_key_required")
    source_set = source_sets_store.get_source_set(source_set_key=normalized_key)
    if source_set is None:
        raise KeyError("source_set_not_found")
    if source_set_revision_id is not None:
        revision = source_sets_store.get_revision(revision_id=int(source_set_revision_id))
        if revision is None or revision.source_set_key != normalized_key:
            raise KeyError("source_set_revision_not_found")
        return source_set, revision
    revisions = source_sets_store.list_revisions(source_set_key=normalized_key)
    revision = next((item for item in revisions if item.status in {"published", "legacy_flat"}), None)
    if revision is None:
        raise ValueError("source_set_revision_not_publishable")
    return source_set, revision


def _resolve_discovery_mode(*, revision) -> str:
    status = str(revision.status or "").strip().lower()
    adapter_policy = dict(revision.adapter_policy_json or {})
    extractor = str(adapter_policy.get("extractor") or "").strip().lower()
    mode = str(adapter_policy.get("mode") or "").strip().lower()
    if status == "legacy_flat":
        return "legacy_flat"
    if mode == "passthrough":
        return "passthrough"
    if extractor in {"forum_topic", "direct_links"}:
        return "passthrough"
    raise ValueError("source_set_discovery_adapter_unsupported")


def _build_passthrough_discovery_snapshot(*, revision) -> dict[str, Any]:
    validation = validate_source_urls(list(revision.container_urls))
    invalid_details = {
        str(item.get("url") or "").strip(): str(item.get("reason") or "").strip()
        for item in validation.invalid_details
        if str(item.get("url") or "").strip()
    }
    broken_links = [
        {
            "normalized_url": raw_url,
            "source_container_url": raw_url,
            "discovery_status": "broken",
            "alias_hints_json": {},
            "metadata_json": {"reason": invalid_details.get(raw_url, "invalid_source_url")},
        }
        for raw_url in validation.invalid_urls
        if str(raw_url or "").strip()
    ]
    discovered_links = [
        {
            "normalized_url": url,
            "source_container_url": url,
            "discovery_status": "discovered",
            "alias_hints_json": {},
            "metadata_json": {},
        }
        for url in validation.accepted_urls
    ]
    duplicate_links = [
        {
            "normalized_url": url,
            "source_container_url": url,
            "discovery_status": "duplicate",
            "alias_hints_json": {},
            "metadata_json": {"duplicate": True},
        }
        for url in validation.duplicate_urls
    ]
    items = discovered_links + broken_links + duplicate_links
    fingerprint_payload = "|".join(
        f"{item['discovery_status']}::{item['normalized_url']}"
        for item in sorted(items, key=lambda entry: (entry["discovery_status"], entry["normalized_url"]))
    )
    input_fingerprint = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest() if items else ""
    return {
        "mode": _resolve_discovery_mode(revision=revision),
        "items": items,
        "summary_json": {
            "input_fingerprint": input_fingerprint,
            "total_links": len(items),
            "discovered_links": len(discovered_links),
            "broken_links": len(broken_links),
            "duplicate_links": len(duplicate_links),
        },
        "status": (
            "failed"
            if not discovered_links and broken_links
            else "partial_success"
            if broken_links or duplicate_links
            else "succeeded"
        ),
        "error_summary": "" if discovered_links or duplicate_links else "no_valid_links_discovered",
    }


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


def execute_source_set_discovery_payload(
    *,
    source_sets_store: LawSourceSetsStore,
    discovery_store: LawSourceDiscoveryStore,
    source_set_key: str,
    source_set_revision_id: int | None = None,
    trigger_mode: str = "manual",
    safe_rerun: bool = True,
) -> dict[str, Any]:
    source_set, revision = _resolve_target_revision(
        source_sets_store=source_sets_store,
        source_set_key=source_set_key,
        source_set_revision_id=source_set_revision_id,
    )
    snapshot = _build_passthrough_discovery_snapshot(revision=revision)
    latest_run = next(iter(discovery_store.list_runs_for_revision(source_set_revision_id=revision.id)), None)
    if safe_rerun and latest_run is not None:
        latest_fingerprint = str((latest_run.summary_json or {}).get("input_fingerprint") or "")
        if latest_fingerprint and latest_fingerprint == snapshot["summary_json"]["input_fingerprint"]:
            return {
                "ok": True,
                "changed": False,
                "source_set": {
                    "source_set_key": source_set.source_set_key,
                    "title": source_set.title,
                    "description": source_set.description,
                    "scope": source_set.scope,
                },
                "revision": {
                    "id": revision.id,
                    "revision": revision.revision,
                    "status": revision.status,
                    "container_urls": list(revision.container_urls),
                    "adapter_policy_json": dict(revision.adapter_policy_json),
                    "metadata_json": dict(revision.metadata_json),
                },
                "run": {
                    "id": latest_run.id,
                    "source_set_revision_id": latest_run.source_set_revision_id,
                    "source_set_key": latest_run.source_set_key,
                    "revision": latest_run.revision,
                    "trigger_mode": latest_run.trigger_mode,
                    "status": latest_run.status,
                    "summary_json": dict(latest_run.summary_json),
                    "error_summary": latest_run.error_summary,
                    "created_at": latest_run.created_at,
                    "started_at": latest_run.started_at,
                    "finished_at": latest_run.finished_at,
                },
            }

    run = discovery_store.create_run(
        source_set_revision_id=revision.id,
        trigger_mode=trigger_mode,
        status=snapshot["status"],
        summary_json=snapshot["summary_json"],
        error_summary=snapshot["error_summary"],
    )
    for item in snapshot["items"]:
        discovery_store.create_link(
            source_discovery_run_id=run.id,
            source_set_revision_id=revision.id,
            normalized_url=item["normalized_url"],
            source_container_url=item["source_container_url"],
            discovery_status=item["discovery_status"],
            alias_hints_json=item["alias_hints_json"],
            metadata_json=item["metadata_json"],
        )
    return {
        "ok": True,
        "changed": True,
        "source_set": {
            "source_set_key": source_set.source_set_key,
            "title": source_set.title,
            "description": source_set.description,
            "scope": source_set.scope,
        },
        "revision": {
            "id": revision.id,
            "revision": revision.revision,
            "status": revision.status,
            "container_urls": list(revision.container_urls),
            "adapter_policy_json": dict(revision.adapter_policy_json),
            "metadata_json": dict(revision.metadata_json),
        },
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
    }
