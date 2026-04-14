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
from ogp_web.dependencies import get_content_workflow_service, get_runtime_servers_store
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


class _FakeRuntimeServersStore:
    def __init__(self):
        self.rows = {
            "blackberry": {
                "code": "blackberry",
                "title": "BlackBerry",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        }

    class _Record:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    @staticmethod
    def to_payload(record):
        return dict(record.__dict__)

    def list_servers(self):
        return [self._Record(**value) for _, value in sorted(self.rows.items())]

    def create_server(self, *, code: str, title: str):
        if code in self.rows:
            raise ValueError("server_code_already_exists")
        row = {"code": code, "title": title, "is_active": True, "created_at": "2026-04-14T00:00:00+00:00"}
        self.rows[code] = row
        return self._Record(**row)

    def update_server(self, *, code: str, title: str):
        if code not in self.rows:
            raise KeyError("server_not_found")
        self.rows[code]["title"] = title
        return self._Record(**self.rows[code])

    def set_active(self, *, code: str, is_active: bool):
        if code not in self.rows:
            raise KeyError("server_not_found")
        self.rows[code]["is_active"] = bool(is_active)
        return self._Record(**self.rows[code])




class _FakeContentWorkflowService:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def list_audit_trail(self, *, server_scope: str, server_id: str | None, entity_type: str = "", entity_id: str = "", limit: int = 100):
        self.calls.append(
            {
                "server_scope": server_scope,
                "server_id": server_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "limit": limit,
            }
        )
        return [
            {
                "id": 1,
                "entity_type": entity_type or "law",
                "entity_id": entity_id or "42",
                "action": "update",
            }
        ]




class _FakeContentWorkflowServiceError:
    def __init__(self, error: Exception):
        self.error = error

    def list_audit_trail(self, **kwargs):
        raise self.error

class AdminRuntimeServersApiTests(unittest.TestCase):
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
        self.runtime_store = _FakeRuntimeServersStore()
        app.dependency_overrides[get_runtime_servers_store] = lambda: self.runtime_store
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

    def test_runtime_servers_crud_endpoints(self):
        listed = self.client.get("/api/admin/runtime-servers")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)

        created = self.client.post("/api/admin/runtime-servers", json={"code": "city2", "title": "City 2"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["item"]["code"], "city2")

        updated = self.client.put("/api/admin/runtime-servers/city2", json={"code": "city2", "title": "City 2 RU"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["item"]["title"], "City 2 RU")

        deactivated = self.client.post("/api/admin/runtime-servers/city2/deactivate")
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()["item"]["is_active"])

        activated = self.client.post("/api/admin/runtime-servers/city2/activate")
        self.assertEqual(activated.status_code, 200)
        self.assertTrue(activated.json()["item"]["is_active"])

    def test_runtime_server_update_rejects_code_mismatch(self):
        response = self.client.put("/api/admin/runtime-servers/city2", json={"code": "city3", "title": "Wrong"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("server_code_mismatch", response.json().get("detail", []))

    def test_catalog_audit_accepts_entity_filters(self):
        fake_workflow = _FakeContentWorkflowService()
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/catalog/audit", params={"entity_type": " LAW ", "entity_id": " 42 ", "limit": 5})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filters"], {"entity_type": "law", "entity_id": "42", "limit": 5})
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(fake_workflow.calls[-1]["entity_type"], "law")
        self.assertEqual(fake_workflow.calls[-1]["entity_id"], "42")
        self.assertEqual(fake_workflow.calls[-1]["limit"], 5)

    def test_catalog_audit_returns_default_filters_when_not_passed(self):
        fake_workflow = _FakeContentWorkflowService()
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/catalog/audit")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filters"], {"entity_type": "", "entity_id": "", "limit": 100})
        self.assertEqual(fake_workflow.calls[-1]["entity_type"], "")
        self.assertEqual(fake_workflow.calls[-1]["entity_id"], "")
        self.assertEqual(fake_workflow.calls[-1]["limit"], 100)

    def test_platform_blueprint_status_returns_default_stage(self):
        previous = os.environ.get("OGP_ADMIN_PLATFORM_STAGE")
        os.environ.pop("OGP_ADMIN_PLATFORM_STAGE", None)
        try:
            response = self.client.get("/api/admin/platform-blueprint/status")
        finally:
            if previous is None:
                os.environ.pop("OGP_ADMIN_PLATFORM_STAGE", None)
            else:
                os.environ["OGP_ADMIN_PLATFORM_STAGE"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload["stage"]["stage_code"], "phase_a_foundation")
        self.assertIn("Phase A", payload["stage"]["stage_label"])

    def test_platform_blueprint_status_accepts_known_stage_from_env(self):
        previous = os.environ.get("OGP_ADMIN_PLATFORM_STAGE")
        os.environ["OGP_ADMIN_PLATFORM_STAGE"] = "phase_c_quality_center"
        try:
            response = self.client.get("/api/admin/platform-blueprint/status")
        finally:
            if previous is None:
                os.environ.pop("OGP_ADMIN_PLATFORM_STAGE", None)
            else:
                os.environ["OGP_ADMIN_PLATFORM_STAGE"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stage"]["stage_code"], "phase_c_quality_center")
        self.assertIn("Phase C", payload["stage"]["stage_label"])

    def test_platform_blueprint_status_falls_back_for_unknown_stage(self):
        previous = os.environ.get("OGP_ADMIN_PLATFORM_STAGE")
        os.environ["OGP_ADMIN_PLATFORM_STAGE"] = "phase_z_unknown"
        try:
            response = self.client.get("/api/admin/platform-blueprint/status")
        finally:
            if previous is None:
                os.environ.pop("OGP_ADMIN_PLATFORM_STAGE", None)
            else:
                os.environ["OGP_ADMIN_PLATFORM_STAGE"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stage"]["stage_code"], "phase_a_foundation")
        self.assertIn("Phase A", payload["stage"]["stage_label"])

    def test_catalog_audit_maps_value_error_to_400_with_error_code_header(self):
        fake_workflow = _FakeContentWorkflowServiceError(ValueError("bad_filter"))
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/catalog/audit", params={"entity_type": "laws"})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("bad_filter", payload.get("detail", []))
        self.assertEqual(payload.get("error", {}).get("code"), "admin_catalog_audit_bad_request")
        self.assertEqual(payload.get("error", {}).get("source"), "admin_catalog_audit")
        self.assertEqual(response.headers.get("x-error-code"), "admin_catalog_audit_bad_request")

    def test_catalog_audit_maps_permission_error_to_404_with_error_code_header(self):
        fake_workflow = _FakeContentWorkflowServiceError(PermissionError("forbidden_scope"))
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/catalog/audit", params={"entity_type": "laws"})

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertIn("forbidden_scope", payload.get("detail", []))
        self.assertEqual(payload.get("error", {}).get("code"), "admin_catalog_audit_not_found")
        self.assertEqual(payload.get("error", {}).get("source"), "admin_catalog_audit")
        self.assertEqual(response.headers.get("x-error-code"), "admin_catalog_audit_not_found")

