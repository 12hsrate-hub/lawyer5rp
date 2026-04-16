from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.runtime_servers_store import RuntimeServersStore


class _Cursor:
    def __init__(self, one=None, rows=None):
        self._one = one
        self._rows = rows or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return list(self._rows)


class _Connection:
    def __init__(self):
        self.rows = {
            "blackberry": {"code": "blackberry", "title": "BlackBerry", "is_active": True, "created_at": "2026-01-01T00:00:00+00:00"},
        }
        self.committed = 0

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT code, title, is_active, created_at FROM servers ORDER BY code ASC"):
            return _Cursor(rows=[self.rows[key] for key in sorted(self.rows.keys())])
        if normalized.startswith("INSERT INTO servers (code, title, is_active) VALUES"):
            code, title = params
            if code in self.rows:
                return _Cursor(one=None)
            row = {"code": code, "title": title, "is_active": False, "created_at": "2026-04-14T00:00:00+00:00"}
            self.rows[code] = row
            return _Cursor(one=row)
        if normalized.startswith("UPDATE servers SET title = %s WHERE code = %s RETURNING"):
            title, code = params
            row = self.rows.get(code)
            if not row:
                return _Cursor(one=None)
            row["title"] = title
            return _Cursor(one=row)
        if normalized.startswith("UPDATE servers SET is_active = %s WHERE code = %s RETURNING"):
            is_active, code = params
            row = self.rows.get(code)
            if not row:
                return _Cursor(one=None)
            row["is_active"] = bool(is_active)
            return _Cursor(one=row)
        raise AssertionError(f"Unsupported query: {normalized}")

    def commit(self):
        self.committed += 1

    def rollback(self):
        return None

    def close(self):
        return None


class _Backend:
    def __init__(self):
        self.conn = _Connection()

    def connect(self):
        return self.conn


def test_runtime_servers_store_crud():
    store = RuntimeServersStore(_Backend())
    initial = store.list_servers()
    assert len(initial) == 1
    assert initial[0].code == "blackberry"

    created = store.create_server(code="city2", title="City 2")
    assert created.code == "city2"
    assert created.title == "City 2"
    assert created.is_active is False

    updated = store.update_server(code="city2", title="City 2 RU")
    assert updated.title == "City 2 RU"

    toggled = store.set_active(code="city2", is_active=True)
    assert toggled.is_active is True


def test_runtime_servers_store_duplicate_code():
    store = RuntimeServersStore(_Backend())
    try:
        store.create_server(code="blackberry", title="Duplicate")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "server_code_already_exists"
