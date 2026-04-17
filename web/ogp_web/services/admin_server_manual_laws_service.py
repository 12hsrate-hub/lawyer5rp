from __future__ import annotations

import hashlib
import re
from typing import Any

from ogp_web.services.admin_runtime_servers_service import normalize_runtime_server_code
from ogp_web.storage.canonical_law_documents_store import CanonicalLawDocumentsStore
from ogp_web.storage.canonical_law_document_versions_store import CanonicalLawDocumentVersionsStore
from ogp_web.storage.law_source_discovery_store import LawSourceDiscoveryStore
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore


def _normalize_text(value: str) -> str:
    return str(value or "").strip()


def _normalize_source_set_key(value: str) -> str:
    return _normalize_text(value).lower()


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", _normalize_text(value)).strip("-").lower()
    return normalized or "law"


def _manual_identity_key(*, source_set_key: str, normalized_url: str, title: str) -> str:
    seed = "|".join((source_set_key, normalized_url, title))
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"manual:{_slugify(title)}:{digest}"


def _manual_url(*, source_set_key: str, canonical_identity_key: str) -> str:
    return f"manual://{source_set_key}/{_slugify(canonical_identity_key)}"


def _bound_source_set_keys(*, source_sets_store: LawSourceSetsStore, server_code: str) -> set[str]:
    return {
        str(item.source_set_key or "").strip().lower()
        for item in source_sets_store.list_bindings(server_code=server_code)
        if str(item.source_set_key or "").strip() and bool(item.is_active)
    }


def _latest_revision(*, source_sets_store: LawSourceSetsStore, source_set_key: str):
    revisions = list(source_sets_store.list_revisions(source_set_key=source_set_key))
    if not revisions:
        raise KeyError("source_set_revision_not_found")
    revisions.sort(key=lambda item: (int(getattr(item, "revision", 0) or 0), int(getattr(item, "id", 0) or 0)), reverse=True)
    return revisions[0]


def _latest_version_for_identity(
    *,
    versions_store: CanonicalLawDocumentVersionsStore,
    source_set_key: str,
    canonical_identity_key: str,
):
    candidates = [
        item
        for item in versions_store.list_parsed_versions_for_source_sets(source_set_keys=[source_set_key])
        if str(getattr(item, "canonical_identity_key", "") or "").strip().lower() == canonical_identity_key
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            str(getattr(item, "updated_at", "") or ""),
            int(getattr(item, "id", 0) or 0),
        ),
        reverse=True,
    )
    return candidates[0]


def get_server_manual_law_editor_payload(
    *,
    server_code: str,
    source_set_key: str,
    canonical_identity_key: str,
    source_sets_store: LawSourceSetsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    normalized_source_set_key = _normalize_source_set_key(source_set_key)
    normalized_identity_key = _normalize_text(canonical_identity_key).lower()
    if not normalized_source_set_key:
        raise ValueError("source_set_key_required")
    if not normalized_identity_key:
        raise ValueError("canonical_identity_key_required")
    if normalized_source_set_key not in _bound_source_set_keys(source_sets_store=source_sets_store, server_code=normalized_server):
        raise KeyError("server_source_set_binding_not_found")
    version = _latest_version_for_identity(
        versions_store=versions_store,
        source_set_key=normalized_source_set_key,
        canonical_identity_key=normalized_identity_key,
    )
    if version is None:
        raise KeyError("canonical_law_document_version_not_found")
    return {
        "server_code": normalized_server,
        "source_set_key": normalized_source_set_key,
        "canonical_identity_key": str(version.canonical_identity_key or ""),
        "normalized_url": str(version.normalized_url or ""),
        "title": str(version.parsed_title or version.raw_title or version.display_title or ""),
        "body_text": str(version.body_text or ""),
        "latest_version": {
            "id": int(version.id),
            "canonical_law_document_id": int(version.canonical_law_document_id),
            "source_set_revision_id": int(version.source_set_revision_id or 0),
            "revision": int(version.revision or 0),
            "updated_at": str(version.updated_at or ""),
        },
    }


def save_server_manual_law_entry_payload(
    *,
    server_code: str,
    source_set_key: str,
    canonical_identity_key: str,
    normalized_url: str,
    title: str,
    body_text: str,
    source_sets_store: LawSourceSetsStore,
    discovery_store: LawSourceDiscoveryStore,
    documents_store: CanonicalLawDocumentsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    normalized_source_set_key = _normalize_source_set_key(source_set_key)
    normalized_identity_key = _normalize_text(canonical_identity_key).lower()
    normalized_url_value = _normalize_text(normalized_url)
    normalized_title = _normalize_text(title)
    normalized_body = _normalize_text(body_text)
    if not normalized_source_set_key:
        raise ValueError("source_set_key_required")
    if not normalized_title:
        raise ValueError("manual_law_title_required")
    if not normalized_body:
        raise ValueError("manual_law_body_required")
    if normalized_source_set_key not in _bound_source_set_keys(source_sets_store=source_sets_store, server_code=normalized_server):
        raise KeyError("server_source_set_binding_not_found")

    revision = _latest_revision(source_sets_store=source_sets_store, source_set_key=normalized_source_set_key)
    resolved = None
    if normalized_identity_key:
        document = documents_store.get_document(canonical_identity_key=normalized_identity_key)
        if document is not None:
            resolved = type(
                "_ManualResolved",
                (),
                {
                    "document_id": int(document.id),
                    "canonical_identity_key": str(document.canonical_identity_key or ""),
                    "display_title": str(document.display_title or ""),
                },
            )()
    if resolved is None and normalized_url_value:
        resolved = documents_store.resolve_document_by_alias(normalized_url=normalized_url_value)
    if resolved is None:
        generated_identity_key = normalized_identity_key or _manual_identity_key(
            source_set_key=normalized_source_set_key,
            normalized_url=normalized_url_value,
            title=normalized_title,
        )
        document = documents_store.create_document(
            canonical_identity_key=generated_identity_key,
            identity_source="manual_remap",
            display_title=normalized_title,
            metadata_json={
                "manual_entry": True,
                "server_code": normalized_server,
                "source_set_key": normalized_source_set_key,
            },
        )
        resolved = type(
            "_ManualResolved",
            (),
            {
                "document_id": int(document.id),
                "canonical_identity_key": str(document.canonical_identity_key or ""),
                "display_title": str(document.display_title or ""),
            },
        )()
    canonical_identity_key_value = str(getattr(resolved, "canonical_identity_key", "") or "").strip().lower()
    manual_or_resolved_url = normalized_url_value or _manual_url(
        source_set_key=normalized_source_set_key,
        canonical_identity_key=canonical_identity_key_value,
    )
    if normalized_url_value:
        existing_alias = documents_store.resolve_document_by_alias(normalized_url=normalized_url_value)
        if existing_alias is None:
            documents_store.create_alias(
                canonical_law_document_id=int(getattr(resolved, "document_id")),
                normalized_url=normalized_url_value,
                alias_kind="manual_remap",
                metadata_json={
                    "manual_entry": True,
                    "server_code": normalized_server,
                    "source_set_key": normalized_source_set_key,
                },
            )

    run = discovery_store.create_run(
        source_set_revision_id=int(revision.id),
        trigger_mode="manual",
        status="succeeded",
        summary_json={
            "manual_entry": True,
            "server_code": normalized_server,
            "source_set_key": normalized_source_set_key,
        },
    )
    link = discovery_store.create_link(
        source_discovery_run_id=int(run.id),
        source_set_revision_id=int(revision.id),
        normalized_url=manual_or_resolved_url,
        source_container_url=manual_or_resolved_url,
        discovery_status="discovered",
        alias_hints_json={"canonical_identity_key": canonical_identity_key_value},
        metadata_json={
            "manual_entry": True,
            "server_code": normalized_server,
            "display_title": normalized_title,
        },
    )
    version = versions_store.create_version(
        canonical_law_document_id=int(getattr(resolved, "document_id")),
        source_discovery_run_id=int(run.id),
        discovered_law_link_id=int(link.id),
        fetch_status="fetched",
        parse_status="parsed",
        content_checksum=hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()[:24],
        raw_title=normalized_title,
        parsed_title=normalized_title,
        body_text=normalized_body,
        metadata_json={
            "manual_entry": True,
            "server_code": normalized_server,
            "source_set_key": normalized_source_set_key,
            "source_set_revision_id": int(revision.id),
            "canonical_identity_key": canonical_identity_key_value,
            "normalized_url": manual_or_resolved_url,
        },
    )
    return {
        "server_code": normalized_server,
        "source_set_key": normalized_source_set_key,
        "canonical_identity_key": canonical_identity_key_value,
        "normalized_url": manual_or_resolved_url,
        "item": {
            "canonical_law_document_id": int(version.canonical_law_document_id),
            "canonical_identity_key": str(version.canonical_identity_key or ""),
            "display_title": normalized_title,
            "version_id": int(version.id),
            "source_set_revision_id": int(version.source_set_revision_id or 0),
            "revision": int(version.revision or 0),
            "updated_at": str(version.updated_at or ""),
        },
        "run": {
            "id": int(run.id),
            "source_set_revision_id": int(run.source_set_revision_id),
            "source_set_key": str(run.source_set_key or ""),
            "revision": int(run.revision or 0),
        },
    }
