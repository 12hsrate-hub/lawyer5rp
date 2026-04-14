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
from ogp_web.dependencies import get_content_workflow_service, get_runtime_law_sets_store, get_runtime_servers_store
import ogp_web.routes.admin as admin_route
from ogp_web.rate_limit import reset_for_testing as reset_rate_limit
from ogp_web.services.law_version_service import ResolvedLawVersion
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

    def get_server(self, *, code: str):
        row = self.rows.get(code)
        return self._Record(**row) if row else None

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


class _FakeRuntimeLawSetsStore:
    def __init__(self):
        self.law_sets = {
            1: {
                "id": 1,
                "server_code": "blackberry",
                "name": "Default",
                "is_active": True,
                "is_published": True,
                "item_count": 1,
            }
        }
        self.bindings = {
            "blackberry": [
                {
                    "law_set_id": 1,
                    "item_id": 1,
                    "law_code": "uk",
                    "priority": 100,
                    "effective_from": "",
                }
            ]
        }

    def list_law_sets(self, *, server_code: str):
        return [row for row in self.law_sets.values() if row["server_code"] == server_code]

    def create_law_set(self, *, server_code: str, name: str):
        next_id = max(self.law_sets.keys(), default=0) + 1
        row = {"id": next_id, "server_code": server_code, "name": name, "is_active": True, "is_published": False}
        self.law_sets[next_id] = {**row, "item_count": 0}
        return row

    def replace_law_set_items(self, *, law_set_id: int, items):
        self.law_sets[law_set_id]["item_count"] = len(items)
        return list(items)

    def list_server_law_bindings(self, *, server_code: str):
        return list(self.bindings.get(server_code, []))

    def add_server_law_binding(self, *, server_code: str, law_code: str, source_id: int, effective_from: str = "", priority: int = 100, law_set_id=None):
        item = {
            "law_set_id": int(law_set_id or 1),
            "item_id": len(self.bindings.get(server_code, [])) + 1,
            "law_code": law_code,
            "priority": priority,
            "effective_from": effective_from,
            "source_id": source_id,
        }
        self.bindings.setdefault(server_code, []).append(item)
        return item

    def publish_law_set(self, *, law_set_id: int):
        row = self.law_sets[law_set_id]
        for item in self.law_sets.values():
            if item["server_code"] == row["server_code"]:
                item["is_published"] = False
        row["is_published"] = True
        row["is_active"] = True
        return {k: row[k] for k in ("id", "server_code", "name", "is_active", "is_published")}


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
        self.runtime_law_sets_store = _FakeRuntimeLawSetsStore()
        app.dependency_overrides[get_runtime_servers_store] = lambda: self.runtime_store
        app.dependency_overrides[get_runtime_law_sets_store] = lambda: self.runtime_law_sets_store
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

    def test_runtime_server_health_and_setup_flow(self):
        created = self.client.post("/api/admin/runtime-servers", json={"code": "city2", "title": "City 2"})
        self.assertEqual(created.status_code, 200)

        created_law_set = self.client.post(
            "/api/admin/runtime-servers/city2/law-sets",
            json={"name": "City 2 Draft", "is_active": True, "items": [{"law_code": "city2_law", "priority": 10}]},
        )
        self.assertEqual(created_law_set.status_code, 200)
        law_set_id = created_law_set.json()["law_set"]["id"]

        published = self.client.post(f"/api/admin/law-sets/{law_set_id}/publish")
        self.assertEqual(published.status_code, 200)

        binding = self.client.post(
            "/api/admin/runtime-servers/city2/law-bindings",
            json={"law_code": "city2_law", "source_id": 1, "priority": 25, "law_set_id": law_set_id},
        )
        self.assertEqual(binding.status_code, 200)

        deactivated = self.client.post("/api/admin/runtime-servers/city2/deactivate")
        self.assertEqual(deactivated.status_code, 200)

        with patch.object(
            admin_route,
            "resolve_active_law_version",
            return_value=ResolvedLawVersion(
                id=77,
                server_code="city2",
                generated_at_utc="2026-04-14T00:00:00+00:00",
                effective_from="2026-04-14",
                effective_to="",
                fingerprint="test-fingerprint",
                chunk_count=12,
            ),
        ):
            health_before = self.client.get("/api/admin/runtime-servers/city2/health")
            self.assertEqual(health_before.status_code, 200)
            payload_before = health_before.json()
            self.assertEqual(payload_before["summary"]["ready_count"], 4)
            self.assertFalse(payload_before["checks"]["activation"]["ok"])
            self.assertTrue(payload_before["checks"]["health"]["ok"])

            activated = self.client.post("/api/admin/runtime-servers/city2/activate")
            self.assertEqual(activated.status_code, 200)

            health_after = self.client.get("/api/admin/runtime-servers/city2/health")
            self.assertEqual(health_after.status_code, 200)
            payload_after = health_after.json()
            self.assertTrue(payload_after["summary"]["is_ready"])
            self.assertEqual(payload_after["summary"]["ready_count"], payload_after["summary"]["total_count"])
            self.assertEqual(payload_after["checks"]["health"]["active_law_version_id"], 77)

    def test_catalog_audit_accepts_entity_filters(self):
        fake_workflow = _FakeContentWorkflowService()
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/catalog/audit", params={"entity_type": " LaW ", "entity_id": " 42 ", "limit": 5})

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
