from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.admin_canonical_law_documents_service import (
    ingest_discovery_run_documents_payload,
    list_discovery_run_documents_payload,
)


class _FakeDiscoveryStore:
    class _Run:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Link:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def get_run(self, *, run_id: int):
        if int(run_id) != 5:
            return None
        return self._Run(
            id=5,
            source_set_revision_id=7,
            source_set_key="orange-core",
            revision=2,
            trigger_mode="manual",
            status="succeeded",
            summary_json={"discovered_links": 1},
            error_summary="",
        )

    def list_links(self, *, source_discovery_run_id: int):
        if int(source_discovery_run_id) != 5:
            return []
        return [
            self._Link(
                id=11,
                source_discovery_run_id=5,
                source_set_revision_id=7,
                normalized_url="https://example.com/law/a",
                source_container_url="https://example.com/topic/1",
                discovery_status="discovered",
                alias_hints_json={},
                metadata_json={},
                first_seen_at="2026-04-16T00:10:00+00:00",
                last_seen_at="2026-04-16T00:10:00+00:00",
                created_at="2026-04-16T00:10:00+00:00",
                updated_at="2026-04-16T00:10:00+00:00",
            ),
            self._Link(
                id=12,
                source_discovery_run_id=5,
                source_set_revision_id=7,
                normalized_url="https://example.com/law/broken",
                source_container_url="https://example.com/topic/1",
                discovery_status="broken",
                alias_hints_json={},
                metadata_json={},
                first_seen_at="2026-04-16T00:10:00+00:00",
                last_seen_at="2026-04-16T00:10:00+00:00",
                created_at="2026-04-16T00:10:00+00:00",
                updated_at="2026-04-16T00:10:00+00:00",
            ),
        ]


class _FakeDocumentsStore:
    class _Resolved:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Document:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def __init__(self):
        self.documents = {}
        self.aliases = {}
        self.next_document_id = 1
        self.next_alias_id = 1

    def resolve_document_by_alias(self, *, normalized_url: str):
        resolved = self.aliases.get(normalized_url)
        return self._Resolved(**resolved) if resolved else None

    def create_document(self, *, canonical_identity_key: str, identity_source: str = "url_seed", display_title: str = "", metadata_json=None):
        document = {
            "id": self.next_document_id,
            "canonical_identity_key": canonical_identity_key,
            "identity_source": identity_source,
            "display_title": display_title,
            "metadata_json": dict(metadata_json or {}),
        }
        self.documents[self.next_document_id] = document
        self.next_document_id += 1
        return self._Document(**document)

    def create_alias(self, *, canonical_law_document_id: int, normalized_url: str, alias_kind: str = "canonical", metadata_json=None, **kwargs):
        document = self.documents[int(canonical_law_document_id)]
        alias = {
            "document_id": document["id"],
            "canonical_identity_key": document["canonical_identity_key"],
            "identity_source": document["identity_source"],
            "display_title": document["display_title"],
            "document_metadata_json": dict(document["metadata_json"]),
            "alias_id": self.next_alias_id,
            "normalized_url": normalized_url,
            "alias_kind": alias_kind,
            "is_active": True,
            "alias_metadata_json": dict(metadata_json or {}),
        }
        self.aliases[normalized_url] = alias
        self.next_alias_id += 1
        return self._Resolved(**alias)


def test_ingest_discovery_run_documents_payload_creates_canonical_documents():
    store = _FakeDocumentsStore()
    payload = ingest_discovery_run_documents_payload(
        discovery_store=_FakeDiscoveryStore(),
        documents_store=store,
        run_id=5,
    )
    assert payload["changed"] is True
    assert payload["count"] == 1
    assert payload["created_documents"] == 1
    assert payload["items"][0]["normalized_url"] == "https://example.com/law/a"


def test_ingest_discovery_run_documents_payload_safe_rerun_reuses_existing_documents():
    store = _FakeDocumentsStore()
    first = ingest_discovery_run_documents_payload(
        discovery_store=_FakeDiscoveryStore(),
        documents_store=store,
        run_id=5,
    )
    second = ingest_discovery_run_documents_payload(
        discovery_store=_FakeDiscoveryStore(),
        documents_store=store,
        run_id=5,
        safe_rerun=True,
    )
    assert first["count"] == second["count"] == 1
    assert second["changed"] is False
    assert second["reused_documents"] == 1


def test_list_discovery_run_documents_payload_lists_ingested_documents():
    store = _FakeDocumentsStore()
    ingest_discovery_run_documents_payload(
        discovery_store=_FakeDiscoveryStore(),
        documents_store=store,
        run_id=5,
    )
    payload = list_discovery_run_documents_payload(
        discovery_store=_FakeDiscoveryStore(),
        documents_store=store,
        run_id=5,
    )
    assert payload["count"] == 1
    assert payload["items"][0]["identity_source"] == "url_seed"
