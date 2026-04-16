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

    def list_revisions(self, *, source_set_key: str):
        return [self._Revision(**item) for item in self.revisions.get(source_set_key, [])]

    def list_bindings(self, *, server_code: str):
        return [self._Binding(**item) for item in self.bindings.get(server_code, [])]


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


if __name__ == "__main__":
    unittest.main()
