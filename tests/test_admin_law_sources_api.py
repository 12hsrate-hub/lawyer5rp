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
from ogp_web.dependencies import get_content_workflow_service, get_law_source_sets_store
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
        self.source_sets: dict[str, dict[str, object]] = {}
        self.revisions: dict[str, list[dict[str, object]]] = {}
        self.bindings: dict[str, list[dict[str, object]]] = {}
        self.next_revision_id = 1
        self.next_binding_id = 1

    class _SourceSet:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Revision:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Binding:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def get_source_set(self, *, source_set_key: str):
        row = self.source_sets.get(source_set_key)
        return self._SourceSet(**row) if row else None

    def create_source_set(self, *, source_set_key: str, title: str, description: str = "", scope: str = "global"):
        row = {
            "source_set_key": source_set_key,
            "title": title,
            "description": description,
            "scope": scope,
        }
        self.source_sets[source_set_key] = row
        return self._SourceSet(**row)

    def list_revisions(self, *, source_set_key: str):
        return [self._Revision(**item) for item in self.revisions.get(source_set_key, [])]

    def create_revision(self, *, source_set_key: str, container_urls, adapter_policy_json=None, metadata_json=None, status="draft"):
        row = {
            "id": self.next_revision_id,
            "source_set_key": source_set_key,
            "revision": len(self.revisions.get(source_set_key, [])) + 1,
            "status": status,
            "container_urls": tuple(container_urls),
            "adapter_policy_json": dict(adapter_policy_json or {}),
            "metadata_json": dict(metadata_json or {}),
        }
        self.next_revision_id += 1
        self.revisions.setdefault(source_set_key, []).insert(0, row)
        return self._Revision(**row)

    def list_bindings(self, *, server_code: str):
        return [self._Binding(**item) for item in self.bindings.get(server_code, [])]

    def create_binding(self, *, server_code: str, source_set_key: str, priority: int = 100, is_active: bool = True, metadata_json=None, **kwargs):
        _ = kwargs
        row = {
            "id": self.next_binding_id,
            "server_code": server_code,
            "source_set_key": source_set_key,
            "priority": priority,
            "is_active": is_active,
            "metadata_json": dict(metadata_json or {}),
        }
        self.next_binding_id += 1
        self.bindings.setdefault(server_code, []).append(row)
        return self._Binding(**row)


class _FakeWorkflowService:
    repository = object()


class AdminLawSourcesApiTests(unittest.TestCase):
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
        app.dependency_overrides[get_content_workflow_service] = lambda: _FakeWorkflowService()
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

    def test_admin_law_sources_backfill_source_set_endpoint(self):
        from unittest.mock import patch

        with patch(
            "ogp_web.services.admin_law_sources_service.LawAdminService.get_effective_sources",
            return_value=type(
                "Snapshot",
                (),
                {
                    "source_urls": ("https://example.com/law/a",),
                    "source_origin": "content_workflow",
                },
            )(),
        ):
            response = self.client.post("/api/admin/law-sources/backfill-source-set", json={"server_code": ""})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["server_code"], "blackberry")
        self.assertEqual(payload["source_set_key"], "legacy-blackberry-default")
        self.assertTrue(payload["revision_created"])
        self.assertTrue(payload["binding_created"])

    def test_admin_law_sources_backfill_source_set_rejects_missing_sources(self):
        from unittest.mock import patch

        with patch(
            "ogp_web.services.admin_law_sources_service.LawAdminService.get_effective_sources",
            return_value=type(
                "Snapshot",
                (),
                {
                    "source_urls": (),
                    "source_origin": "server_config",
                },
            )(),
        ):
            response = self.client.post("/api/admin/law-sources/backfill-source-set", json={"server_code": ""})

        self.assertEqual(response.status_code, 400)
        self.assertIn("server_has_no_law_qa_sources", " ".join(response.json().get("detail") or []))


if __name__ == "__main__":
    unittest.main()
