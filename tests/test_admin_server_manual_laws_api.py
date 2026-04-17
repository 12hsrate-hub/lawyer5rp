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
    get_law_source_sets_store,
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


class _FakeLawSourceSetsStore:
    class _Binding:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Revision:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def list_bindings(self, *, server_code: str):
        if str(server_code or "").strip().lower() != "blackberry":
            return []
        return [
            self._Binding(
                id=11,
                server_code="blackberry",
                source_set_key="legacy-blackberry-default",
                priority=100,
                is_active=True,
                include_law_keys=[],
                exclude_law_keys=[],
                pin_policy_json={},
                metadata_json={},
                created_at="2026-04-17T07:00:00+00:00",
                updated_at="2026-04-17T07:00:00+00:00",
            )
        ]

    def list_revisions(self, *, source_set_key: str):
        if str(source_set_key or "").strip().lower() != "legacy-blackberry-default":
            return []
        return [
            self._Revision(
                id=7,
                source_set_key="legacy-blackberry-default",
                revision=3,
                status="published",
                container_urls=("https://example.com/topic",),
                adapter_policy_json={},
                metadata_json={},
            )
        ]


class _FakeDiscoveryStore:
    class _Run:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Link:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def __init__(self):
        self.next_run_id = 31
        self.next_link_id = 41

    def create_run(self, *, source_set_revision_id: int, trigger_mode: str = "manual", status: str = "succeeded", summary_json=None, error_summary: str = ""):
        run = self._Run(
            id=self.next_run_id,
            source_set_revision_id=int(source_set_revision_id),
            source_set_key="legacy-blackberry-default",
            revision=3,
            trigger_mode=trigger_mode,
            status=status,
            summary_json=dict(summary_json or {}),
            error_summary=error_summary,
        )
        self.next_run_id += 1
        return run

    def create_link(self, *, source_discovery_run_id: int, source_set_revision_id: int, normalized_url: str, source_container_url: str = "", discovery_status: str = "discovered", alias_hints_json=None, metadata_json=None):
        link = self._Link(
            id=self.next_link_id,
            source_discovery_run_id=int(source_discovery_run_id),
            source_set_revision_id=int(source_set_revision_id),
            normalized_url=normalized_url,
            source_container_url=source_container_url,
            discovery_status=discovery_status,
            alias_hints_json=dict(alias_hints_json or {}),
            metadata_json=dict(metadata_json or {}),
        )
        self.next_link_id += 1
        return link


class _FakeCanonicalLawDocumentsStore:
    class _Document:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Resolved:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def __init__(self):
        self.next_document_id = 1
        self.next_alias_id = 1
        self.documents_by_key = {}
        self.aliases_by_url = {}

    def get_document(self, *, canonical_identity_key: str):
        return self.documents_by_key.get(str(canonical_identity_key or "").strip().lower())

    def resolve_document_by_alias(self, *, normalized_url: str):
        item = self.aliases_by_url.get(str(normalized_url or "").strip())
        return self._Resolved(**item) if item else None

    def create_document(self, *, canonical_identity_key: str, identity_source: str = "manual_remap", display_title: str = "", metadata_json=None):
        document = self._Document(
            id=self.next_document_id,
            canonical_identity_key=str(canonical_identity_key or "").strip().lower(),
            identity_source=identity_source,
            display_title=display_title,
            metadata_json=dict(metadata_json or {}),
        )
        self.documents_by_key[document.canonical_identity_key] = document
        self.next_document_id += 1
        return document

    def create_alias(self, *, canonical_law_document_id: int, normalized_url: str, alias_kind: str = "manual_remap", metadata_json=None, **kwargs):
        document = next(item for item in self.documents_by_key.values() if int(item.id) == int(canonical_law_document_id))
        alias = {
            "document_id": int(document.id),
            "canonical_identity_key": str(document.canonical_identity_key),
            "identity_source": str(document.identity_source),
            "display_title": str(document.display_title),
            "document_metadata_json": dict(document.metadata_json),
            "alias_id": self.next_alias_id,
            "normalized_url": str(normalized_url),
            "alias_kind": alias_kind,
            "is_active": True,
            "alias_metadata_json": dict(metadata_json or {}),
        }
        self.aliases_by_url[str(normalized_url)] = alias
        self.next_alias_id += 1
        return self._Resolved(**alias)


class _FakeCanonicalLawDocumentVersionsStore:
    class _Version:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def __init__(self):
        self.next_version_id = 101
        self.items = []

    def create_version(self, **kwargs):
        version = self._Version(
            id=self.next_version_id,
            canonical_identity_key=kwargs.get("metadata_json", {}).get("canonical_identity_key", "") or "",
            display_title=kwargs.get("parsed_title") or kwargs.get("raw_title") or "",
            source_set_key="legacy-blackberry-default",
            source_set_revision_id=7,
            revision=3,
            normalized_url="",
            source_container_url="",
            created_at="2026-04-17T08:00:00+00:00",
            updated_at="2026-04-17T08:00:00+00:00",
            **kwargs,
        )
        version.canonical_identity_key = str(kwargs.get("metadata_json", {}).get("canonical_identity_key") or version.canonical_identity_key or "").strip().lower()
        version.source_set_key = "legacy-blackberry-default"
        version.source_set_revision_id = 7
        version.revision = 3
        version.normalized_url = str(kwargs.get("metadata_json", {}).get("normalized_url") or "")
        version.source_container_url = version.normalized_url
        self.items.append(version)
        self.next_version_id += 1
        return version

    def list_parsed_versions_for_source_sets(self, *, source_set_keys):
        normalized = {str(item or "").strip().lower() for item in source_set_keys}
        return [
            item for item in self.items
            if str(getattr(item, "source_set_key", "") or "").strip().lower() in normalized
            and str(getattr(item, "parse_status", "") or "").strip().lower() == "parsed"
        ]


class AdminServerManualLawsApiTests(unittest.TestCase):
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
        self.source_sets_store = _FakeLawSourceSetsStore()
        self.discovery_store = _FakeDiscoveryStore()
        self.documents_store = _FakeCanonicalLawDocumentsStore()
        self.versions_store = _FakeCanonicalLawDocumentVersionsStore()
        app.dependency_overrides[get_law_source_sets_store] = lambda: self.source_sets_store
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

    def test_admin_runtime_server_manual_law_entry_and_editor_endpoints(self):
        created = self.client.post(
            "/api/admin/runtime-servers/blackberry/laws/manual-entry",
            json={
                "source_set_key": "legacy-blackberry-default",
                "canonical_identity_key": "manual:test-law",
                "normalized_url": "https://example.com/manual/test-law",
                "title": "Тестовый закон",
                "body_text": "Статья 1. Тестовое содержание.",
            },
        )
        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.json()["ok"])
        self.assertEqual(created.json()["item"]["canonical_identity_key"], "manual:test-law")
        self.assertEqual(created.json()["source_set_key"], "legacy-blackberry-default")

        editor = self.client.get(
            "/api/admin/runtime-servers/blackberry/laws/manual-editor",
            params={"source_set_key": "legacy-blackberry-default", "canonical_identity_key": "manual:test-law"},
        )
        self.assertEqual(editor.status_code, 200)
        self.assertEqual(editor.json()["canonical_identity_key"], "manual:test-law")
        self.assertEqual(editor.json()["title"], "Тестовый закон")
        self.assertEqual(editor.json()["body_text"], "Статья 1. Тестовое содержание.")

    def test_admin_runtime_server_manual_law_entry_requires_bound_source_set(self):
        response = self.client.post(
            "/api/admin/runtime-servers/blackberry/laws/manual-entry",
            json={
                "source_set_key": "missing-set",
                "canonical_identity_key": "manual:test-law",
                "normalized_url": "",
                "title": "Тестовый закон",
                "body_text": "Текст",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("server_source_set_binding_not_found", " ".join(response.json().get("detail") or []))
