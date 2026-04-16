from __future__ import annotations

import hashlib
from typing import Any

from ogp_web.storage.canonical_law_documents_store import CanonicalLawDocumentsStore
from ogp_web.storage.law_source_discovery_store import LawSourceDiscoveryStore


def _canonical_identity_key_from_url(normalized_url: str) -> str:
    digest = hashlib.sha256(str(normalized_url or "").strip().encode("utf-8")).hexdigest()[:24]
    return f"url_seed:{digest}"


def ingest_discovery_run_documents_payload(
    *,
    discovery_store: LawSourceDiscoveryStore,
    documents_store: CanonicalLawDocumentsStore,
    run_id: int,
    safe_rerun: bool = True,
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("source_discovery_run_id_required")
    run = discovery_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("source_discovery_run_not_found")
    links = discovery_store.list_links(source_discovery_run_id=int(run_id))
    discovered_links = [item for item in links if item.discovery_status == "discovered" and item.normalized_url]
    if not discovered_links:
        raise ValueError("source_discovery_run_has_no_discovered_links")

    created_documents = 0
    reused_documents = 0
    created_aliases = 0
    items: list[dict[str, Any]] = []
    for link in discovered_links:
        resolved = documents_store.resolve_document_by_alias(normalized_url=link.normalized_url)
        if resolved is None:
            document = documents_store.create_document(
                canonical_identity_key=_canonical_identity_key_from_url(link.normalized_url),
                identity_source="url_seed",
                display_title=str((link.metadata_json or {}).get("document_title") or link.normalized_url),
                metadata_json={
                    "seed_url": link.normalized_url,
                    "source_discovery_run_id": int(run.id),
                    "source_set_revision_id": int(run.source_set_revision_id),
                    "identity_mode": "url_seed",
                },
            )
            created_documents += 1
            documents_store.create_alias(
                canonical_law_document_id=document.id,
                normalized_url=link.normalized_url,
                alias_kind="canonical",
                metadata_json={
                    "source_discovery_run_id": int(run.id),
                    "source_set_revision_id": int(run.source_set_revision_id),
                },
            )
            created_aliases += 1
            resolved = documents_store.resolve_document_by_alias(normalized_url=link.normalized_url)
        else:
            reused_documents += 1
        if resolved is None:
            continue
        items.append(
            {
                "canonical_identity_key": resolved.canonical_identity_key,
                "display_title": resolved.display_title,
                "identity_source": resolved.identity_source,
                "normalized_url": resolved.normalized_url,
                "alias_kind": resolved.alias_kind,
                "document_id": resolved.document_id,
                "alias_id": resolved.alias_id,
            }
        )
    changed = bool(created_documents or created_aliases)
    if safe_rerun and not changed:
        reused_documents = len(items)
    return {
        "ok": True,
        "changed": changed,
        "run": {
            "id": run.id,
            "source_set_revision_id": run.source_set_revision_id,
            "source_set_key": run.source_set_key,
            "revision": run.revision,
            "trigger_mode": run.trigger_mode,
            "status": run.status,
            "summary_json": dict(run.summary_json),
            "error_summary": run.error_summary,
        },
        "items": items,
        "count": len(items),
        "created_documents": created_documents,
        "reused_documents": reused_documents,
        "created_aliases": created_aliases,
    }


def list_discovery_run_documents_payload(
    *,
    discovery_store: LawSourceDiscoveryStore,
    documents_store: CanonicalLawDocumentsStore,
    run_id: int,
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("source_discovery_run_id_required")
    run = discovery_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("source_discovery_run_not_found")
    items: list[dict[str, Any]] = []
    for link in discovery_store.list_links(source_discovery_run_id=int(run_id)):
        if link.discovery_status != "discovered":
            continue
        resolved = documents_store.resolve_document_by_alias(normalized_url=link.normalized_url)
        if resolved is None:
            continue
        items.append(
            {
                "canonical_identity_key": resolved.canonical_identity_key,
                "display_title": resolved.display_title,
                "identity_source": resolved.identity_source,
                "normalized_url": resolved.normalized_url,
                "alias_kind": resolved.alias_kind,
                "document_id": resolved.document_id,
                "alias_id": resolved.alias_id,
            }
        )
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
        },
        "items": items,
        "count": len(items),
    }
