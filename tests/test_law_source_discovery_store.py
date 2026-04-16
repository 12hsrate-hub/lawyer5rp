from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.law_source_discovery_store import LawSourceDiscoveryStore


class _Cursor:
    def __init__(self, *, one=None, rows=None):
        self._one = one
        self._rows = rows or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return list(self._rows)


class _Connection:
    def __init__(self):
        self.revisions = {
            7: {"id": 7, "source_set_key": "orange-core", "revision": 2},
        }
        self.runs: list[dict[str, object]] = []
        self.links: list[dict[str, object]] = []
        self.next_run_id = 1
        self.next_link_id = 1

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT r.id, r.source_set_revision_id, rev.source_set_key, rev.revision, r.trigger_mode, r.status, r.summary_json, r.error_summary, r.created_at, r.started_at, r.finished_at FROM source_discovery_runs AS r JOIN source_set_revisions AS rev ON rev.id = r.source_set_revision_id WHERE rev.source_set_key = %s ORDER BY r.created_at DESC, r.id DESC"):
            source_set_key = params[0]
            rows = [
                row
                for row in self.runs
                if self.revisions[int(row["source_set_revision_id"])]["source_set_key"] == source_set_key
            ]
            rows.sort(key=lambda item: (str(item["created_at"]), int(item["id"])), reverse=True)
            return _Cursor(rows=rows)
        if normalized.startswith("SELECT r.id, r.source_set_revision_id, rev.source_set_key, rev.revision, r.trigger_mode, r.status, r.summary_json, r.error_summary, r.created_at, r.started_at, r.finished_at FROM source_discovery_runs AS r JOIN source_set_revisions AS rev ON rev.id = r.source_set_revision_id WHERE r.id = %s"):
            run_id = int(params[0])
            row = next((item for item in self.runs if int(item["id"]) == run_id), None)
            return _Cursor(one=row)
        if normalized.startswith("INSERT INTO source_discovery_runs ( source_set_revision_id, trigger_mode, status, summary_json, error_summary ) VALUES"):
            source_set_revision_id, trigger_mode, status, summary_json, error_summary = params
            revision = self.revisions.get(int(source_set_revision_id))
            if revision is None:
                raise Exception('insert or update on table "source_discovery_runs" violates foreign key constraint')
            row = {
                "id": self.next_run_id,
                "source_set_revision_id": int(source_set_revision_id),
                "source_set_key": revision["source_set_key"],
                "revision": revision["revision"],
                "trigger_mode": trigger_mode,
                "status": status,
                "summary_json": dict(summary_json),
                "error_summary": error_summary,
                "created_at": f"2026-04-16T00:0{self.next_run_id}:00+00:00",
                "started_at": None,
                "finished_at": None,
            }
            self.next_run_id += 1
            self.runs.append(row)
            return _Cursor(one={"id": row["id"]})
        if normalized.startswith("SELECT id, source_discovery_run_id, source_set_revision_id, normalized_url, source_container_url, discovery_status, alias_hints_json, metadata_json, first_seen_at, last_seen_at, created_at, updated_at FROM discovered_law_links WHERE source_discovery_run_id = %s ORDER BY normalized_url ASC, id ASC"):
            run_id = int(params[0])
            rows = [row for row in self.links if int(row["source_discovery_run_id"]) == run_id]
            rows.sort(key=lambda item: (str(item["normalized_url"]), int(item["id"])))
            return _Cursor(rows=rows)
        if normalized.startswith("INSERT INTO discovered_law_links ( source_discovery_run_id, source_set_revision_id, normalized_url, source_container_url, discovery_status, alias_hints_json, metadata_json ) VALUES"):
            source_discovery_run_id, source_set_revision_id, normalized_url, source_container_url, discovery_status, alias_hints_json, metadata_json = params
            if any(
                row
                for row in self.links
                if int(row["source_discovery_run_id"]) == int(source_discovery_run_id)
                and str(row["normalized_url"]) == str(normalized_url)
            ):
                raise Exception(
                    'duplicate key value violates unique constraint "discovered_law_links_source_discovery_run_id_normalized_url_key"'
                )
            row = {
                "id": self.next_link_id,
                "source_discovery_run_id": int(source_discovery_run_id),
                "source_set_revision_id": int(source_set_revision_id),
                "normalized_url": normalized_url,
                "source_container_url": source_container_url,
                "discovery_status": discovery_status,
                "alias_hints_json": dict(alias_hints_json),
                "metadata_json": dict(metadata_json),
                "first_seen_at": "2026-04-16T00:20:00+00:00",
                "last_seen_at": "2026-04-16T00:20:00+00:00",
                "created_at": "2026-04-16T00:20:00+00:00",
                "updated_at": "2026-04-16T00:20:00+00:00",
            }
            self.next_link_id += 1
            self.links.append(row)
            return _Cursor(one=row)
        raise AssertionError(f"Unsupported query: {normalized}")

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


class _Backend:
    def __init__(self):
        self.conn = _Connection()

    def connect(self):
        return self.conn


def test_law_source_discovery_store_creates_runs_and_links():
    store = LawSourceDiscoveryStore(_Backend())

    run = store.create_run(
        source_set_revision_id=7,
        trigger_mode="manual",
        status="partial_success",
        summary_json={"total_links": 2, "broken_links": 1},
    )
    assert run.source_set_key == "orange-core"
    assert run.revision == 2
    assert run.status == "partial_success"

    link = store.create_link(
        source_discovery_run_id=run.id,
        source_set_revision_id=7,
        normalized_url="https://example.com/law/a",
        source_container_url="https://example.com/topic/1",
        discovery_status="discovered",
        alias_hints_json={"raw_url": "https://example.com/law/a?ref=topic"},
    )
    assert link.normalized_url == "https://example.com/law/a"
    assert link.alias_hints_json["raw_url"] == "https://example.com/law/a?ref=topic"

    listed_runs = store.list_runs(source_set_key="orange-core")
    assert [item.id for item in listed_runs] == [run.id]
    listed_links = store.list_links(source_discovery_run_id=run.id)
    assert [item.normalized_url for item in listed_links] == ["https://example.com/law/a"]


def test_law_source_discovery_store_requires_non_empty_url():
    store = LawSourceDiscoveryStore(_Backend())
    try:
        store.create_link(source_discovery_run_id=1, source_set_revision_id=7, normalized_url=" ")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "discovered_law_link_url_required"


def test_law_source_discovery_store_duplicate_link_returns_value_error():
    store = LawSourceDiscoveryStore(_Backend())
    run = store.create_run(source_set_revision_id=7)
    created = store.create_link(
        source_discovery_run_id=run.id,
        source_set_revision_id=7,
        normalized_url="https://example.com/law/a",
    )
    assert created.id == 1
    try:
        store.create_link(
            source_discovery_run_id=run.id,
            source_set_revision_id=7,
            normalized_url="https://example.com/law/a",
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "discovered_law_link_already_exists"
