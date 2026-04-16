from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from ogp_web.storage.canonical_law_document_versions_store import (
    CanonicalLawDocumentVersionRecord,
    CanonicalLawDocumentVersionsStore,
)
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore, ServerSourceSetBindingRecord
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
