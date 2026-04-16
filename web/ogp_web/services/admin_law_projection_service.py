from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from urllib.parse import urlsplit
from typing import Any

from ogp_web.storage.canonical_law_document_versions_store import (
    CanonicalLawDocumentVersionRecord,
    CanonicalLawDocumentVersionsStore,
)
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore, ServerSourceSetBindingRecord
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.server_effective_law_projections_store import (
    ServerEffectiveLawProjectionsStore,
)


def _normalize_server_code(value: str) -> str:
    return str(value or "").strip().lower()


def _binding_allows(binding: ServerSourceSetBindingRecord, version: CanonicalLawDocumentVersionRecord) -> bool:
    keys = {
        str(version.canonical_identity_key or "").strip().lower(),
        str(version.normalized_url or "").strip().lower(),
    }
    include = {str(item or "").strip().lower() for item in binding.include_law_keys if str(item or "").strip()}
    exclude = {str(item or "").strip().lower() for item in binding.exclude_law_keys if str(item or "").strip()}
    if include and not (keys & include):
        return False
    if exclude and (keys & exclude):
        return False
    return True


def _fingerprint(*, server_code: str, bindings: list[ServerSourceSetBindingRecord], versions: list[CanonicalLawDocumentVersionRecord]) -> str:
    payload = {
        "server_code": server_code,
        "bindings": [
            {
                "source_set_key": binding.source_set_key,
                "priority": binding.priority,
                "include": list(binding.include_law_keys),
                "exclude": list(binding.exclude_law_keys),
                "pin_policy_json": dict(binding.pin_policy_json),
            }
            for binding in bindings
        ],
        "versions": [
            {
                "id": version.id,
                "canonical_identity_key": version.canonical_identity_key,
                "source_set_key": version.source_set_key,
                "revision": version.revision,
                "updated_at": version.updated_at,
            }
            for version in versions
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _version_sort_key(binding: ServerSourceSetBindingRecord, version: CanonicalLawDocumentVersionRecord) -> tuple[Any, ...]:
    return (
        int(binding.priority),
        -int(version.revision),
        str(version.source_set_key or "").strip().lower(),
        -int(version.id),
    )


def _source_name_for_url(url: str) -> str:
    normalized_url = str(url or "").strip()
    host = str(urlsplit(normalized_url).netloc or "").strip().lower()
    if host:
        return f"Projection source {host}"
    return "Projection source"


def _next_materialization_name(*, run_id: int, previous_attempts: int) -> str:
    attempt = int(previous_attempts) + 1
    return f"Projection candidate #{int(run_id)}.{attempt}"


def _contributors_payload(
    *,
    candidates: list[tuple[ServerSourceSetBindingRecord, CanonicalLawDocumentVersionRecord]],
    selected_version_id: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for binding, version in candidates:
        items.append(
            {
                "document_version_id": int(version.id),
                "source_set_key": str(version.source_set_key or ""),
                "revision": int(version.revision),
                "binding_priority": int(binding.priority),
                "selected": int(version.id) == int(selected_version_id),
                "normalized_url": str(version.normalized_url or ""),
            }
        )
    return items


def list_server_effective_law_projection_runs_payload(
    *,
    projections_store: ServerEffectiveLawProjectionsStore,
    server_code: str,
) -> dict[str, Any]:
    normalized_server = _normalize_server_code(server_code)
    items = [
        {
            "id": item.id,
            "server_code": item.server_code,
            "trigger_mode": item.trigger_mode,
            "status": item.status,
            "summary_json": dict(item.summary_json),
            "created_at": item.created_at,
        }
        for item in projections_store.list_runs(server_code=normalized_server)
    ]
    return {"server_code": normalized_server, "items": items, "count": len(items)}


def list_server_effective_law_projection_items_payload(
    *,
    projections_store: ServerEffectiveLawProjectionsStore,
    run_id: int,
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("server_effective_law_projection_run_id_required")
    run = projections_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("server_effective_law_projection_run_not_found")
    items = [
        {
            "id": item.id,
            "projection_run_id": item.projection_run_id,
            "canonical_law_document_id": item.canonical_law_document_id,
            "canonical_identity_key": item.canonical_identity_key,
            "normalized_url": item.normalized_url,
            "selected_document_version_id": item.selected_document_version_id,
            "selected_source_set_key": item.selected_source_set_key,
            "selected_revision": item.selected_revision,
            "precedence_rank": item.precedence_rank,
            "contributor_count": item.contributor_count,
            "status": item.status,
            "provenance_json": dict(item.provenance_json),
            "created_at": item.created_at,
        }
        for item in projections_store.list_items(projection_run_id=int(run_id))
    ]
    return {
        "run": {
            "id": run.id,
            "server_code": run.server_code,
            "trigger_mode": run.trigger_mode,
            "status": run.status,
            "summary_json": dict(run.summary_json),
            "created_at": run.created_at,
        },
        "items": items,
        "count": len(items),
    }


def get_server_effective_law_projection_status_payload(
    *,
    projections_store: ServerEffectiveLawProjectionsStore,
    runtime_law_sets_store: RuntimeLawSetsStore,
    active_law_version: Any,
    run_id: int,
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("server_effective_law_projection_run_id_required")
    run = projections_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("server_effective_law_projection_run_not_found")
    items = projections_store.list_items(projection_run_id=int(run_id))
    summary_json = dict(run.summary_json or {})
    materialization = dict(summary_json.get("materialization") or {})
    activation = dict(summary_json.get("activation") or {})
    law_set_id = int(materialization.get("law_set_id") or 0)
    law_set_detail = None
    if law_set_id > 0:
        law_set_detail = runtime_law_sets_store.get_law_set_detail(law_set_id=law_set_id)
    active_payload = None
    if active_law_version is not None:
        active_payload = {
            "id": int(active_law_version.id),
            "server_code": str(active_law_version.server_code or ""),
            "generated_at_utc": str(active_law_version.generated_at_utc or ""),
            "effective_from": str(active_law_version.effective_from or ""),
            "effective_to": str(active_law_version.effective_to or ""),
            "fingerprint": str(active_law_version.fingerprint or ""),
            "chunk_count": int(active_law_version.chunk_count or 0),
        }
    materialized_item_count = len((law_set_detail or {}).get("items") or [])
    projection_item_count = len(items)
    runtime_alignment = {
        "projection_item_count": projection_item_count,
        "materialized_item_count": materialized_item_count,
        "item_count_matches_materialization": law_set_detail is not None and materialized_item_count == projection_item_count,
        "activation_law_version_matches_active": bool(active_payload)
        and int(activation.get("law_version_id") or 0) > 0
        and int(activation.get("law_version_id") or 0) == int(active_payload.get("id") or 0),
    }
    return {
        "run": {
            "id": run.id,
            "server_code": run.server_code,
            "trigger_mode": run.trigger_mode,
            "status": run.status,
            "summary_json": summary_json,
            "created_at": run.created_at,
        },
        "materialization": materialization,
        "activation": activation,
        "law_set_detail": law_set_detail,
        "active_law_version": active_payload,
        "runtime_alignment": runtime_alignment,
    }


def decide_server_effective_law_projection_payload(
    *,
    projections_store: ServerEffectiveLawProjectionsStore,
    run_id: int,
    status: str,
    decided_by: str,
    reason: str = "",
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("server_effective_law_projection_run_id_required")
    run = projections_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("server_effective_law_projection_run_not_found")
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in {"approved", "held"}:
        raise ValueError("server_effective_law_projection_status_invalid")
    updated_summary = dict(run.summary_json or {})
    updated_summary.update(
        {
            "decision_status": normalized_status,
            "decision_reason": str(reason or "").strip(),
            "decided_by": str(decided_by or "").strip(),
        }
    )
    updated = projections_store.update_run_status(
        run_id=int(run_id),
        status=normalized_status,
        summary_json=updated_summary,
    )
    return {
        "ok": True,
        "run": {
            "id": updated.id,
            "server_code": updated.server_code,
            "trigger_mode": updated.trigger_mode,
            "status": updated.status,
            "summary_json": dict(updated.summary_json),
            "created_at": updated.created_at,
        },
    }


def materialize_server_effective_law_projection_payload(
    *,
    projections_store: ServerEffectiveLawProjectionsStore,
    runtime_law_sets_store: RuntimeLawSetsStore,
    run_id: int,
    materialized_by: str,
    safe_rerun: bool = True,
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("server_effective_law_projection_run_id_required")
    run = projections_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("server_effective_law_projection_run_not_found")
    if str(run.status or "").strip().lower() != "approved":
        raise ValueError("server_effective_law_projection_run_not_approved")

    summary_json = dict(run.summary_json or {})
    materialization = dict(summary_json.get("materialization") or {})
    if safe_rerun and int(materialization.get("law_set_id") or 0) > 0:
        return {
            "ok": True,
            "changed": False,
            "reused_law_set": True,
            "run": {
                "id": run.id,
                "server_code": run.server_code,
                "trigger_mode": run.trigger_mode,
                "status": run.status,
                "summary_json": summary_json,
                "created_at": run.created_at,
            },
            "materialization": materialization,
        }

    items = projections_store.list_items(projection_run_id=int(run_id))
    if not items:
        raise ValueError("server_effective_law_projection_items_missing")

    sources_by_url = {
        str(source.url or "").strip(): source
        for source in runtime_law_sets_store.list_sources()
        if str(source.url or "").strip()
    }
    runtime_items: list[dict[str, Any]] = []
    created_source_ids: list[int] = []
    for item in items:
        normalized_url = str(item.normalized_url or "").strip()
        if not normalized_url:
            raise ValueError("server_effective_law_projection_item_url_required")
        source = sources_by_url.get(normalized_url)
        if source is None:
            source = runtime_law_sets_store.create_source(
                name=_source_name_for_url(normalized_url),
                kind="url",
                url=normalized_url,
            )
            sources_by_url[normalized_url] = source
            created_source_ids.append(int(source.id))
        runtime_items.append(
            {
                "law_code": str(item.canonical_identity_key or "").strip(),
                "effective_from": "",
                "priority": int(item.precedence_rank or 100),
                "source_id": int(source.id),
            }
        )

    previous_attempts = int(summary_json.get("materialization_attempts") or 0)
    law_set_name = _next_materialization_name(run_id=int(run.id), previous_attempts=previous_attempts)
    created_law_set = runtime_law_sets_store.create_law_set(
        server_code=run.server_code,
        name=law_set_name,
    )
    law_set_id = int(created_law_set.get("id") or 0)
    materialized_items = runtime_law_sets_store.replace_law_set_items(
        law_set_id=law_set_id,
        items=runtime_items,
    )
    updated_law_set = runtime_law_sets_store.update_law_set(
        law_set_id=law_set_id,
        name=law_set_name,
        is_active=False,
    )
    materialization_payload = {
        "law_set_id": law_set_id,
        "law_set_name": str(updated_law_set.get("name") or law_set_name),
        "item_count": len(materialized_items),
        "created_source_ids": created_source_ids,
        "materialized_by": str(materialized_by or "").strip(),
    }
    summary_json.update(
        {
            "materialization": materialization_payload,
            "materialization_attempts": previous_attempts + 1,
        }
    )
    updated_run = projections_store.update_run_status(
        run_id=int(run.id),
        status=run.status,
        summary_json=summary_json,
    )
    return {
        "ok": True,
        "changed": True,
        "reused_law_set": False,
        "run": {
            "id": updated_run.id,
            "server_code": updated_run.server_code,
            "trigger_mode": updated_run.trigger_mode,
            "status": updated_run.status,
            "summary_json": dict(updated_run.summary_json),
            "created_at": updated_run.created_at,
        },
        "law_set": dict(updated_law_set),
        "items": list(materialized_items),
        "count": len(materialized_items),
        "materialization": materialization_payload,
    }


def activate_server_effective_law_projection_payload(
    *,
    projections_store: ServerEffectiveLawProjectionsStore,
    runtime_law_sets_store: RuntimeLawSetsStore,
    law_admin_service: Any,
    run_id: int,
    actor_user_id: int,
    request_id: str,
    activated_by: str,
    safe_rerun: bool = True,
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("server_effective_law_projection_run_id_required")
    run = projections_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("server_effective_law_projection_run_not_found")
    if str(run.status or "").strip().lower() != "approved":
        raise ValueError("server_effective_law_projection_run_not_approved")

    summary_json = dict(run.summary_json or {})
    materialization = dict(summary_json.get("materialization") or {})
    law_set_id = int(materialization.get("law_set_id") or 0)
    if law_set_id <= 0:
        raise ValueError("server_effective_law_projection_materialization_missing")
    activation = dict(summary_json.get("activation") or {})
    if safe_rerun and int(activation.get("law_set_id") or 0) == law_set_id and int(activation.get("law_version_id") or 0) > 0:
        return {
            "ok": True,
            "changed": False,
            "reused_activation": True,
            "run": {
                "id": run.id,
                "server_code": run.server_code,
                "trigger_mode": run.trigger_mode,
                "status": run.status,
                "summary_json": summary_json,
                "created_at": run.created_at,
            },
            "activation": activation,
        }

    published_law_set = runtime_law_sets_store.publish_law_set(law_set_id=law_set_id)
    server_code, source_urls = runtime_law_sets_store.list_source_urls_for_law_set(law_set_id=law_set_id)
    if not source_urls:
        raise ValueError("law_set_sources_empty")
    rebuild_result = law_admin_service.rebuild_index(
        server_code=server_code,
        source_urls=list(source_urls),
        actor_user_id=int(actor_user_id),
        request_id=str(request_id or "").strip(),
        persist_sources=False,
        dry_run=False,
    )
    activation_payload = {
        "law_set_id": law_set_id,
        "server_code": str(server_code or ""),
        "law_version_id": int(rebuild_result.get("law_version_id") or 0),
        "source_urls_count": len(source_urls),
        "activated_by": str(activated_by or "").strip(),
    }
    summary_json["activation"] = activation_payload
    updated_run = projections_store.update_run_status(
        run_id=int(run.id),
        status=run.status,
        summary_json=summary_json,
    )
    return {
        "ok": True,
        "changed": True,
        "reused_activation": False,
        "run": {
            "id": updated_run.id,
            "server_code": updated_run.server_code,
            "trigger_mode": updated_run.trigger_mode,
            "status": updated_run.status,
            "summary_json": dict(updated_run.summary_json),
            "created_at": updated_run.created_at,
        },
        "law_set": dict(published_law_set),
        "activation": activation_payload,
        "result": rebuild_result,
    }


def preview_server_effective_law_projection_payload(
    *,
    source_sets_store: LawSourceSetsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
    projections_store: ServerEffectiveLawProjectionsStore,
    server_code: str,
    trigger_mode: str = "manual",
    safe_rerun: bool = True,
) -> dict[str, Any]:
    normalized_server = _normalize_server_code(server_code)
    if not normalized_server:
        raise ValueError("server_code_required")
    bindings = [item for item in source_sets_store.list_bindings(server_code=normalized_server) if item.is_active]
    if not bindings:
        raise ValueError("server_source_set_bindings_missing")
    source_set_keys = [item.source_set_key for item in bindings]
    parsed_versions = versions_store.list_parsed_versions_for_source_sets(source_set_keys=source_set_keys)
    if not parsed_versions:
        raise ValueError("server_effective_law_projection_candidates_missing")

    grouped: dict[str, list[tuple[ServerSourceSetBindingRecord, CanonicalLawDocumentVersionRecord]]] = defaultdict(list)
    binding_by_source_set = {item.source_set_key: item for item in bindings}
    for version in parsed_versions:
        binding = binding_by_source_set.get(version.source_set_key)
        if binding is None:
            continue
        if not _binding_allows(binding, version):
            continue
        grouped[version.canonical_identity_key].append((binding, version))
    if not grouped:
        raise ValueError("server_effective_law_projection_candidates_missing")

    candidate_versions = [version for values in grouped.values() for _, version in values]
    current_fingerprint = _fingerprint(server_code=normalized_server, bindings=bindings, versions=candidate_versions)
    latest_runs = projections_store.list_runs(server_code=normalized_server)
    latest = latest_runs[0] if latest_runs else None
    if safe_rerun and latest is not None and str((latest.summary_json or {}).get("input_fingerprint") or "") == current_fingerprint:
        return {
            "ok": True,
            "changed": False,
            "run": {
                "id": latest.id,
                "server_code": latest.server_code,
                "trigger_mode": latest.trigger_mode,
                "status": latest.status,
                "summary_json": dict(latest.summary_json),
                "created_at": latest.created_at,
            },
            "items": [
                {
                    "id": item.id,
                    "projection_run_id": item.projection_run_id,
                    "canonical_law_document_id": item.canonical_law_document_id,
                    "canonical_identity_key": item.canonical_identity_key,
                    "normalized_url": item.normalized_url,
                    "selected_document_version_id": item.selected_document_version_id,
                    "selected_source_set_key": item.selected_source_set_key,
                    "selected_revision": item.selected_revision,
                    "precedence_rank": item.precedence_rank,
                    "contributor_count": item.contributor_count,
                    "status": item.status,
                    "provenance_json": dict(item.provenance_json),
                    "created_at": item.created_at,
                }
                for item in projections_store.list_items(projection_run_id=int(latest.id))
            ],
            "count": len(projections_store.list_items(projection_run_id=int(latest.id))),
            "reused_run": True,
        }

    preview_groups: list[tuple[CanonicalLawDocumentVersionRecord, list[tuple[ServerSourceSetBindingRecord, CanonicalLawDocumentVersionRecord]]]] = []
    for identity_key, candidates in grouped.items():
        ordered = sorted(candidates, key=lambda item: _version_sort_key(item[0], item[1]))
        winner_binding, winner_version = ordered[0]
        _ = identity_key
        preview_groups.append((winner_version, ordered))
    preview_groups.sort(key=lambda item: (binding_by_source_set[item[0].source_set_key].priority, item[0].canonical_identity_key))

    run = projections_store.create_projection_run(
        server_code=normalized_server,
        trigger_mode=trigger_mode,
        status="preview",
        summary_json={
            "binding_count": len(bindings),
            "candidate_count": len(candidate_versions),
            "selected_count": len(preview_groups),
            "input_fingerprint": current_fingerprint,
            "source_set_keys": source_set_keys,
        },
    )
    items: list[dict[str, Any]] = []
    for index, (winner, ordered_candidates) in enumerate(preview_groups, start=1):
        item = projections_store.create_projection_item(
            projection_run_id=run.id,
            canonical_law_document_id=winner.canonical_law_document_id,
            canonical_identity_key=winner.canonical_identity_key,
            normalized_url=winner.normalized_url,
            selected_document_version_id=winner.id,
            selected_source_set_key=winner.source_set_key,
            selected_revision=winner.revision,
            precedence_rank=index,
            contributor_count=len(ordered_candidates),
            status="candidate",
            provenance_json={
                "selection_rule": "binding_priority_then_latest_revision_then_source_set_key_then_version_id",
                "contributors": _contributors_payload(candidates=ordered_candidates, selected_version_id=winner.id),
            },
        )
        items.append(
            {
                "id": item.id,
                "projection_run_id": item.projection_run_id,
                "canonical_law_document_id": item.canonical_law_document_id,
                "canonical_identity_key": item.canonical_identity_key,
                "normalized_url": item.normalized_url,
                "selected_document_version_id": item.selected_document_version_id,
                "selected_source_set_key": item.selected_source_set_key,
                "selected_revision": item.selected_revision,
                "precedence_rank": item.precedence_rank,
                "contributor_count": item.contributor_count,
                "status": item.status,
                "provenance_json": dict(item.provenance_json),
                "created_at": item.created_at,
            }
        )
    return {
        "ok": True,
        "changed": True,
        "run": {
            "id": run.id,
            "server_code": run.server_code,
            "trigger_mode": run.trigger_mode,
            "status": run.status,
            "summary_json": dict(run.summary_json),
            "created_at": run.created_at,
        },
        "items": items,
        "count": len(items),
        "reused_run": False,
    }
