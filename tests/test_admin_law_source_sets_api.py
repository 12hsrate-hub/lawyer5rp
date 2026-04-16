from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_WEB_SECRET", "test-secret")
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
os.environ.setdefault("OGP_SKIP_DEFAULT_APP_INIT", "1")

from fastapi.testclient import TestClient

from ogp_web.app import create_app
from ogp_web.dependencies import get_law_source_sets_store
from ogp_web.rate_limit import reset_for_testing as reset_rate_limit
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_repository import UserRepository
from ogp_web.storage.user_store import UserStore
from tests.temp_helpers import make_temporary_directory
from tests.test_web_storage import (
    FakeAdminMetricsPostgresBackend,
    FakeExamAnswersPostgresBackend,
    FakeExamImportTasksPostgresBackend,
    PostgresBackend,
)
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry


class _FakeLawSourceSetsStore:
    def __init__(self):
        self.source_sets = {
            "orange-core": {
                "source_set_key": "orange-core",
                "title": "Orange core",
                "description": "Primary containers",
                "scope": "global",
                "created_at": "2026-04-16T00:00:00+00:00",
                "updated_at": "2026-04-16T00:00:00+00:00",
            }
        }
        self.next_revision_id = 8
        self.next_binding_id = 4
        self.revisions = {
            "orange-core": [
                {
                    "id": 7,
                    "source_set_key": "orange-core",
                    "revision": 2,
                    "status": "published",
                    "container_urls": ("https://example.com/a", "https://example.com/b"),
                    "adapter_policy_json": {"extractor": "forum_topic"},
                    "metadata_json": {"promotion_mode": "hybrid"},
                    "created_at": "2026-04-16T00:05:00+00:00",
                    "published_at": "2026-04-16T00:06:00+00:00",
                }
            ]
        }
        self.bindings = {
            "orange": [
                {
                    "id": 3,
                    "server_code": "orange",
                    "source_set_key": "orange-core",
                    "priority": 10,
                    "is_active": True,
                    "include_law_keys": ("law.alpha",),
                    "exclude_law_keys": ("law.beta",),
                    "pin_policy_json": {"freeze": True},
                    "metadata_json": {"origin": "phase2"},
                    "created_at": "2026-04-16T00:10:00+00:00",
                    "updated_at": "2026-04-16T00:10:00+00:00",
                }
            ]
        }

    class _SourceSet:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Revision:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Binding:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def list_source_sets(self):
        return [self._SourceSet(**item) for _, item in sorted(self.source_sets.items())]

    def get_source_set(self, *, source_set_key: str):
        row = self.source_sets.get(source_set_key)
        return self._SourceSet(**row) if row else None

    def create_source_set(self, *, source_set_key: str, title: str, description: str = "", scope: str = "global"):
        if source_set_key in self.source_sets:
            raise ValueError("source_set_key_already_exists")
        row = {
            "source_set_key": source_set_key,
            "title": title,
            "description": description,
            "scope": scope,
            "created_at": "2026-04-16T00:20:00+00:00",
            "updated_at": "2026-04-16T00:20:00+00:00",
        }
        self.source_sets[source_set_key] = row
        return self._SourceSet(**row)

    def update_source_set(self, *, source_set_key: str, title: str, description: str = ""):
        row = self.source_sets.get(source_set_key)
        if not row:
            raise KeyError("source_set_not_found")
        row["title"] = title
        row["description"] = description
        row["updated_at"] = "2026-04-16T00:30:00+00:00"
        return self._SourceSet(**row)

    def list_revisions(self, *, source_set_key: str):
        return [self._Revision(**item) for item in self.revisions.get(source_set_key, [])]

    def create_revision(self, *, source_set_key: str, container_urls, adapter_policy_json=None, metadata_json=None, status="draft"):
        if source_set_key not in self.source_sets:
            raise KeyError("source_set_not_found")
        row = {
            "id": self.next_revision_id,
            "source_set_key": source_set_key,
            "revision": len(self.revisions.get(source_set_key, [])) + 1,
            "status": status,
            "container_urls": tuple(container_urls),
            "adapter_policy_json": dict(adapter_policy_json or {}),
            "metadata_json": dict(metadata_json or {}),
            "created_at": "2026-04-16T00:25:00+00:00",
            "published_at": "2026-04-16T00:26:00+00:00" if status == "published" else None,
        }
        self.next_revision_id += 1
        self.revisions.setdefault(source_set_key, []).insert(0, row)
        return self._Revision(**row)

    def list_bindings(self, *, server_code: str):
        return [self._Binding(**item) for item in self.bindings.get(server_code, [])]

    def create_binding(self, *, server_code: str, source_set_key: str, priority: int = 100, is_active: bool = True, include_law_keys=None, exclude_law_keys=None, pin_policy_json=None, metadata_json=None):
        if source_set_key not in self.source_sets:
            raise KeyError("source_set_not_found")
        if any(item["source_set_key"] == source_set_key for item in self.bindings.get(server_code, [])):
            raise ValueError("server_source_set_binding_already_exists")
        row = {
            "id": self.next_binding_id,
            "server_code": server_code,
            "source_set_key": source_set_key,
            "priority": priority,
            "is_active": is_active,
            "include_law_keys": tuple(include_law_keys or ()),
            "exclude_law_keys": tuple(exclude_law_keys or ()),
            "pin_policy_json": dict(pin_policy_json or {}),
            "metadata_json": dict(metadata_json or {}),
            "created_at": "2026-04-16T00:35:00+00:00",
            "updated_at": "2026-04-16T00:35:00+00:00",
        }
        self.next_binding_id += 1
        self.bindings.setdefault(server_code, []).append(row)
        return self._Binding(**row)

    def update_binding(self, *, binding_id: int, server_code: str, source_set_key: str, priority: int = 100, is_active: bool = True, include_law_keys=None, exclude_law_keys=None, pin_policy_json=None, metadata_json=None):
        rows = self.bindings.get(server_code, [])
        row = next((item for item in rows if int(item["id"]) == int(binding_id)), None)
        if not row:
            raise KeyError("server_source_set_binding_not_found")
        if source_set_key not in self.source_sets:
            raise KeyError("source_set_not_found")
        if any(item["source_set_key"] == source_set_key and int(item["id"]) != int(binding_id) for item in rows):
            raise ValueError("server_source_set_binding_already_exists")
        row.update(
            {
                "source_set_key": source_set_key,
                "priority": priority,
                "is_active": is_active,
                "include_law_keys": tuple(include_law_keys or ()),
                "exclude_law_keys": tuple(exclude_law_keys or ()),
                "pin_policy_json": dict(pin_policy_json or {}),
                "metadata_json": dict(metadata_json or {}),
                "updated_at": "2026-04-16T00:40:00+00:00",
            }
        )
        return self._Binding(**row)


class AdminLawSourceSetsApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = make_temporary_directory()
        root = Path(self.tmpdir.name)
        self.user_store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(PostgresBackend()),
        )
        self.exam_store = ExamAnswersStore(root / "exam_answers.db", backend=FakeExamAnswersPostgresBackend())
        self.admin_store = AdminMetricsStore(root / "admin_metrics.db", backend=FakeAdminMetricsPostgresBackend())
        self.task_registry = ExamImportTaskRegistry(
            root / "exam_import_tasks.db",
            backend=FakeExamImportTasksPostgresBackend(),
        )
        app = create_app(self.user_store, self.exam_store, self.admin_store, self.task_registry)
        self.store = _FakeLawSourceSetsStore()
        app.dependency_overrides[get_law_source_sets_store] = lambda: self.store
        self.client = TestClient(app, base_url="https://testserver")
        reset_rate_limit(self.client.app.state.rate_limiter)
        self._register_and_login_admin("12345", "admin@example.com")

    def tearDown(self):
        reset_rate_limit(self.client.app.state.rate_limiter)
        self.client.close()
        self.client.app.state.rate_limiter.repository.close()
        self.user_store.repository.close()
        self.tmpdir.cleanup()

    def _register_and_login_admin(self, username: str, email: str):
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "email": email, "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        login = self.client.post("/api/auth/login", json={"username": username, "password": "Password123!"})
        self.assertEqual(login.status_code, 200)

    def test_admin_law_source_set_read_endpoints(self):
        listed = self.client.get("/api/admin/law-source-sets")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)
        self.assertEqual(listed.json()["items"][0]["source_set_key"], "orange-core")

        revisions = self.client.get("/api/admin/law-source-sets/orange-core/revisions")
        self.assertEqual(revisions.status_code, 200)
        self.assertEqual(revisions.json()["count"], 1)
        self.assertEqual(revisions.json()["source_set"]["source_set_key"], "orange-core")
        self.assertEqual(revisions.json()["items"][0]["status"], "published")

        bindings = self.client.get("/api/admin/runtime-servers/orange/source-set-bindings")
        self.assertEqual(bindings.status_code, 200)
        self.assertEqual(bindings.json()["count"], 1)
        self.assertEqual(bindings.json()["items"][0]["source_set_key"], "orange-core")

    def test_admin_law_source_set_revisions_returns_404_for_missing_set(self):
        response = self.client.get("/api/admin/law-source-sets/missing/revisions")
        self.assertEqual(response.status_code, 404)
        self.assertIn("source_set_not_found", " ".join(response.json().get("detail") or []))

    def test_admin_law_source_set_mutation_endpoints(self):
        created = self.client.post(
            "/api/admin/law-source-sets",
            json={
                "source_set_key": "citrus-laws",
                "title": "Citrus laws",
                "description": "Container sources",
                "scope": "global",
            },
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["item"]["source_set_key"], "citrus-laws")

        updated = self.client.put(
            "/api/admin/law-source-sets/citrus-laws",
            json={
                "source_set_key": "citrus-laws",
                "title": "Citrus laws updated",
                "description": "Updated metadata",
                "scope": "global",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["item"]["title"], "Citrus laws updated")

        created_revision = self.client.post(
            "/api/admin/law-source-sets/citrus-laws/revisions",
            json={
                "container_urls": ["https://example.com/root", "https://example.com/root-2"],
                "adapter_policy_json": {"extractor": "forum"},
                "metadata_json": {"mode": "hybrid"},
                "status": "draft",
            },
        )
        self.assertEqual(created_revision.status_code, 200)
        self.assertEqual(created_revision.json()["item"]["source_set_key"], "citrus-laws")
        self.assertEqual(len(created_revision.json()["item"]["container_urls"]), 2)

        invalid_revision = self.client.post(
            "/api/admin/law-source-sets/citrus-laws/revisions",
            json={"container_urls": []},
        )
        self.assertEqual(invalid_revision.status_code, 422)

    def test_admin_server_source_set_binding_mutation_endpoints(self):
        created = self.client.post(
            "/api/admin/runtime-servers/orange/source-set-bindings",
            json={
                "source_set_key": "orange-core",
                "priority": 20,
                "is_active": True,
                "include_law_keys": ["law.alpha"],
                "exclude_law_keys": ["law.beta"],
                "pin_policy_json": {"freeze": True},
                "metadata_json": {"origin": "ui"},
            },
        )
        self.assertEqual(created.status_code, 400)
        self.assertIn("server_source_set_binding_already_exists", " ".join(created.json().get("detail") or []))

        created_second = self.client.post(
            "/api/admin/runtime-servers/orange/source-set-bindings",
            json={
                "source_set_key": "citrus-laws",
                "priority": 30,
                "is_active": False,
                "include_law_keys": ["law.gamma"],
                "exclude_law_keys": [],
                "pin_policy_json": {},
                "metadata_json": {"origin": "ui"},
            },
        )
        self.assertEqual(created_second.status_code, 404)

        self.store.create_source_set(source_set_key="citrus-laws", title="Citrus", description="", scope="global")
        created_second = self.client.post(
            "/api/admin/runtime-servers/orange/source-set-bindings",
            json={
                "source_set_key": "citrus-laws",
                "priority": 30,
                "is_active": False,
                "include_law_keys": ["law.gamma"],
                "exclude_law_keys": [],
                "pin_policy_json": {},
                "metadata_json": {"origin": "ui"},
            },
        )
        self.assertEqual(created_second.status_code, 200)
        binding_id = created_second.json()["item"]["id"]

        updated = self.client.put(
            f"/api/admin/runtime-servers/orange/source-set-bindings/{binding_id}",
            json={
                "source_set_key": "citrus-laws",
                "priority": 15,
                "is_active": True,
                "include_law_keys": ["law.gamma", "law.delta"],
                "exclude_law_keys": ["law.hidden"],
                "pin_policy_json": {"freeze": False},
                "metadata_json": {"origin": "ui-edit"},
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["item"]["priority"], 15)
        self.assertTrue(updated.json()["item"]["is_active"])


if __name__ == "__main__":
    unittest.main()
