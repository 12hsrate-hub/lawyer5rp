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
from ogp_web.dependencies import get_canonical_law_documents_store, get_law_source_discovery_store
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
                first_seen_at="2026-04-16T00:10:00+00:00",
                last_seen_at="2026-04-16T00:10:00+00:00",
                created_at="2026-04-16T00:10:00+00:00",
                updated_at="2026-04-16T00:10:00+00:00",
            )
        ]


class _FakeDocumentsStore:
    class _Resolved:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Document:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def __init__(self):
        self.documents = {}
        self.aliases = {}
        self.next_document_id = 1
        self.next_alias_id = 1

    def resolve_document_by_alias(self, *, normalized_url: str):
        resolved = self.aliases.get(normalized_url)
        return self._Resolved(**resolved) if resolved else None

    def create_document(self, *, canonical_identity_key: str, identity_source: str = "url_seed", display_title: str = "", metadata_json=None):
        document = {
            "id": self.next_document_id,
            "canonical_identity_key": canonical_identity_key,
            "identity_source": identity_source,
            "display_title": display_title,
            "metadata_json": dict(metadata_json or {}),
        }
        self.documents[self.next_document_id] = document
        self.next_document_id += 1
        return self._Document(**document)

    def create_alias(self, *, canonical_law_document_id: int, normalized_url: str, alias_kind: str = "canonical", metadata_json=None, **kwargs):
        document = self.documents[int(canonical_law_document_id)]
        alias = {
            "document_id": document["id"],
            "canonical_identity_key": document["canonical_identity_key"],
            "identity_source": document["identity_source"],
            "display_title": document["display_title"],
            "document_metadata_json": dict(document["metadata_json"]),
            "alias_id": self.next_alias_id,
            "normalized_url": normalized_url,
            "alias_kind": alias_kind,
            "is_active": True,
            "alias_metadata_json": dict(metadata_json or {}),
        }
        self.aliases[normalized_url] = alias
        self.next_alias_id += 1
        return self._Resolved(**alias)


class AdminCanonicalLawDocumentsApiTests(unittest.TestCase):
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
        app.dependency_overrides[get_law_source_discovery_store] = lambda: self.discovery_store
        app.dependency_overrides[get_canonical_law_documents_store] = lambda: self.documents_store
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

    def test_admin_canonical_law_document_ingest_and_read_endpoints(self):
        ingest = self.client.post("/api/admin/law-source-discovery-runs/5/ingest-documents", json={"safe_rerun": True})
        self.assertEqual(ingest.status_code, 200)
        self.assertTrue(ingest.json()["changed"])
        self.assertEqual(ingest.json()["created_documents"], 1)

        listed = self.client.get("/api/admin/law-source-discovery-runs/5/documents")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)
        self.assertEqual(listed.json()["items"][0]["identity_source"], "url_seed")

    def test_admin_canonical_law_document_ingest_missing_run(self):
        response = self.client.post("/api/admin/law-source-discovery-runs/999/ingest-documents", json={"safe_rerun": True})
        self.assertEqual(response.status_code, 404)
        self.assertIn("source_discovery_run_not_found", " ".join(response.json().get("detail") or []))
