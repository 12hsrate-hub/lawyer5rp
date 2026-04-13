from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import scripts.migrate_admin_catalog_to_db as migration


class FakeLegacyStore:
    def iter_legacy_items(self):
        return [
            ("laws", {"id": "law_1", "title": "Law 1", "config": {"a": 1}}),
            ("laws", {"id": "law_1", "title": "Law 1", "config": {"a": 1}}),
        ]


class FakeUserStore:
    def get_user_id(self, username: str):
        _ = username
        return 1


class FakeRepo:
    def __init__(self):
        self.items = {}

    def get_content_item_by_identity(self, *, server_scope, server_id, content_type, content_key):
        return self.items.get((server_scope, server_id, content_type, content_key))


class FakeService:
    def __init__(self, repository, legacy_store=None):
        self.repository = repository
        self.created = 0

    def create_content_item(self, **kwargs):
        key = (kwargs["server_scope"], kwargs["server_id"], kwargs["content_type"], kwargs["content_key"])
        row = {"id": self.created + 1, **kwargs}
        self.repository.items[key] = row
        self.created += 1
        return row

    def create_draft_version(self, **kwargs):
        return {"change_request": {"id": 10}, "version": {"id": 20}, "content_item": {"id": kwargs["content_item_id"]}}

    def submit_change_request(self, **kwargs):
        return {"id": kwargs["change_request_id"]}

    def review_change_request(self, **kwargs):
        return {"ok": True}

    def publish_change_request(self, **kwargs):
        return {"ok": True}


def test_migration_dry_run_and_safe_rerun(monkeypatch):
    fake_repo = FakeRepo()

    monkeypatch.setattr(migration, "AdminCatalogStore", lambda: FakeLegacyStore())
    monkeypatch.setattr(migration, "get_database_backend", lambda: object())
    monkeypatch.setattr(migration, "ContentWorkflowRepository", lambda backend: fake_repo)
    monkeypatch.setattr(migration, "ContentWorkflowService", FakeService)
    monkeypatch.setattr(migration, "get_user_store_for_migration", lambda: FakeUserStore())

    summary = migration.migrate(dry_run=True)
    assert summary["migrated_items"] == 2

    summary_real = migration.migrate(dry_run=False, safe_rerun=True)
    assert summary_real["migrated_items"] == 1
    assert summary_real["skipped"] == 1
    assert summary_real["errors"] == 0
