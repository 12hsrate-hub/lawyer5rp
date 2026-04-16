from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.admin_law_projection_service import (
    list_server_effective_law_projection_items_payload,
    list_server_effective_law_projection_runs_payload,
    preview_server_effective_law_projection_payload,
)


class _FakeBinding:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeVersion:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeSourceSetsStore:
    def list_bindings(self, *, server_code: str):
        if server_code != "orange":
            return []
        return [
            _FakeBinding(
                id=1,
                server_code="orange",
                source_set_key="orange-priority",
                priority=10,
                is_active=True,
                include_law_keys=(),
                exclude_law_keys=(),
                pin_policy_json={},
                metadata_json={},
            ),
            _FakeBinding(
                id=2,
                server_code="orange",
                source_set_key="orange-core",
                priority=20,
                is_active=True,
                include_law_keys=(),
                exclude_law_keys=(),
                pin_policy_json={},
                metadata_json={},
            ),
        ]


class _FakeVersionsStore:
    def list_parsed_versions_for_source_sets(self, *, source_set_keys):
        return [
            _FakeVersion(
                id=7,
                canonical_law_document_id=1,
                canonical_identity_key="url_seed:law-a",
                display_title="Law A",
                source_discovery_run_id=11,
                discovered_law_link_id=101,
                source_set_key="orange-core",
                source_set_revision_id=3,
                revision=3,
                normalized_url="https://example.com/law/a",
                source_container_url="https://example.com/container/1",
                fetch_status="fetched",
                parse_status="parsed",
                content_checksum="abc",
                raw_title="Law A",
                parsed_title="Law A",
                body_text="Law A body",
                metadata_json={},
                created_at="2026-04-16T05:00:00+00:00",
                updated_at="2026-04-16T05:00:00+00:00",
            ),
            _FakeVersion(
                id=8,
                canonical_law_document_id=1,
                canonical_identity_key="url_seed:law-a",
                display_title="Law A",
                source_discovery_run_id=12,
                discovered_law_link_id=102,
                source_set_key="orange-priority",
                source_set_revision_id=4,
                revision=4,
                normalized_url="https://example.com/law/a",
                source_container_url="https://example.com/container/2",
                fetch_status="fetched",
                parse_status="parsed",
                content_checksum="def",
                raw_title="Law A",
                parsed_title="Law A",
                body_text="Law A body updated",
                metadata_json={},
                created_at="2026-04-16T05:10:00+00:00",
                updated_at="2026-04-16T05:10:00+00:00",
            ),
            _FakeVersion(
                id=9,
                canonical_law_document_id=2,
                canonical_identity_key="url_seed:law-b",
                display_title="Law B",
                source_discovery_run_id=13,
                discovered_law_link_id=103,
                source_set_key="orange-core",
                source_set_revision_id=3,
                revision=3,
                normalized_url="https://example.com/law/b",
                source_container_url="https://example.com/container/1",
                fetch_status="fetched",
                parse_status="parsed",
                content_checksum="ghi",
                raw_title="Law B",
                parsed_title="Law B",
                body_text="Law B body",
                metadata_json={},
                created_at="2026-04-16T05:20:00+00:00",
                updated_at="2026-04-16T05:20:00+00:00",
            ),
        ]


class _FakeRun:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeItem:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeProjectionsStore:
    def __init__(self):
        self.runs = []
        self.items = []

    def list_runs(self, *, server_code: str):
        return [item for item in self.runs if item.server_code == server_code]

    def get_run(self, *, run_id: int):
        return next((item for item in self.runs if int(item.id) == int(run_id)), None)

    def list_items(self, *, projection_run_id: int):
        return [item for item in self.items if int(item.projection_run_id) == int(projection_run_id)]

    def create_projection_run(self, **kwargs):
        item = _FakeRun(
            id=len(self.runs) + 1,
            server_code=kwargs["server_code"],
            trigger_mode=kwargs["trigger_mode"],
            status=kwargs["status"],
            summary_json=dict(kwargs.get("summary_json") or {}),
            created_at="2026-04-16T06:00:00+00:00",
        )
        self.runs.insert(0, item)
        return item

    def create_projection_item(self, **kwargs):
        item = _FakeItem(
            id=len(self.items) + 1,
            projection_run_id=kwargs["projection_run_id"],
            canonical_law_document_id=kwargs["canonical_law_document_id"],
            canonical_identity_key=kwargs["canonical_identity_key"],
            normalized_url=kwargs["normalized_url"],
            selected_document_version_id=kwargs["selected_document_version_id"],
            selected_source_set_key=kwargs["selected_source_set_key"],
            selected_revision=kwargs["selected_revision"],
            precedence_rank=kwargs["precedence_rank"],
            contributor_count=kwargs["contributor_count"],
            status=kwargs["status"],
            provenance_json=dict(kwargs.get("provenance_json") or {}),
            created_at="2026-04-16T06:01:00+00:00",
        )
        self.items.append(item)
        return item


def test_preview_server_effective_law_projection_payload_selects_highest_priority_binding():
    projections = _FakeProjectionsStore()
    payload = preview_server_effective_law_projection_payload(
        source_sets_store=_FakeSourceSetsStore(),
        versions_store=_FakeVersionsStore(),
        projections_store=projections,
        server_code="orange",
    )
    assert payload["changed"] is True
    assert payload["count"] == 2
    first = payload["items"][0]
    assert first["canonical_identity_key"] == "url_seed:law-a"
    assert first["selected_source_set_key"] == "orange-priority"
    assert first["selected_document_version_id"] == 8
    assert first["contributor_count"] == 2


def test_preview_server_effective_law_projection_payload_safe_rerun_reuses_identical_run():
    projections = _FakeProjectionsStore()
    preview_server_effective_law_projection_payload(
        source_sets_store=_FakeSourceSetsStore(),
        versions_store=_FakeVersionsStore(),
        projections_store=projections,
        server_code="orange",
    )
    second = preview_server_effective_law_projection_payload(
        source_sets_store=_FakeSourceSetsStore(),
        versions_store=_FakeVersionsStore(),
        projections_store=projections,
        server_code="orange",
        safe_rerun=True,
    )
    assert second["changed"] is False
    assert second["reused_run"] is True
    assert second["count"] == 2


def test_list_server_effective_law_projection_payloads():
    projections = _FakeProjectionsStore()
    created = preview_server_effective_law_projection_payload(
        source_sets_store=_FakeSourceSetsStore(),
        versions_store=_FakeVersionsStore(),
        projections_store=projections,
        server_code="orange",
    )
    runs = list_server_effective_law_projection_runs_payload(
        projections_store=projections,
        server_code="orange",
    )
    assert runs["count"] == 1
    items = list_server_effective_law_projection_items_payload(
        projections_store=projections,
        run_id=created["run"]["id"],
    )
    assert items["count"] == 2
