from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_WEB_SECRET", "test-secret")
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
os.environ.setdefault("OGP_SKIP_DEFAULT_APP_INIT", "1")

from ogp_web.services.admin_law_sets_service import (
    add_runtime_server_law_binding_payload,
    create_law_source_registry_payload,
    create_runtime_server_law_set_payload,
    list_law_source_registry_payload,
    list_runtime_server_law_bindings_payload,
    list_runtime_server_law_sets_payload,
    publish_law_set_payload,
    resolve_law_set_rebuild_context,
    resolve_law_set_rollback_context,
    update_law_set_payload,
    update_law_source_registry_payload,
)


class _FakeRuntimeLawSetsStore:
    class _Source:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def __init__(self) -> None:
        self.law_sets = {
            1: {"id": 1, "server_code": "blackberry", "name": "Default", "is_active": True, "is_published": True, "item_count": 1}
        }
        self.sources = {
            1: {"id": 1, "name": "Main", "kind": "url", "url": "https://example.com/law/a", "is_active": True}
        }

    def list_law_sets(self, *, server_code: str):
        return [row for row in self.law_sets.values() if row["server_code"] == server_code]

    def list_server_law_bindings(self, *, server_code: str):
        return [
            {
                "law_set_id": 1,
                "law_set_name": "Default",
                "law_code": "uk",
                "priority": 100,
                "source_name": "Main",
            }
        ] if server_code == "blackberry" else []

    def add_server_law_binding(self, *, server_code: str, law_code: str, source_id: int, effective_from: str = "", priority: int = 100, law_set_id=None):
        return {
            "id": 9,
            "server_code": server_code,
            "law_code": law_code,
            "source_id": source_id,
            "effective_from": effective_from,
            "priority": priority,
            "law_set_id": int(law_set_id or 1),
        }

    def create_law_set(self, *, server_code: str, name: str):
        next_id = max(self.law_sets.keys()) + 1
        row = {"id": next_id, "server_code": server_code, "name": name, "is_active": True, "is_published": False}
        self.law_sets[next_id] = {**row, "item_count": 0}
        return row

    def replace_law_set_items(self, *, law_set_id: int, items):
        self.law_sets[law_set_id]["item_count"] = len(items)
        return list(items)

    def update_law_set(self, *, law_set_id: int, name: str, is_active: bool):
        row = self.law_sets[law_set_id]
        row["name"] = name
        row["is_active"] = bool(is_active)
        return {k: row[k] for k in ("id", "server_code", "name", "is_active", "is_published")}

    def publish_law_set(self, *, law_set_id: int):
        row = self.law_sets[law_set_id]
        row["is_published"] = True
        row["is_active"] = True
        return {k: row[k] for k in ("id", "server_code", "name", "is_active", "is_published")}

    def list_source_urls_for_law_set(self, *, law_set_id: int):
        if law_set_id == 2:
            return "blackberry", []
        return self.law_sets[law_set_id]["server_code"], ["https://example.com/law/a"]

    def list_sources(self):
        return [self._Source(**item) for item in self.sources.values()]

    def create_source(self, *, name: str, kind: str, url: str):
        next_id = max(self.sources.keys()) + 1
        row = {"id": next_id, "name": name, "kind": kind, "url": url, "is_active": True}
        self.sources[next_id] = row
        return self._Source(**row)

    def update_source(self, *, source_id: int, name: str, kind: str, url: str, is_active: bool):
        row = {"id": source_id, "name": name, "kind": kind, "url": url, "is_active": bool(is_active)}
        self.sources[source_id] = row
        return self._Source(**row)


class AdminLawSetsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _FakeRuntimeLawSetsStore()

    def test_runtime_server_lists_normalize_server_code(self):
        law_sets_payload = list_runtime_server_law_sets_payload(store=self.store, server_code=" BlackBerry ")
        bindings_payload = list_runtime_server_law_bindings_payload(store=self.store, server_code=" BlackBerry ")

        self.assertEqual(law_sets_payload["server_code"], "blackberry")
        self.assertEqual(law_sets_payload["count"], 1)
        self.assertEqual(bindings_payload["server_code"], "blackberry")
        self.assertEqual(bindings_payload["count"], 1)

    def test_create_update_publish_and_binding_payloads(self):
        created = create_runtime_server_law_set_payload(
            store=self.store,
            server_code=" BlackBerry ",
            name="Draft 2",
            items=[{"law_code": "uk", "priority": 50}],
        )
        law_set_id = created["law_set"]["id"]

        updated = update_law_set_payload(
            store=self.store,
            law_set_id=law_set_id,
            name="Draft 2.1",
            is_active=False,
            items=[],
        )
        published = publish_law_set_payload(store=self.store, law_set_id=law_set_id)
        binding = add_runtime_server_law_binding_payload(
            store=self.store,
            server_code=" BlackBerry ",
            law_code="uk",
            source_id=1,
            priority=25,
            law_set_id=law_set_id,
        )

        self.assertEqual(created["server_code"], "blackberry")
        self.assertEqual(updated["law_set"]["name"], "Draft 2.1")
        self.assertTrue(published["law_set"]["is_published"])
        self.assertEqual(binding["server_code"], "blackberry")
        self.assertEqual(binding["item"]["law_set_id"], law_set_id)

    def test_rebuild_and_rollback_contexts(self):
        rebuild = resolve_law_set_rebuild_context(store=self.store, law_set_id=1)
        rollback = resolve_law_set_rollback_context(store=self.store, law_set_id=1)

        self.assertEqual(rebuild["server_code"], "blackberry")
        self.assertEqual(rebuild["source_urls"], ["https://example.com/law/a"])
        self.assertEqual(rollback["server_code"], "blackberry")

        with self.assertRaisesRegex(ValueError, "law_set_sources_empty"):
            resolve_law_set_rebuild_context(store=self.store, law_set_id=2)

    def test_law_source_registry_payloads(self):
        listed = list_law_source_registry_payload(store=self.store)
        created = create_law_source_registry_payload(
            store=self.store,
            name="Backup",
            kind="url",
            url="https://example.com/law/b",
        )
        updated = update_law_source_registry_payload(
            store=self.store,
            source_id=created["item"]["id"],
            name="Backup v2",
            kind="url",
            url="https://example.com/law/b2",
            is_active=False,
        )

        self.assertEqual(listed["count"], 1)
        self.assertEqual(created["item"]["name"], "Backup")
        self.assertFalse(updated["item"]["is_active"])


if __name__ == "__main__":
    unittest.main()
