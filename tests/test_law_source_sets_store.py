from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.law_source_sets_store import LawSourceSetsStore


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
        self.servers = {
            "blackberry": {"code": "blackberry"},
        }
        self.source_sets: dict[str, dict[str, object]] = {}
        self.revisions: list[dict[str, object]] = []
        self.bindings: list[dict[str, object]] = []
        self.next_revision_id = 1
        self.next_binding_id = 1
        self.commits = 0

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT source_set_key, title, description, scope, created_at, updated_at FROM source_sets ORDER BY source_set_key ASC"):
            rows = [self.source_sets[key] for key in sorted(self.source_sets.keys())]
            return _Cursor(rows=rows)
        if normalized.startswith("SELECT source_set_key, title, description, scope, created_at, updated_at FROM source_sets WHERE source_set_key = %s"):
            key = params[0]
            return _Cursor(one=self.source_sets.get(key))
        if normalized.startswith("INSERT INTO source_sets (source_set_key, title, description, scope) VALUES"):
            source_set_key, title, description, scope = params
            if source_set_key in self.source_sets:
                raise Exception('duplicate key value violates unique constraint "source_sets_pkey"')
            row = {
                "source_set_key": source_set_key,
                "title": title,
                "description": description,
                "scope": scope,
                "created_at": "2026-04-16T00:00:00+00:00",
                "updated_at": "2026-04-16T00:00:00+00:00",
            }
            self.source_sets[source_set_key] = row
            return _Cursor(one=row)
        if normalized.startswith("SELECT id, source_set_key, revision, status, container_urls_json, adapter_policy_json, metadata_json, created_at, published_at FROM source_set_revisions WHERE source_set_key = %s ORDER BY revision DESC"):
            source_set_key = params[0]
            rows = [row for row in self.revisions if row["source_set_key"] == source_set_key]
            rows.sort(key=lambda item: int(item["revision"]), reverse=True)
            return _Cursor(rows=rows)
        if normalized.startswith("SELECT source_set_key FROM source_sets WHERE source_set_key = %s"):
            source_set_key = params[0]
            row = self.source_sets.get(source_set_key)
            if row is None:
                return _Cursor(one=None)
            return _Cursor(one={"source_set_key": source_set_key})
        if normalized.startswith("SELECT COALESCE(MAX(revision), 0) + 1 AS next_revision FROM source_set_revisions WHERE source_set_key = %s"):
            source_set_key = params[0]
            revisions = [int(row["revision"]) for row in self.revisions if row["source_set_key"] == source_set_key]
            return _Cursor(one={"next_revision": (max(revisions) + 1) if revisions else 1})
        if normalized.startswith("INSERT INTO source_set_revisions ( source_set_key, revision, status, container_urls_json, adapter_policy_json, metadata_json, published_at ) VALUES"):
            source_set_key, revision, status, container_urls_json, adapter_policy_json, metadata_json, published_status = params
            row = {
                "id": self.next_revision_id,
                "source_set_key": source_set_key,
                "revision": revision,
                "status": status,
                "container_urls_json": list(container_urls_json),
                "adapter_policy_json": dict(adapter_policy_json),
                "metadata_json": dict(metadata_json),
                "created_at": "2026-04-16T00:05:00+00:00",
                "published_at": "2026-04-16T00:05:00+00:00" if published_status == "published" else None,
            }
            self.next_revision_id += 1
            self.revisions.append(row)
            return _Cursor(one=row)
        if normalized.startswith("SELECT id, server_code, source_set_key, priority, is_active, include_law_keys_json, exclude_law_keys_json, pin_policy_json, metadata_json, created_at, updated_at FROM server_source_set_bindings WHERE server_code = %s ORDER BY is_active DESC, priority ASC, id ASC"):
            server_code = params[0]
            rows = [row for row in self.bindings if row["server_code"] == server_code]
            rows.sort(key=lambda item: (not bool(item["is_active"]), int(item["priority"]), int(item["id"])))
            return _Cursor(rows=rows)
        if normalized.startswith("SELECT code FROM servers WHERE code = %s"):
            code = params[0]
            return _Cursor(one=self.servers.get(code))
        if normalized.startswith("INSERT INTO server_source_set_bindings ( server_code, source_set_key, priority, is_active, include_law_keys_json, exclude_law_keys_json, pin_policy_json, metadata_json ) VALUES"):
            server_code, source_set_key, priority, is_active, include_law_keys_json, exclude_law_keys_json, pin_policy_json, metadata_json = params
            if any(row for row in self.bindings if row["server_code"] == server_code and row["source_set_key"] == source_set_key):
                raise Exception(
                    'duplicate key value violates unique constraint "server_source_set_bindings_server_code_source_set_key_key"'
                )
            row = {
                "id": self.next_binding_id,
                "server_code": server_code,
                "source_set_key": source_set_key,
                "priority": priority,
                "is_active": is_active,
                "include_law_keys_json": list(include_law_keys_json),
                "exclude_law_keys_json": list(exclude_law_keys_json),
                "pin_policy_json": dict(pin_policy_json),
                "metadata_json": dict(metadata_json),
                "created_at": "2026-04-16T00:10:00+00:00",
                "updated_at": "2026-04-16T00:10:00+00:00",
            }
            self.next_binding_id += 1
            self.bindings.append(row)
            return _Cursor(one=row)
        raise AssertionError(f"Unsupported query: {normalized}")

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None

    def close(self):
        return None


class _Backend:
    def __init__(self):
        self.conn = _Connection()

    def connect(self):
        return self.conn


def test_law_source_sets_store_creates_source_set_revision_and_binding():
    store = LawSourceSetsStore(_Backend())

    source_set = store.create_source_set(
        source_set_key="orange-core",
        title="Orange core laws",
        description="Primary container set",
    )
    assert source_set.source_set_key == "orange-core"
    assert source_set.scope == "global"

    revision = store.create_revision(
        source_set_key="orange-core",
        container_urls=["https://example.com/container/a", "https://example.com/container/a", "https://example.com/container/b"],
        adapter_policy_json={"extractor": "forum_topic"},
        metadata_json={"promotion_mode": "hybrid"},
        status="published",
    )
    assert revision.revision == 1
    assert revision.status == "published"
    assert revision.container_urls == (
        "https://example.com/container/a",
        "https://example.com/container/b",
    )
    assert revision.metadata_json["promotion_mode"] == "hybrid"

    binding = store.create_binding(
        server_code="blackberry",
        source_set_key="orange-core",
        priority=10,
        include_law_keys=["law.alpha"],
        exclude_law_keys=["law.beta"],
        pin_policy_json={"freeze": True},
        metadata_json={"origin": "phase1"},
    )
    assert binding.server_code == "blackberry"
    assert binding.source_set_key == "orange-core"
    assert binding.priority == 10
    assert binding.include_law_keys == ("law.alpha",)
    assert binding.exclude_law_keys == ("law.beta",)
    assert binding.pin_policy_json["freeze"] is True

    listed_sets = store.list_source_sets()
    assert [item.source_set_key for item in listed_sets] == ["orange-core"]
    listed_revisions = store.list_revisions(source_set_key="orange-core")
    assert [item.revision for item in listed_revisions] == [1]
    listed_bindings = store.list_bindings(server_code="blackberry")
    assert [item.source_set_key for item in listed_bindings] == ["orange-core"]


def test_law_source_sets_store_duplicate_binding_returns_value_error():
    store = LawSourceSetsStore(_Backend())
    store.create_source_set(source_set_key="orange-core", title="Orange core laws")
    created = store.create_binding(server_code="blackberry", source_set_key="orange-core")
    assert created.id == 1
    try:
        store.create_binding(server_code="blackberry", source_set_key="orange-core")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "server_source_set_binding_already_exists"


def test_law_source_sets_store_requires_existing_source_set_for_revision():
    store = LawSourceSetsStore(_Backend())
    try:
        store.create_revision(
            source_set_key="missing",
            container_urls=["https://example.com/container/a"],
        )
        assert False, "expected KeyError"
    except KeyError as exc:
        assert str(exc) == "'source_set_not_found'"
