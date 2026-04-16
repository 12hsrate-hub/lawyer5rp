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
from ogp_web.dependencies import get_law_source_discovery_store, get_law_source_sets_store
from ogp_web.rate_limit import reset_for_testing as reset_rate_limit
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry
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


class _FakeLawSourceSetsStore:
    class _SourceSet:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def get_source_set(self, *, source_set_key: str):
        if source_set_key != "orange-core":
            return None
        return self._SourceSet(
            source_set_key="orange-core",
            title="Orange core",
            description="Primary containers",
            scope="global",
            created_at="2026-04-16T00:00:00+00:00",
            updated_at="2026-04-16T00:00:00+00:00",
        )


class _FakeLawSourceDiscoveryStore:
    class _Run:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Link:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def list_runs(self, *, source_set_key: str):
        if source_set_key != "orange-core":
            return []
        return [
            self._Run(
                id=5,
                source_set_revision_id=7,
                source_set_key="orange-core",
                revision=2,
                trigger_mode="manual",
                status="partial_success",
                summary_json={"total_links": 3, "broken_links": 1},
                error_summary="1 broken item",
                created_at="2026-04-16T00:10:00+00:00",
                started_at="2026-04-16T00:10:01+00:00",
                finished_at="2026-04-16T00:10:05+00:00",
            )
        ]

    def get_run(self, *, run_id: int):
        if int(run_id) != 5:
            return None
        return self._Run(
            id=5,
            source_set_revision_id=7,
            source_set_key="orange-core",
            revision=2,
            trigger_mode="manual",
            status="partial_success",
            summary_json={"total_links": 3, "broken_links": 1},
            error_summary="1 broken item",
            created_at="2026-04-16T00:10:00+00:00",
            started_at="2026-04-16T00:10:01+00:00",
            finished_at="2026-04-16T00:10:05+00:00",
        )

    def list_links(self, *, source_discovery_run_id: int):
        if int(source_discovery_run_id) != 5:
            return []
        return [
            self._Link(
                id=9,
                source_discovery_run_id=5,
                source_set_revision_id=7,
                normalized_url="https://example.com/law/a",
                source_container_url="https://example.com/topic/1",
                discovery_status="discovered",
                alias_hints_json={"raw_url": "https://example.com/law/a?ref=topic"},
                metadata_json={"position": 1},
                first_seen_at="2026-04-16T00:10:02+00:00",
                last_seen_at="2026-04-16T00:10:02+00:00",
                created_at="2026-04-16T00:10:02+00:00",
                updated_at="2026-04-16T00:10:02+00:00",
            )
        ]


class AdminLawSourceDiscoveryApiTests(unittest.TestCase):
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
        app.dependency_overrides[get_law_source_sets_store] = lambda: _FakeLawSourceSetsStore()
        app.dependency_overrides[get_law_source_discovery_store] = lambda: _FakeLawSourceDiscoveryStore()
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

    def test_admin_law_source_discovery_read_endpoints(self):
        runs = self.client.get("/api/admin/law-source-sets/orange-core/discovery-runs")
        self.assertEqual(runs.status_code, 200)
        self.assertEqual(runs.json()["count"], 1)
        self.assertEqual(runs.json()["items"][0]["status"], "partial_success")

        links = self.client.get("/api/admin/law-source-discovery-runs/5/links")
        self.assertEqual(links.status_code, 200)
        self.assertEqual(links.json()["count"], 1)
        self.assertEqual(links.json()["items"][0]["normalized_url"], "https://example.com/law/a")

    def test_admin_law_source_discovery_missing_resources(self):
        missing_source_set = self.client.get("/api/admin/law-source-sets/missing/discovery-runs")
        self.assertEqual(missing_source_set.status_code, 404)
        self.assertIn("source_set_not_found", " ".join(missing_source_set.json().get("detail") or []))

        missing_run = self.client.get("/api/admin/law-source-discovery-runs/999/links")
        self.assertEqual(missing_run.status_code, 404)
        self.assertIn("source_discovery_run_not_found", " ".join(missing_run.json().get("detail") or []))


if __name__ == "__main__":
    unittest.main()
