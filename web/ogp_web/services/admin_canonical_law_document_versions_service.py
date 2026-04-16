from __future__ import annotations

import hashlib
from typing import Any

from ogp_web.storage.canonical_law_documents_store import CanonicalLawDocumentsStore
from ogp_web.storage.canonical_law_document_versions_store import CanonicalLawDocumentVersionsStore
from ogp_web.storage.law_source_discovery_store import LawSourceDiscoveryStore


def _seed_checksum(*, normalized_url: str, canonical_identity_key: str, run_id: int) -> str:
    payload = "|".join((str(normalized_url or "").strip(), str(canonical_identity_key or "").strip(), str(int(run_id))))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def ingest_discovery_run_document_versions_payload(
    *,
    discovery_store: LawSourceDiscoveryStore,
    documents_store: CanonicalLawDocumentsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
    run_id: int,
    safe_rerun: bool = True,
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("source_discovery_run_id_required")
    run = discovery_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("source_discovery_run_not_found")
    discovered_links = [item for item in discovery_store.list_links(source_discovery_run_id=int(run_id)) if item.discovery_status == "discovered"]
    if not discovered_links:
        raise ValueError("source_discovery_run_has_no_discovered_links")

    created_versions = 0
    reused_versions = 0
    items: list[dict[str, Any]] = []
    for link in discovered_links:
        existing = versions_store.get_version_by_discovered_link(discovered_law_link_id=int(link.id))
        if existing is not None and safe_rerun:
            reused_versions += 1
            items.append(
                {
                    "id": existing.id,
                    "canonical_law_document_id": existing.canonical_law_document_id,
                    "canonical_identity_key": existing.canonical_identity_key,
                    "normalized_url": existing.normalized_url,
                    "fetch_status": existing.fetch_status,
                    "parse_status": existing.parse_status,
                    "content_checksum": existing.content_checksum,
                }
            )
            continue
        resolved = documents_store.resolve_document_by_alias(normalized_url=link.normalized_url)
        if resolved is None:
            continue
        version = versions_store.create_version(
            canonical_law_document_id=resolved.document_id,
            source_discovery_run_id=int(run.id),
            discovered_law_link_id=int(link.id),
            fetch_status="seeded",
            parse_status="pending",
            content_checksum=_seed_checksum(
                normalized_url=link.normalized_url,
                canonical_identity_key=resolved.canonical_identity_key,
                run_id=int(run.id),
            ),
            raw_title=str(resolved.display_title or ""),
            metadata_json={
                "source_set_revision_id": int(run.source_set_revision_id),
                "source_discovery_run_id": int(run.id),
                "seed_mode": "discovery_link_seed",
                "source_container_url": str(link.source_container_url or ""),
            },
        )
        created_versions += 1
        items.append(
            {
                "id": version.id,
                "canonical_law_document_id": version.canonical_law_document_id,
                "canonical_identity_key": version.canonical_identity_key,
                "normalized_url": version.normalized_url,
                "fetch_status": version.fetch_status,
                "parse_status": version.parse_status,
                "content_checksum": version.content_checksum,
            }
        )
    return {
        "ok": True,
        "changed": bool(created_versions),
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
        "created_versions": created_versions,
        "reused_versions": reused_versions,
    }


def list_discovery_run_document_versions_payload(
    *,
    discovery_store: LawSourceDiscoveryStore,
    versions_store: CanonicalLawDocumentVersionsStore,
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
            "canonical_law_document_id": item.canonical_law_document_id,
            "canonical_identity_key": item.canonical_identity_key,
            "display_title": item.display_title,
            "normalized_url": item.normalized_url,
            "source_container_url": item.source_container_url,
            "fetch_status": item.fetch_status,
            "parse_status": item.parse_status,
            "content_checksum": item.content_checksum,
            "raw_title": item.raw_title,
            "parsed_title": item.parsed_title,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in versions_store.list_versions_for_run(source_discovery_run_id=int(run_id))
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
        },
        "items": items,
        "count": len(items),
    }


def list_canonical_law_document_versions_payload(
    *,
    versions_store: CanonicalLawDocumentVersionsStore,
    canonical_law_document_id: int,
) -> dict[str, Any]:
    if int(canonical_law_document_id) <= 0:
        raise ValueError("canonical_law_document_id_required")
    items = [
        {
            "id": item.id,
            "canonical_law_document_id": item.canonical_law_document_id,
            "canonical_identity_key": item.canonical_identity_key,
            "display_title": item.display_title,
            "source_discovery_run_id": item.source_discovery_run_id,
            "discovered_law_link_id": item.discovered_law_link_id,
            "source_set_key": item.source_set_key,
            "revision": item.revision,
            "normalized_url": item.normalized_url,
            "fetch_status": item.fetch_status,
            "parse_status": item.parse_status,
            "content_checksum": item.content_checksum,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in versions_store.list_versions_for_document(canonical_law_document_id=int(canonical_law_document_id))
    ]
    return {
        "canonical_law_document_id": int(canonical_law_document_id),
        "items": items,
        "count": len(items),
    }
