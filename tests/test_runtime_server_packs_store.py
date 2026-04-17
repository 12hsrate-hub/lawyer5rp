from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.runtime_server_packs_store import RuntimeServerPacksStore


class _Cursor:
    def __init__(self, one=None):
        self._one = one

    def fetchone(self):
        return self._one


class _Connection:
    def __init__(self):
        self.rows = [
            {
                "id": 1,
                "server_code": "blackberry",
                "version": 1,
                "status": "published",
                "metadata_json": {"organizations": ["GOV"]},
                "created_at": "2026-04-16T00:00:00+00:00",
                "published_at": "2026-04-16T00:00:00+00:00",
            }
        ]
        self.committed = 0

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())
        if "OFFSET 1 LIMIT 1" in normalized and "WHERE server_code = %s AND status = 'published'" in normalized:
            rows = [row for row in self.rows if row["server_code"] == params[0] and row["status"] == "published"]
            rows.sort(key=lambda row: (row["version"], row["id"]), reverse=True)
            return _Cursor(one=rows[1] if len(rows) > 1 else None)
        if "WHERE server_code = %s AND status = 'published'" in normalized and normalized.startswith("SELECT id, server_code"):
            rows = [row for row in self.rows if row["server_code"] == params[0] and row["status"] == "published"]
            rows.sort(key=lambda row: (row["version"], row["id"]), reverse=True)
            return _Cursor(one=rows[0] if rows else None)
        if "WHERE server_code = %s AND status = 'draft'" in normalized and normalized.startswith("SELECT id, server_code"):
            rows = [row for row in self.rows if row["server_code"] == params[0] and row["status"] == "draft"]
            rows.sort(key=lambda row: (row["version"], row["id"]), reverse=True)
            return _Cursor(one=rows[0] if rows else None)
        if normalized.startswith("SELECT version FROM server_packs"):
            rows = [row for row in self.rows if row["server_code"] == params[0] and row["status"] == "published"]
            rows.sort(key=lambda row: (row["version"], row["id"]), reverse=True)
            return _Cursor(one={"version": rows[0]["version"]} if rows else None)
        if normalized.startswith("SELECT id, server_code, version, status, metadata_json, created_at, published_at FROM server_packs WHERE server_code = %s AND status = 'published' AND version = %s LIMIT 1"):
            row = next(
                (item for item in self.rows if item["server_code"] == params[0] and item["status"] == "published" and int(item["version"]) == int(params[1])),
                None,
            )
            return _Cursor(one=row)
        if normalized.startswith("INSERT INTO server_packs") and "VALUES (%s, %s, 'published'," in normalized:
            server_code, version, metadata_json = params
            row = {
                "id": len(self.rows) + 1,
                "server_code": server_code,
                "version": int(version),
                "status": "published",
                "metadata_json": __import__("json").loads(metadata_json),
                "created_at": "2026-04-17T02:00:00+00:00",
                "published_at": "2026-04-17T02:00:00+00:00",
            }
            self.rows.append(row)
            return _Cursor(one=row)
        if normalized.startswith("INSERT INTO server_packs"):
            server_code, version, metadata_json = params
            row = {
                "id": len(self.rows) + 1,
                "server_code": server_code,
                "version": int(version),
                "status": "draft",
                "metadata_json": __import__("json").loads(metadata_json),
                "created_at": "2026-04-17T00:00:00+00:00",
                "published_at": "",
            }
            self.rows.append(row)
            return _Cursor(one=row)
        if normalized.startswith("UPDATE server_packs SET metadata_json = %s::jsonb WHERE id = %s RETURNING"):
            metadata_json, row_id = params
            row = next((item for item in self.rows if int(item["id"]) == int(row_id)), None)
            if row is None:
                return _Cursor(one=None)
            row["metadata_json"] = __import__("json").loads(metadata_json)
            return _Cursor(one=row)
        if normalized.startswith("SELECT id FROM server_packs"):
            rows = [row for row in self.rows if row["server_code"] == params[0] and row["status"] == "draft"]
            rows.sort(key=lambda row: (row["version"], row["id"]), reverse=True)
            return _Cursor(one={"id": rows[0]["id"]} if rows else None)
        if normalized.startswith("UPDATE server_packs SET status = 'published', published_at = NOW() WHERE id = %s RETURNING"):
            row = next((item for item in self.rows if int(item["id"]) == int(params[0])), None)
            if row is None:
                return _Cursor(one=None)
            row["status"] = "published"
            row["published_at"] = "2026-04-17T01:00:00+00:00"
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


def test_runtime_server_packs_store_save_and_publish_flow():
    store = RuntimeServerPacksStore(_Backend())

    published = store.get_latest_published_pack(server_code="blackberry")
    assert published is not None
    assert published.version == 1

    draft = store.save_draft_pack(server_code="blackberry", metadata_json={"organizations": ["GOV", "DOJ"]})
    assert draft.status == "draft"
    assert draft.version == 2

    updated_draft = store.save_draft_pack(server_code="blackberry", metadata_json={"organizations": ["GOV", "LSPD"]})
    assert updated_draft.id == draft.id
    assert updated_draft.metadata_json["organizations"] == ["GOV", "LSPD"]

    promoted = store.publish_latest_draft_pack(server_code="blackberry")
    assert promoted.status == "published"
    assert promoted.version == 2


def test_runtime_server_packs_store_rolls_back_to_previous_published_pack():
    backend = _Backend()
    backend.conn.rows.append(
        {
            "id": 2,
            "server_code": "blackberry",
            "version": 2,
            "status": "published",
            "metadata_json": {"organizations": ["GOV", "LSPD"]},
            "created_at": "2026-04-17T00:00:00+00:00",
            "published_at": "2026-04-17T01:00:00+00:00",
        }
    )
    store = RuntimeServerPacksStore(backend)

    previous = store.get_previous_published_pack(server_code="blackberry")
    assert previous is not None
    assert previous.version == 1

    rolled_back = store.rollback_to_published_pack(server_code="blackberry")
    assert rolled_back.status == "published"
    assert rolled_back.version == 3
    assert rolled_back.metadata_json["organizations"] == ["GOV"]
