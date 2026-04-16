from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.admin_canonical_law_document_versions_service import (
    ingest_discovery_run_document_versions_payload,
    list_canonical_law_document_versions_payload,
    list_discovery_run_document_versions_payload,
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
            )
        ]


class _FakeDocumentsStore:
    class _Resolved:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def resolve_document_by_alias(self, *, normalized_url: str):
        if normalized_url != "https://example.com/law/a":
            return None
        return self._Resolved(
            document_id=1,
            canonical_identity_key="url_seed:abc",
            identity_source="url_seed",
            display_title="Procedural Code",
            document_metadata_json={},
            alias_id=1,
            normalized_url=normalized_url,
            alias_kind="canonical",
            is_active=True,
            alias_metadata_json={},
        )


class _FakeVersionsStore:
    class _Version:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def __init__(self):
        self.items = []

    def get_version_by_discovered_link(self, *, discovered_law_link_id: int):
        item = next((row for row in self.items if int(row.discovered_law_link_id) == int(discovered_law_link_id)), None)
        return item

    def create_version(self, **kwargs):
        payload = {
            "id": len(self.items) + 1,
            "canonical_identity_key": "url_seed:abc",
            "display_title": "Procedural Code",
            "source_set_key": "orange-core",
            "source_set_revision_id": 7,
            "revision": 2,
            "normalized_url": "https://example.com/law/a",
            "source_container_url": "https://example.com/topic/1",
            "raw_title": "Procedural Code",
            "parsed_title": "",
            "body_text": "",
            "created_at": "2026-04-16T02:00:00+00:00",
            "updated_at": "2026-04-16T02:00:00+00:00",
        }
        payload.update(kwargs)
        item = self._Version(**payload)
        self.items.append(item)
        return item

    def list_versions_for_run(self, *, source_discovery_run_id: int):
        return [item for item in self.items if int(item.source_discovery_run_id) == int(source_discovery_run_id)]

    def list_versions_for_document(self, *, canonical_law_document_id: int):
        return [item for item in self.items if int(item.canonical_law_document_id) == int(canonical_law_document_id)]


def test_ingest_discovery_run_document_versions_payload_creates_seeded_versions():
    versions_store = _FakeVersionsStore()
    payload = ingest_discovery_run_document_versions_payload(
        discovery_store=_FakeDiscoveryStore(),
        documents_store=_FakeDocumentsStore(),
        versions_store=versions_store,
        run_id=5,
    )
    assert payload["changed"] is True
    assert payload["created_versions"] == 1
    assert payload["items"][0]["fetch_status"] == "seeded"
    assert payload["items"][0]["parse_status"] == "pending"


def test_ingest_discovery_run_document_versions_payload_safe_rerun_reuses_versions():
    versions_store = _FakeVersionsStore()
    ingest_discovery_run_document_versions_payload(
        discovery_store=_FakeDiscoveryStore(),
        documents_store=_FakeDocumentsStore(),
        versions_store=versions_store,
        run_id=5,
    )
    second = ingest_discovery_run_document_versions_payload(
        discovery_store=_FakeDiscoveryStore(),
        documents_store=_FakeDocumentsStore(),
        versions_store=versions_store,
        run_id=5,
        safe_rerun=True,
    )
    assert second["changed"] is False
    assert second["reused_versions"] == 1


def test_list_document_version_payloads():
    versions_store = _FakeVersionsStore()
    ingest_discovery_run_document_versions_payload(
        discovery_store=_FakeDiscoveryStore(),
        documents_store=_FakeDocumentsStore(),
        versions_store=versions_store,
        run_id=5,
    )
    by_run = list_discovery_run_document_versions_payload(
        discovery_store=_FakeDiscoveryStore(),
        versions_store=versions_store,
        run_id=5,
    )
    assert by_run["count"] == 1
    by_document = list_canonical_law_document_versions_payload(
        versions_store=versions_store,
        canonical_law_document_id=1,
    )
    assert by_document["count"] == 1
