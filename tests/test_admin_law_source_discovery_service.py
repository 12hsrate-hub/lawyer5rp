from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.admin_law_source_discovery_service import (
    execute_source_set_discovery_payload,
    list_discovery_run_links_payload,
    list_source_set_discovery_runs_payload,
)


class _FakeSourceSetsStore:
    class _SourceSet:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Revision:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def get_source_set(self, *, source_set_key: str):
        if source_set_key != "orange-core":
            return None
        return self._SourceSet(
            source_set_key="orange-core",
            title="Orange core",
            description="Primary containers",
            scope="global",
            created_at="2026-04-16T00:00:00+00:00",
            updated_at="2026-04-16T00:00:00+00:00",
        )

    def get_revision(self, *, revision_id: int):
        if int(revision_id) != 7:
            return None
        return self._Revision(
            id=7,
            source_set_key="orange-core",
            revision=2,
            status="published",
            container_urls=("https://example.com/topic/1", "notaurl"),
            adapter_policy_json={"extractor": "forum_topic"},
            metadata_json={"promotion_mode": "hybrid"},
            created_at="2026-04-16T00:05:00+00:00",
            published_at="2026-04-16T00:06:00+00:00",
        )

    def list_revisions(self, *, source_set_key: str):
        if source_set_key != "orange-core":
            return []
        return [self.get_revision(revision_id=7)]


class _FakeDiscoveryStore:
    class _Run:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Link:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def list_runs(self, *, source_set_key: str):
        if source_set_key != "orange-core":
            return []
        return [
            self._Run(
                id=5,
                source_set_revision_id=7,
                source_set_key="orange-core",
                revision=2,
                trigger_mode="manual",
                status="partial_success",
                summary_json={"total_links": 3, "broken_links": 1},
                error_summary="1 broken item",
                created_at="2026-04-16T00:10:00+00:00",
                started_at="2026-04-16T00:10:01+00:00",
                finished_at="2026-04-16T00:10:05+00:00",
            )
        ]

    def list_runs_for_revision(self, *, source_set_revision_id: int):
        if int(source_set_revision_id) != 7:
            return []
        return list(self.list_runs(source_set_key="orange-core"))

    def get_run(self, *, run_id: int):
        if int(run_id) != 5:
            return None
        return self._Run(
            id=5,
            source_set_revision_id=7,
            source_set_key="orange-core",
            revision=2,
            trigger_mode="manual",
            status="partial_success",
            summary_json={"total_links": 3, "broken_links": 1},
            error_summary="1 broken item",
            created_at="2026-04-16T00:10:00+00:00",
            started_at="2026-04-16T00:10:01+00:00",
            finished_at="2026-04-16T00:10:05+00:00",
        )

    def list_links(self, *, source_discovery_run_id: int):
        if int(source_discovery_run_id) != 5:
            return []
        return [
            self._Link(
                id=9,
                source_discovery_run_id=5,
                source_set_revision_id=7,
                normalized_url="https://example.com/law/a",
                source_container_url="https://example.com/topic/1",
                discovery_status="discovered",
                alias_hints_json={"raw_url": "https://example.com/law/a?ref=topic"},
                metadata_json={"position": 1},
                first_seen_at="2026-04-16T00:10:02+00:00",
                last_seen_at="2026-04-16T00:10:02+00:00",
                created_at="2026-04-16T00:10:02+00:00",
                updated_at="2026-04-16T00:10:02+00:00",
            )
        ]


class _MutableDiscoveryStore(_FakeDiscoveryStore):
    def __init__(self):
        self.created_runs = []
        self.created_links = []

    def list_runs(self, *, source_set_key: str):
        if not self.created_runs:
            return []
        return list(self.created_runs)

    def list_runs_for_revision(self, *, source_set_revision_id: int):
        return [item for item in self.created_runs if int(item.source_set_revision_id) == int(source_set_revision_id)]

    def create_run(self, *, source_set_revision_id: int, trigger_mode: str = "manual", status: str = "pending", summary_json=None, error_summary: str = ""):
        run = self._Run(
            id=len(self.created_runs) + 1,
            source_set_revision_id=source_set_revision_id,
            source_set_key="orange-core",
            revision=2,
            trigger_mode=trigger_mode,
            status=status,
            summary_json=dict(summary_json or {}),
            error_summary=error_summary,
            created_at="2026-04-16T00:20:00+00:00",
            started_at=None,
            finished_at=None,
        )
        self.created_runs.insert(0, run)
        return run

    def create_link(self, **kwargs):
        link = self._Link(
            id=len(self.created_links) + 1,
            first_seen_at="2026-04-16T00:20:00+00:00",
            last_seen_at="2026-04-16T00:20:00+00:00",
            created_at="2026-04-16T00:20:00+00:00",
            updated_at="2026-04-16T00:20:00+00:00",
            **kwargs,
        )
        self.created_links.append(link)
        return link


def test_list_source_set_discovery_runs_payload():
    payload = list_source_set_discovery_runs_payload(
        source_sets_store=_FakeSourceSetsStore(),
        discovery_store=_FakeDiscoveryStore(),
        source_set_key=" Orange-Core ",
    )
    assert payload["source_set"]["source_set_key"] == "orange-core"
    assert payload["count"] == 1
    assert payload["items"][0]["status"] == "partial_success"


def test_list_discovery_run_links_payload():
    payload = list_discovery_run_links_payload(discovery_store=_FakeDiscoveryStore(), run_id=5)
    assert payload["run"]["id"] == 5
    assert payload["count"] == 1
    assert payload["items"][0]["normalized_url"] == "https://example.com/law/a"


def test_execute_source_set_discovery_payload_creates_partial_success_run():
    discovery_store = _MutableDiscoveryStore()
    payload = execute_source_set_discovery_payload(
        source_sets_store=_FakeSourceSetsStore(),
        discovery_store=discovery_store,
        source_set_key="orange-core",
        source_set_revision_id=7,
    )
    assert payload["changed"] is True
    assert payload["run"]["status"] == "partial_success"
    assert payload["run"]["summary_json"]["discovered_links"] == 1
    assert payload["run"]["summary_json"]["broken_links"] == 1
    assert len(discovery_store.created_links) == 2


def test_execute_source_set_discovery_payload_safe_rerun_reuses_existing_run():
    discovery_store = _MutableDiscoveryStore()
    first = execute_source_set_discovery_payload(
        source_sets_store=_FakeSourceSetsStore(),
        discovery_store=discovery_store,
        source_set_key="orange-core",
        source_set_revision_id=7,
    )
    second = execute_source_set_discovery_payload(
        source_sets_store=_FakeSourceSetsStore(),
        discovery_store=discovery_store,
        source_set_key="orange-core",
        source_set_revision_id=7,
        safe_rerun=True,
    )
    assert first["run"]["id"] == second["run"]["id"]
    assert second["changed"] is False
