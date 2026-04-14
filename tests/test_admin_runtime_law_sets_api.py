from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

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
from ogp_web.dependencies import get_runtime_law_sets_store
import ogp_web.routes.admin as admin_route
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


class _FakeRuntimeLawSetsStore:
    def __init__(self):
        self.law_sets = {
            1: {"id": 1, "server_code": "blackberry", "name": "Default", "is_active": True, "is_published": True, "item_count": 1}
        }
        self.sources = {
            1: {"id": 1, "name": "Main", "kind": "url", "url": "https://example.com/law/a", "is_active": True}
        }

    class _Source:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def list_law_sets(self, *, server_code: str):
        return [row for row in self.law_sets.values() if row["server_code"] == server_code]

    def create_law_set(self, *, server_code: str, name: str):
        next_id = max(self.law_sets.keys()) + 1
        row = {"id": next_id, "server_code": server_code, "name": name, "is_active": True, "is_published": False}
        self.law_sets[next_id] = {**row, "item_count": 0}
        return row

    def replace_law_set_items(self, *, law_set_id: int, items):
        self.law_sets[law_set_id]["item_count"] = len(items)
        return list(items)

    def update_law_set(self, *, law_set_id: int, name: str, is_active: bool):
        if law_set_id not in self.law_sets:
            raise KeyError("law_set_not_found")
        self.law_sets[law_set_id]["name"] = name
        self.law_sets[law_set_id]["is_active"] = bool(is_active)
        return {k: self.law_sets[law_set_id][k] for k in ("id", "server_code", "name", "is_active", "is_published")}

    def publish_law_set(self, *, law_set_id: int):
        if law_set_id not in self.law_sets:
            raise KeyError("law_set_not_found")
        self.law_sets[law_set_id]["is_published"] = True
        self.law_sets[law_set_id]["is_active"] = True
        return {k: self.law_sets[law_set_id][k] for k in ("id", "server_code", "name", "is_active", "is_published")}

    def list_source_urls_for_law_set(self, *, law_set_id: int):
        if law_set_id not in self.law_sets:
            raise KeyError("law_set_not_found")
        return self.law_sets[law_set_id]["server_code"], ["https://example.com/law/a"]

    def list_server_law_bindings(self, *, server_code: str):
        return [
            {
                "law_set_id": 1,
                "law_set_name": "Default",
                "item_id": 1,
                "law_code": "uk",
                "priority": 100,
                "effective_from": "",
                "source_name": "Main",
                "source_url": "https://example.com/law/a",
            }
        ] if server_code == "blackberry" else []

    def add_server_law_binding(self, *, server_code: str, law_code: str, source_id: int, effective_from: str = "", priority: int = 100, law_set_id=None):
        if law_set_id is not None:
            set_row = self.law_sets.get(int(law_set_id))
            if not set_row:
                raise ValueError("law_set_not_found")
            if str(set_row.get("server_code") or "").strip().lower() != str(server_code or "").strip().lower():
                raise ValueError("law_set_server_mismatch")
        return {
            "id": 88,
            "law_set_id": int(law_set_id or 1),
            "law_code": law_code,
            "source_id": source_id,
            "priority": priority,
            "effective_from": effective_from,
            "server_code": server_code,
        }

    def list_sources(self):
        return [self._Source(**item) for item in self.sources.values()]

    def create_source(self, *, name: str, kind: str, url: str):
        next_id = max(self.sources.keys()) + 1
        row = {"id": next_id, "name": name, "kind": kind, "url": url, "is_active": True}
        self.sources[next_id] = row
        return self._Source(**row)

    def update_source(self, *, source_id: int, name: str, kind: str, url: str, is_active: bool):
        if source_id not in self.sources:
            raise KeyError("law_source_not_found")
        self.sources[source_id] = {"id": source_id, "name": name, "kind": kind, "url": url, "is_active": bool(is_active)}
        return self._Source(**self.sources[source_id])


class AdminRuntimeLawSetsApiTests(unittest.TestCase):
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
        self.store = _FakeRuntimeLawSetsStore()
        app.dependency_overrides[get_runtime_law_sets_store] = lambda: self.store
        class DummyWorkflowService:
            repository = object()

        app.dependency_overrides[admin_route.get_content_workflow_service] = lambda: DummyWorkflowService()
        self.client = TestClient(app, base_url="https://testserver")
        reset_rate_limit(self.client.app.state.rate_limiter)
        self._register_and_login_admin("12345", "admin@example.com")

    def tearDown(self):
        reset_rate_limit(self.client.app.state.rate_limiter)
        self.client.app.dependency_overrides.pop(admin_route.get_content_workflow_service, None)
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

    def test_law_sets_registry_and_jobs_endpoints(self):
        listed = self.client.get("/api/admin/runtime-servers/blackberry/law-sets")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)

        created = self.client.post(
            "/api/admin/runtime-servers/blackberry/law-sets",
            json={"name": "Draft 2", "is_active": True, "items": [{"law_code": "uk", "priority": 10}]},
        )
        self.assertEqual(created.status_code, 200)
        created_id = created.json()["law_set"]["id"]

        updated = self.client.put(
            f"/api/admin/law-sets/{created_id}",
            json={"name": "Draft 2.1", "is_active": True, "items": []},
        )
        self.assertEqual(updated.status_code, 200)

        published = self.client.post(f"/api/admin/law-sets/{created_id}/publish")
        self.assertEqual(published.status_code, 200)

        with patch("ogp_web.routes.admin.LawAdminService.rebuild_index") as fake_rebuild:
            fake_rebuild.return_value = {"ok": True, "dry_run": True, "article_count": 123}
            rebuild = self.client.post(f"/api/admin/law-sets/{created_id}/rebuild", json={"dry_run": True})
        self.assertEqual(rebuild.status_code, 200)
        self.assertTrue(rebuild.json()["result"]["dry_run"])

        with patch("ogp_web.routes.admin.LawAdminService.rollback_active_version") as fake_rollback:
            fake_rollback.return_value = {"ok": True, "active_law_version_id": 7}
            rollback = self.client.post(f"/api/admin/law-sets/{created_id}/rollback", json={})
        self.assertEqual(rollback.status_code, 200)
        self.assertEqual(rollback.json()["result"]["active_law_version_id"], 7)

        source_list = self.client.get("/api/admin/law-source-registry")
        self.assertEqual(source_list.status_code, 200)
        self.assertGreaterEqual(source_list.json()["count"], 1)

        source_create = self.client.post(
            "/api/admin/law-source-registry",
            json={"name": "Backup", "kind": "url", "url": "https://example.com/law/b", "is_active": True},
        )
        self.assertEqual(source_create.status_code, 200)
        source_id = source_create.json()["item"]["id"]

        source_update = self.client.put(
            f"/api/admin/law-source-registry/{source_id}",
            json={"name": "Backup v2", "kind": "url", "url": "https://example.com/law/b2", "is_active": True},
        )
        self.assertEqual(source_update.status_code, 200)

        jobs = self.client.get("/api/admin/law-jobs/overview")
        self.assertEqual(jobs.status_code, 200)
        self.assertIn("summary", jobs.json())

        bindings = self.client.get("/api/admin/runtime-servers/blackberry/law-bindings")
        self.assertEqual(bindings.status_code, 200)
        self.assertGreaterEqual(bindings.json()["count"], 1)

        bind_added = self.client.post(
            "/api/admin/runtime-servers/blackberry/law-bindings",
            json={"law_code": "custom_law", "source_id": 1, "priority": 50, "effective_from": ""},
        )
        self.assertEqual(bind_added.status_code, 200)
        self.assertEqual(bind_added.json()["item"]["law_code"], "custom_law")

        self.store.law_sets[9] = {"id": 9, "server_code": "vinewood", "name": "Foreign", "is_active": True, "is_published": False, "item_count": 0}
        bind_foreign = self.client.post(
            "/api/admin/runtime-servers/blackberry/law-bindings",
            json={"law_code": "cross_server_law", "source_id": 1, "law_set_id": 9},
        )
        self.assertEqual(bind_foreign.status_code, 400)
        self.assertIn("law_set_server_mismatch", " ".join(bind_foreign.json().get("detail") or []))


if __name__ == "__main__":
    unittest.main()
