from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore


class _Cursor:
    def __init__(self, *, one=None):
        self._one = one

    def fetchone(self):
        return self._one

    def fetchall(self):
        return []


class _Connection:
    def __init__(self):
        self.sources: dict[str, dict[str, object]] = {}
        self.law_sets: dict[tuple[str, str], dict[str, object]] = {}
        self.next_source_id = 1
        self.next_law_set_id = 1
        self.commits = 0

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())
        if normalized.startswith("INSERT INTO law_source_registry"):
            name, kind, url = params
            key = str(url).strip().lower()
            if key in self.sources:
                raise Exception('duplicate key value violates unique constraint "idx_law_source_registry_url_unique"')
            row = {
                "id": self.next_source_id,
                "name": name,
                "kind": kind,
                "url": url,
                "is_active": True,
            }
            self.next_source_id += 1
            self.sources[key] = row
            return _Cursor(one=row)
        if normalized.startswith("INSERT INTO law_sets"):
            server_code, name = params
            key = (str(server_code).strip().lower(), str(name).strip().lower())
            if key in self.law_sets:
                raise Exception('duplicate key value violates unique constraint "idx_law_sets_server_name_unique"')
            row = {
                "id": self.next_law_set_id,
                "server_code": server_code,
                "name": name,
                "is_active": True,
                "is_published": False,
            }
            self.next_law_set_id += 1
            self.law_sets[key] = row
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


def test_runtime_law_sets_store_duplicate_source_url_returns_value_error():
    store = RuntimeLawSetsStore(_Backend())
    created = store.create_source(name="Forum", kind="url", url="https://example.com/law/a")
    assert created.id == 1
    try:
        store.create_source(name="Duplicate", kind="url", url="https://example.com/law/a")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "law_source_url_already_exists"


def test_runtime_law_sets_store_duplicate_law_set_name_returns_value_error():
    store = RuntimeLawSetsStore(_Backend())
    created = store.create_law_set(server_code="blackberry", name="Main laws")
    assert int(created["id"]) == 1
    try:
        store.create_law_set(server_code="blackberry", name="Main laws")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "law_set_name_already_exists"
