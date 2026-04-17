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
from tests.second_server_fixtures import blackberry_published_pack, orange_published_pack
from tests.temp_helpers import make_temporary_directory
from tests.test_web_storage import (
    FakeAdminMetricsPostgresBackend,
    FakeExamAnswersPostgresBackend,
    FakeExamImportTasksPostgresBackend,
    PostgresBackend,
)


class RuntimeContextApiTests(unittest.TestCase):
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

    def _register_verify_and_login(self, username: str, email: str, password: str = "Password123!") -> None:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "email": email, "password": password},
        )
        self.assertEqual(response.status_code, 200)
        split = urlsplit(response.json()["verification_url"])
        self.client.get(f"{split.path}?{split.query}")
        login_response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(login_response.status_code, 200)

    def _complaint_payload(self) -> dict[str, object]:
        return {
            "appeal_no": "1234",
            "org": "LSPD",
            "subject_names": "John Doe",
            "situation_description": "Описание",
            "violation_short": "Нарушение",
            "event_dt": "08.04.2026 14:30",
            "today_date": "08.04.2026",
            "victim": {
                "name": "Victim",
                "passport": "BB",
                "address": "Addr",
                "phone": "7654321",
                "discord": "victim",
                "passport_scan_url": "https://example.com/victim",
            },
            "contract_url": "https://example.com/contract",
            "bar_request_url": "",
            "official_answer_url": "",
            "mail_notice_url": "",
            "arrest_record_url": "",
            "personnel_file_url": "",
            "video_fix_urls": [],
            "provided_video_urls": [],
        }

    def test_runtime_context_endpoint_returns_selected_server_capability_payload(self):
        self._register_verify_and_login("tester", "tester@example.com")

        response = self.client.get("/api/runtime/sections/complaint/capability-context")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["section_code"], "complaint")
        self.assertEqual(payload["capability_code"], "complaint.compose")
        self.assertEqual(payload["selected_server_code"], "blackberry")
        self.assertEqual(payload["current_truth"], "hybrid")
        self.assertEqual(payload["target_truth"], "published_pack")
        self.assertEqual(payload["access_verdict"]["status"], "allowed")
        self.assertEqual(payload["runtime_requirement"]["status"], "ready")
        self.assertIn("/api/generate", payload["read_inventory"]["route_entries"])
        self.assertIsInstance(payload["artifact_resolution"], dict)
        self.assertEqual(payload["artifact_resolution"]["section_code"], "complaint")
        self.assertEqual(payload["artifact_resolution"]["template"]["content_key"], "complaint_v1")

    def test_runtime_context_endpoint_enforces_section_permission(self):
        self._register_verify_and_login("basic_user", "basic@example.com")

        response = self.client.get("/api/runtime/sections/law_qa/capability-context")

        self.assertEqual(response.status_code, 403)
        self.assertIn("court_claims", response.json()["detail"][0])

    def test_runtime_context_endpoint_includes_law_context_readiness_for_law_qa(self):
        self._register_verify_and_login("tester", "tester-law-context@example.com")

        response = self.client.get("/api/runtime/sections/law_qa/capability-context")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsInstance(payload["law_context_readiness"], dict)
        self.assertIn("status", payload["law_context_readiness"])

    def test_server_law_context_readiness_endpoint_returns_selected_server_payload(self):
        self._register_verify_and_login("tester", "tester-law-readiness@example.com")

        response = self.client.get("/api/runtime/servers/blackberry/law-context-readiness")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["server_code"], "blackberry")
        self.assertIn("reason_code", payload)
        self.assertIn("projection", payload)
        self.assertIn("runtime_pack", payload)

    def test_selected_server_context_drives_runtime_context_and_document_builder_bundle(self):
        self._register_verify_and_login("tester", "tester-switch@example.com")

        with patch("ogp_web.server_config.registry._load_codes_from_config_repo", return_value=None), patch(
            "ogp_web.server_config.registry._load_server_rows_from_db",
            return_value=[
                {"code": "blackberry", "title": "BlackBerry", "is_active": True},
                {"code": "orange", "title": "Orange County", "is_active": True},
            ],
        ), patch(
            "ogp_web.server_config.registry._load_effective_pack_from_db",
            side_effect=lambda *, server_code, at_timestamp=None: orange_published_pack() if server_code == "orange" else None,
        ):
            switch_response = self.client.patch("/api/profile/selected-server", json={"server_code": "orange"})
            self.assertEqual(switch_response.status_code, 200)

            context_response = self.client.get("/api/runtime/sections/court_claim/capability-context")
            self.assertEqual(context_response.status_code, 200)
            context_payload = context_response.json()
            self.assertEqual(context_payload["selected_server_code"], "orange")
            self.assertEqual(context_payload["runtime_resolution"]["mode"], "published_pack")
            self.assertEqual(context_payload["runtime_requirement"]["reason_code"], "published_pack_ready")

            bundle_response = self.client.get(
                "/api/document-builder/bundle",
                params={"document_type": "court_claim"},
            )
            self.assertEqual(bundle_response.status_code, 200)
            bundle_payload = bundle_response.json()
            self.assertEqual(bundle_payload["server"], "orange")
            self.assertIn("artifact_resolution", bundle_payload["status"])

    def test_court_claim_strict_cutover_env_blocks_bootstrap_server_paths(self):
        self._register_verify_and_login("tester", "tester-court-claim-strict-bootstrap@example.com")

        with patch.dict(os.environ, {"OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS": "court_claim"}, clear=False):
            context_response = self.client.get("/api/runtime/sections/court_claim/capability-context")
            self.assertEqual(context_response.status_code, 200)
            context_payload = context_response.json()
            self.assertEqual(context_payload["selected_server_code"], "blackberry")
            self.assertEqual(context_payload["runtime_requirement"]["status"], "blocked")
            self.assertTrue(context_payload["runtime_requirement"]["strict_cutover_enabled"])
            self.assertEqual(context_payload["runtime_requirement"]["reason_code"], "published_pack_cutover_required")

            bundle_response = self.client.get(
                "/api/document-builder/bundle",
                params={"document_type": "court_claim"},
            )
            self.assertEqual(bundle_response.status_code, 409)

            page_response = self.client.get("/court-claim-test")
            self.assertEqual(page_response.status_code, 409)

    def test_court_claim_strict_cutover_env_preserves_published_pack_paths(self):
        self._register_verify_and_login("tester", "tester-court-claim-strict-published@example.com")

        with patch.dict(os.environ, {"OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS": "court_claim"}, clear=False), patch(
            "ogp_web.server_config.registry._load_codes_from_config_repo",
            return_value=None,
        ), patch(
            "ogp_web.server_config.registry._load_server_rows_from_db",
            return_value=[
                {"code": "blackberry", "title": "BlackBerry", "is_active": True},
                {"code": "orange", "title": "Orange County", "is_active": True},
            ],
        ), patch(
            "ogp_web.server_config.registry._load_effective_pack_from_db",
            side_effect=lambda *, server_code, at_timestamp=None: orange_published_pack() if server_code == "orange" else None,
        ):
            switch_response = self.client.patch("/api/profile/selected-server", json={"server_code": "orange"})
            self.assertEqual(switch_response.status_code, 200)

            context_response = self.client.get("/api/runtime/sections/court_claim/capability-context")
            self.assertEqual(context_response.status_code, 200)
            context_payload = context_response.json()
            self.assertEqual(context_payload["selected_server_code"], "orange")
            self.assertEqual(context_payload["runtime_requirement"]["status"], "ready")
            self.assertTrue(context_payload["runtime_requirement"]["strict_cutover_enabled"])
            self.assertEqual(context_payload["runtime_requirement"]["reason_code"], "published_pack_ready")

            bundle_response = self.client.get(
                "/api/document-builder/bundle",
                params={"document_type": "court_claim"},
            )
            self.assertEqual(bundle_response.status_code, 200)

            page_response = self.client.get("/court-claim-test")
            self.assertEqual(page_response.status_code, 200)

    def test_complaint_strict_cutover_env_blocks_bootstrap_server_paths(self):
        self._register_verify_and_login("tester", "tester-complaint-strict-bootstrap@example.com")
        self.client.put(
            "/api/profile",
            json={
                "name": "Rep",
                "passport": "AA",
                "address": "Addr",
                "phone": "1234567",
                "discord": "disc",
                "passport_scan_url": "https://example.com/rep",
            },
        )

        with patch.dict(os.environ, {"OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS": "complaint"}, clear=False):
            context_response = self.client.get("/api/runtime/sections/complaint/capability-context")
            self.assertEqual(context_response.status_code, 200)
            context_payload = context_response.json()
            self.assertEqual(context_payload["selected_server_code"], "blackberry")
            self.assertEqual(context_payload["runtime_requirement"]["status"], "blocked")
            self.assertTrue(context_payload["runtime_requirement"]["strict_cutover_enabled"])
            self.assertEqual(context_payload["runtime_requirement"]["reason_code"], "published_pack_cutover_required")

            page_response = self.client.get("/complaint")
            self.assertEqual(page_response.status_code, 409)

            generate_response = self.client.post("/api/generate", json=self._complaint_payload())
            self.assertEqual(generate_response.status_code, 409)

    def test_complaint_strict_cutover_env_preserves_published_pack_paths(self):
        self._register_verify_and_login("tester", "tester-complaint-strict-published@example.com")
        self.client.put(
            "/api/profile",
            json={
                "name": "Rep",
                "passport": "AA",
                "address": "Addr",
                "phone": "1234567",
                "discord": "disc",
                "passport_scan_url": "https://example.com/rep",
            },
        )

        with patch.dict(os.environ, {"OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS": "complaint"}, clear=False), patch(
            "ogp_web.server_config.registry._load_effective_pack_from_db",
            side_effect=lambda *, server_code, at_timestamp=None: blackberry_published_pack() if server_code == "blackberry" else None,
        ):
            context_response = self.client.get("/api/runtime/sections/complaint/capability-context")
            self.assertEqual(context_response.status_code, 200)
            context_payload = context_response.json()
            self.assertEqual(context_payload["selected_server_code"], "blackberry")
            self.assertEqual(context_payload["runtime_requirement"]["status"], "ready")
            self.assertTrue(context_payload["runtime_requirement"]["strict_cutover_enabled"])
            self.assertEqual(context_payload["runtime_requirement"]["reason_code"], "published_pack_ready")

            page_response = self.client.get("/complaint")
            self.assertEqual(page_response.status_code, 200)

            generate_response = self.client.post("/api/generate", json=self._complaint_payload())
            self.assertEqual(generate_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
