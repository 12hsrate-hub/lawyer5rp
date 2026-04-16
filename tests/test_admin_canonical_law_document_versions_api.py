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
from ogp_web.dependencies import (
    get_canonical_law_documents_store,
    get_canonical_law_document_versions_store,
    get_law_source_discovery_store,
)
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


class _FakeDiscoveryStore:
    class _Run:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Link:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def get_run(self, *, run_id: int):
        if int(run_id) != 5:
            return None
        return self._Run(
            id=5,
            source_set_revision_id=7,
            source_set_key="orange-core",
            revision=2,
            trigger_mode="manual",
            status="succeeded",
            summary_json={"discovered_links": 1},
            error_summary="",
        )

    def list_links(self, *, source_discovery_run_id: int):
        if int(source_discovery_run_id) != 5:
            return []
        return [
            self._Link(
                id=11,
                source_discovery_run_id=5,
                source_set_revision_id=7,
                normalized_url="https://example.com/law/a",
                source_container_url="https://example.com/topic/1",
                discovery_status="discovered",
                alias_hints_json={},
                metadata_json={},
            )
        ]


class _FakeDocumentsStore:
    class _Resolved:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def resolve_document_by_alias(self, *, normalized_url: str):
        if normalized_url != "https://example.com/law/a":
            return None
        return self._Resolved(
            document_id=1,
            canonical_identity_key="url_seed:abc",
            identity_source="url_seed",
            display_title="Procedural Code",
            document_metadata_json={},
            alias_id=1,
            normalized_url=normalized_url,
            alias_kind="canonical",
            is_active=True,
            alias_metadata_json={},
        )


class _FakeVersionsStore:
    class _Version:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def __init__(self):
        self.items = []

    def get_version_by_discovered_link(self, *, discovered_law_link_id: int):
        return next((row for row in self.items if int(row.discovered_law_link_id) == int(discovered_law_link_id)), None)

    def create_version(self, **kwargs):
        payload = {
            "id": len(self.items) + 1,
            "canonical_identity_key": "url_seed:abc",
            "display_title": "Procedural Code",
            "source_set_key": "orange-core",
            "source_set_revision_id": 7,
            "revision": 2,
            "normalized_url": "https://example.com/law/a",
            "source_container_url": "https://example.com/topic/1",
            "raw_title": "Procedural Code",
            "parsed_title": "",
            "body_text": "",
            "created_at": "2026-04-16T02:00:00+00:00",
            "updated_at": "2026-04-16T02:00:00+00:00",
        }
        payload.update(kwargs)
        item = self._Version(**payload)
        self.items.append(item)
        return item

    def list_versions_for_run(self, *, source_discovery_run_id: int):
        return [item for item in self.items if int(item.source_discovery_run_id) == int(source_discovery_run_id)]

    def list_versions_for_document(self, *, canonical_law_document_id: int):
        return [item for item in self.items if int(item.canonical_law_document_id) == int(canonical_law_document_id)]


class AdminCanonicalLawDocumentVersionsApiTests(unittest.TestCase):
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
        self.discovery_store = _FakeDiscoveryStore()
        self.documents_store = _FakeDocumentsStore()
        self.versions_store = _FakeVersionsStore()
        app.dependency_overrides[get_law_source_discovery_store] = lambda: self.discovery_store
        app.dependency_overrides[get_canonical_law_documents_store] = lambda: self.documents_store
        app.dependency_overrides[get_canonical_law_document_versions_store] = lambda: self.versions_store
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

    def test_admin_canonical_law_document_versions_endpoints(self):
        ingest = self.client.post("/api/admin/law-source-discovery-runs/5/ingest-document-versions", json={"safe_rerun": True})
        self.assertEqual(ingest.status_code, 200)
        self.assertTrue(ingest.json()["changed"])
        self.assertEqual(ingest.json()["created_versions"], 1)

        by_run = self.client.get("/api/admin/law-source-discovery-runs/5/document-versions")
        self.assertEqual(by_run.status_code, 200)
        self.assertEqual(by_run.json()["count"], 1)
        self.assertEqual(by_run.json()["items"][0]["fetch_status"], "seeded")

        by_doc = self.client.get("/api/admin/canonical-law-documents/1/versions")
        self.assertEqual(by_doc.status_code, 200)
        self.assertEqual(by_doc.json()["count"], 1)

    def test_admin_canonical_law_document_versions_missing_run(self):
        response = self.client.post("/api/admin/law-source-discovery-runs/999/ingest-document-versions", json={"safe_rerun": True})
        self.assertEqual(response.status_code, 404)
        self.assertIn("source_discovery_run_not_found", " ".join(response.json().get("detail") or []))
