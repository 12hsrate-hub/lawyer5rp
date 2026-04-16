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


class WebPagesSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = make_temporary_directory()
        root = Path(self.tmpdir.name)
        self.prev_test_users = os.environ.get("OGP_WEB_TEST_USERS")
        os.environ["OGP_WEB_TEST_USERS"] = "tester"
        self.store = UserStore(
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
        self.client = TestClient(
            create_app(self.store, self.exam_store, self.admin_store, self.task_registry),
            base_url="https://testserver",
        )
        reset_rate_limit(self.client.app.state.rate_limiter)

        response = self.client.post(
            "/api/auth/register",
            json={"username": "tester", "email": "tester@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "tester", "password": "Password123!"})

    def tearDown(self):
        reset_rate_limit(self.client.app.state.rate_limiter)
        self.client.close()
        self.client.app.state.rate_limiter.repository.close()
        self.client.app.state.user_store.repository.close()
        self.store.repository.close()
        if self.prev_test_users is None:
            os.environ.pop("OGP_WEB_TEST_USERS", None)
        else:
            os.environ["OGP_WEB_TEST_USERS"] = self.prev_test_users
        self.tmpdir.cleanup()

    def test_complaint_page_smoke(self):
        response = self.client.get("/complaint")
        self.assertEqual(response.status_code, 200)
        self.assertIn("charset=utf-8", response.headers.get("content-type", "").lower())
        self.assertIn("complaint-form", response.text)
        self.assertIn('accept-charset="UTF-8"', response.text)
        self.assertIn("result", response.text)
        self.assertIn("ai-focus-hint", response.text)
        self.assertIn("complaint-basis", response.text)
        self.assertIn("save-draft-btn", response.text)
        self.assertIn("generate-bbcode-btn", response.text)
        self.assertIn("bbcode-status-text", response.text)
        self.assertIn("Статус: готово к формированию BBCode.", response.text)
        self.assertIn("pages/complaint.js?v=", response.text)
        self.assertIn("shared/common.js?v=", response.text)
        self.assertIn('data-username="tester"', response.text)

    def test_rehab_page_smoke(self):
        response = self.client.get("/rehab")
        self.assertEqual(response.status_code, 200)
        self.assertIn("charset=utf-8", response.headers.get("content-type", "").lower())
        self.assertIn("rehab-form", response.text)
        self.assertIn("principal_name", response.text)

    def test_profile_page_smoke(self):
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        self.assertIn("profile-form", response.text)
        self.assertIn("passport_scan_url", response.text)

    def test_exam_import_page_smoke(self):
        response = self.client.get("/exam-import-test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("exam-import", response.text)

    def test_court_claim_test_page_preserves_in_development_marker(self):
        response = self.client.get("/court-claim-test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Тестовый раздел", response.text)
        self.assertIn("Форма находится в разработке", response.text)
        self.assertIn("court-claim-in-development", response.text)

    def test_login_redirects_authenticated_user(self):
        response = self.client.get("/login", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/complaint")

    def test_verify_email_page_renders_server_context(self):
        response = self.client.get("/verify-email")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Подтверждение email", response.text)
        self.assertIn("OGP Builder", response.text)

    def test_verify_email_page_uses_app_default_server_context_when_non_default(self):
        self.client.app.state.server_config = type("Cfg", (), {"code": "orange"})()

        with patch(
            "ogp_web.routes.pages.resolve_server_config",
            return_value=type("ServerCfg", (), {"code": "orange", "name": "Orange County", "app_title": "Orange Builder"})(),
        ) as resolve_server_config_mock, patch(
            "ogp_web.routes.pages.extract_server_shell_context",
            return_value={"server_code": "orange", "server_name": "Orange County", "app_title": "Orange Builder"},
        ):
            response = self.client.get("/verify-email")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Orange Builder", response.text)
        resolve_server_config_mock.assert_called_once_with(server_code="orange")

    def test_reset_password_page_renders_server_context(self):
        response = self.client.get("/reset-password?token=test-token")
        self.assertEqual(response.status_code, 200)
        self.assertIn("test-token", response.text)
        self.assertIn("OGP Builder", response.text)

    def test_admin_page_requires_admin_user(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 403)

    def test_admin_root_redirects_admin_to_servers_workspace(self):
        self.client.post("/api/auth/logout")
        response = self.client.post(
            "/api/auth/register",
            json={"username": "12345", "email": "admin@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})

        response = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/admin/servers")

    def test_admin_dashboard_uses_segmented_item_tabs(self):
        self.client.post("/api/auth/logout")
        response = self.client.post(
            "/api/auth/register",
            json={"username": "12345", "email": "admin@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})

        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="segmented-tabs__item is-active"', response.text)
        self.assertIn("Сводка · Ops", response.text)
        self.assertIn("Global ops workspace", response.text)
        self.assertIn("Global ops", response.text)
        self.assertIn("Открыть server workspace", response.text)
        self.assertIn('href="/admin/users"', response.text)
        self.assertIn("Async Jobs", response.text)
        self.assertIn("Law rebuild tasks", response.text)
        self.assertIn('id="admin-law-jobs"', response.text)
        self.assertIn("Exam import", response.text)
        self.assertIn('id="admin-exam-import-ops"', response.text)
        self.assertIn("Pilot rollout", response.text)
        self.assertIn('id="admin-pilot-rollout"', response.text)
        self.assertIn("Current rollout state, feature-flag modes, fallback signals, and rollback readiness for the pilot scenario.", response.text)
        self.assertIn("Document provenance trace", response.text)
        self.assertIn('id="admin-provenance-form"', response.text)
        self.assertIn('id="admin-provenance-version-id"', response.text)
        self.assertIn('id="admin-provenance-document-id"', response.text)
        self.assertIn('id="admin-provenance-trace"', response.text)
        self.assertIn("Recent generated documents", response.text)
        self.assertIn('id="admin-generated-documents-review"', response.text)
        self.assertIn("Generated document review", response.text)
        self.assertIn('id="admin-generated-document-context"', response.text)

    def test_admin_laws_page_contains_guided_server_setup_block(self):
        self.client.post("/api/auth/logout")
        response = self.client.post(
            "/api/auth/register",
            json={"username": "12345", "email": "admin@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})

        response = self.client.get("/admin/laws")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-catalog-entity="laws"', response.text)
        self.assertIn('/static/shared/admin_common.js', response.text)
        self.assertIn('/static/shared/admin_overview_loader.js', response.text)
        self.assertIn('/static/shared/admin_actions.js', response.text)
        self.assertIn('/static/shared/admin_law_runtime_controller.js', response.text)
        self.assertIn('/static/pages/admin.js', response.text)
        self.assertIn('href="#law-source-sets-host"', response.text)
        self.assertIn('href="#law-source-set-revisions-host"', response.text)
        self.assertIn('href="#server-source-set-bindings-host"', response.text)
        self.assertIn('href="#law-legacy-runtime-panel"', response.text)
        self.assertIn("Advanced law diagnostics", response.text)
        self.assertIn("Низкоуровневый law-domain экран", response.text)
        self.assertIn("Legacy / Runtime", response.text)
        self.assertIn("Source Sets", response.text)
        self.assertIn("Server Bindings", response.text)
        self.assertIn("Advanced / Compatibility", response.text)
        self.assertIn("Advanced diagnostics only", response.text)
        self.assertIn("Вернуться в server workspace", response.text)
        self.assertIn("Основной рабочий путь теперь начинается с", response.text)
        self.assertIn("Открыть server workspace", response.text)
        self.assertIn("Compatibility snapshot", response.text)
        self.assertIn("Advanced catalog / compatibility", response.text)
        self.assertNotIn("Законы · Диагностика", response.text)
        self.assertNotIn('href="#admin-law-domain-map"', response.text)
        self.assertNotIn('href="#law-main-check-host"', response.text)
        self.assertNotIn('href="#admin-domain-summary"', response.text)
        self.assertNotIn('href="#admin-catalog-content"', response.text)
        self.assertNotIn('href="#law-canonical-pipeline-host"', response.text)
        self.assertIn('id="admin-law-modal"', response.text)
        self.assertIn('id="admin-law-modal-body"', response.text)
        self.assertIn('id="admin-law-modal-save"', response.text)
        self.assertNotIn('href="/admin/templates"', response.text)
        self.assertNotIn('href="/admin/features"', response.text)
        self.assertNotIn('href="/admin/rules"', response.text)

    def test_law_qa_test_page_renders_sources_panel(self):
        response = self.client.get("/law-qa-test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Q&A по законодательной базе", response.text)
        self.assertIn("Законы, которые используются в поиске", response.text)

    def test_admin_servers_page_contains_phase_c_read_only_domain_summary(self):
        self.client.post("/api/auth/logout")
        response = self.client.post(
            "/api/auth/register",
            json={"username": "12345", "email": "admin@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})

        response = self.client.get("/admin/servers")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="#admin-domain-summary"', response.text)
        self.assertIn("Read-only domain slice", response.text)
        self.assertIn("Configuration Catalog", response.text)
        self.assertIn("Runtime and configuration workspace", response.text)
        self.assertIn("Runtime inventory, active server state, and linked configuration bundles.", response.text)
        self.assertIn("Серверы · Основное", response.text)
        self.assertIn('href="#admin-server-domain-map"', response.text)
        self.assertIn("Server Domain Map", response.text)
        self.assertIn("Activation State", response.text)
        self.assertIn("Linked Configuration", response.text)

    def test_admin_server_detail_page_contains_server_workspace_tabs(self):
        self.client.post("/api/auth/logout")
        response = self.client.post(
            "/api/auth/register",
            json={"username": "12345", "email": "admin@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})

        response = self.client.get("/admin/servers/blackberry")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="admin-server-workspace"', response.text)
        self.assertIn('data-server-code="blackberry"', response.text)
        self.assertIn("Server workspace: blackberry", response.text)
        self.assertIn("официальный основной путь", response.text)
        self.assertIn("Серверы · Основное", response.text)
        self.assertIn('data-server-workspace-tab="overview"', response.text)
        self.assertIn('data-server-workspace-tab="laws"', response.text)
        self.assertIn('data-server-workspace-tab="features"', response.text)
        self.assertIn('data-server-workspace-tab="templates"', response.text)
        self.assertIn('data-server-workspace-tab="users"', response.text)
        self.assertIn('data-server-workspace-tab="access"', response.text)
        self.assertIn('data-server-workspace-tab="audit"', response.text)
        self.assertIn('data-server-workspace-tab="errors"', response.text)
        self.assertIn('data-server-workspace-tab="diagnostics"', response.text)
        self.assertIn("Сводка · Ops", response.text)
        self.assertIn("Пользователи и аудит · Global", response.text)
        self.assertIn("Серверы · Основное", response.text)
        self.assertNotIn("Законы · Диагностика", response.text)

    def test_admin_templates_page_redirects_to_servers(self):
        self.client.post("/api/auth/logout")
        response = self.client.post(
            "/api/auth/register",
            json={"username": "12345", "email": "admin@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})

        response = self.client.get("/admin/templates", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/admin/servers")

    def test_admin_features_page_redirects_to_servers(self):
        self.client.post("/api/auth/logout")
        response = self.client.post(
            "/api/auth/register",
            json={"username": "12345", "email": "admin@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})

        response = self.client.get("/admin/features", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/admin/servers")

    def test_admin_rules_page_redirects_to_servers(self):
        self.client.post("/api/auth/logout")
        response = self.client.post(
            "/api/auth/register",
            json={"username": "12345", "email": "admin@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})

        response = self.client.get("/admin/rules", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/admin/servers")

    def test_granted_tester_redirected_from_test_pages(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "plainuser", "email": "plainuser@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "plainuser", "password": "Password123!"})
        self.client.post("/api/auth/logout")

        response = self.client.post(
            "/api/auth/register",
            json={"username": "12345", "email": "admin@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})
        self.client.post("/api/admin/users/plainuser/grant-tester")
        self.client.post("/api/auth/logout")

        self.client.post("/api/auth/login", json={"username": "plainuser", "password": "Password123!"})
        response = self.client.get("/complaint-test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("complaint-form", response.text)
        self.assertNotIn("complaint-preset", response.text)


if __name__ == "__main__":
    unittest.main()
