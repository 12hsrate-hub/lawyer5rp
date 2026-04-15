from __future__ import annotations

import os
import threading
import sys
import time
import unittest
from datetime import datetime, timedelta, UTC
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
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
from ogp_web.storage.user_repository import UserRepository
from ogp_web.rate_limit import reset_for_testing as reset_rate_limit
from ogp_web.routes import admin as admin_route
from ogp_web.routes import complaint as complaint_route
from ogp_web.routes import admin as admin_route
from ogp_web.routes import exam_import as exam_import_route
from ogp_web.services import ai_service
from ogp_web.services import admin_ai_pipeline_service
from ogp_web.services.admin_task_ops_service import AdminTaskOpsService
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry
from ogp_web.services.generation_orchestrator import GenerationOrchestrator
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_store import UserStore
from tests.temp_helpers import make_temporary_directory
from tests.test_web_storage import (
    FakeAdminMetricsPostgresBackend,
    FakeExamAnswersPostgresBackend,
    FakeExamImportTasksPostgresBackend,
    PostgresBackend,
)


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = make_temporary_directory()
        root = Path(self.tmpdir.name)
        self.prev_test_users = os.environ.get("OGP_WEB_TEST_USERS")
        self.prev_bridge_mode = os.environ.get("OGP_GENERATION_BRIDGE_MODE")
        self.prev_cases_flag_mode = os.environ.get("OGP_FEATURE_FLAG_CASES_V1_MODE")
        self.prev_documents_flag_mode = os.environ.get("OGP_FEATURE_FLAG_DOCUMENTS_V2_MODE")
        self.prev_validation_flag_mode = os.environ.get("OGP_FEATURE_FLAG_VALIDATION_GATE_V1_MODE")
        self.prev_generation_legacy_write = os.environ.get("OGP_GENERATION_LEGACY_WRITE")
        os.environ["OGP_WEB_TEST_USERS"] = "tester"
        os.environ["OGP_GENERATION_BRIDGE_MODE"] = "shadow_write"
        os.environ["OGP_FEATURE_FLAG_CASES_V1_MODE"] = "all"
        os.environ["OGP_FEATURE_FLAG_DOCUMENTS_V2_MODE"] = "all"
        os.environ["OGP_FEATURE_FLAG_VALIDATION_GATE_V1_MODE"] = "all"
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
        if self.prev_bridge_mode is None:
            os.environ.pop("OGP_GENERATION_BRIDGE_MODE", None)
        else:
            os.environ["OGP_GENERATION_BRIDGE_MODE"] = self.prev_bridge_mode
        if self.prev_cases_flag_mode is None:
            os.environ.pop("OGP_FEATURE_FLAG_CASES_V1_MODE", None)
        else:
            os.environ["OGP_FEATURE_FLAG_CASES_V1_MODE"] = self.prev_cases_flag_mode
        if self.prev_documents_flag_mode is None:
            os.environ.pop("OGP_FEATURE_FLAG_DOCUMENTS_V2_MODE", None)
        else:
            os.environ["OGP_FEATURE_FLAG_DOCUMENTS_V2_MODE"] = self.prev_documents_flag_mode
        if self.prev_validation_flag_mode is None:
            os.environ.pop("OGP_FEATURE_FLAG_VALIDATION_GATE_V1_MODE", None)
        else:
            os.environ["OGP_FEATURE_FLAG_VALIDATION_GATE_V1_MODE"] = self.prev_validation_flag_mode
        if self.prev_generation_legacy_write is None:
            os.environ.pop("OGP_GENERATION_LEGACY_WRITE", None)
        else:
            os.environ["OGP_GENERATION_LEGACY_WRITE"] = self.prev_generation_legacy_write
        self.tmpdir.cleanup()

    def _extract_token(self, url: str) -> str:
        parsed = urlsplit(url)
        return parse_qs(parsed.query)["token"][0]

    def _register_verify_and_login(self, username: str, email: str, password: str = "Password123!") -> None:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "email": email, "password": password},
        )
        self.assertEqual(response.status_code, 200)
        verify_url = response.json()["verification_url"]
        self.assertTrue(verify_url)
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)

    def test_register_verify_login_profile_and_generate_flow(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "tester", "email": "tester@example.com", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["requires_email_verification"])
        self.assertTrue(payload["verification_url"])

        split = urlsplit(payload["verification_url"])
        response = self.client.get(f"{split.path}?{split.query}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Email", response.text)

        response = self.client.post("/api/auth/login", json={"username": "tester", "password": "Password123!"})
        self.assertEqual(response.status_code, 200)

        response = self.client.put(
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
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/api/generate",
            json={
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
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Обращение", response.json()["bbcode"])
        self.assertIsInstance(response.json().get("generated_document_id"), int)

    def test_generated_document_snapshot_history_endpoint(self):
        self._register_verify_and_login("snapshot_user", "snapshot@example.com")

        response = self.client.put(
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
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/api/generate",
            json={
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
            },
        )
        self.assertEqual(response.status_code, 200)
        document_id = int(response.json()["generated_document_id"])

        response = self.client.get("/api/generated-documents/history")
        self.assertEqual(response.status_code, 200)
        history_items = response.json()["items"]
        self.assertTrue(any(int(item["id"]) == document_id for item in history_items))

        response = self.client.get(f"/api/generated-documents/{document_id}/snapshot")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        snapshot = payload["context_snapshot"]
        self.assertIn("server", snapshot)
        self.assertIn("template_version", snapshot)
        self.assertIn("law_version_set", snapshot)
        self.assertIn("validation_rules_version", snapshot)
        self.assertIn("effective_config_snapshot", snapshot)
        self.assertIn("content_workflow", snapshot)
        self.assertIn("feature_flags", snapshot)
        self.assertIsNotNone(payload.get("generation_snapshot_id"))
        self.assertIsInstance(payload.get("provenance"), dict)
        self.assertEqual(payload["provenance"]["document_kind"], "complaint")

        backend_state = self.store.repository.backend._state
        self.assertGreaterEqual(len(backend_state["document_versions"]), 1)
        bridged_versions = list(backend_state["document_versions"].values())
        self.assertIsNotNone(bridged_versions[-1].get("generation_snapshot_id"))

    def test_generate_uses_adapter_snapshot_without_legacy_context_build_when_adapter_active(self):
        previous_adapter_mode = os.environ.get("OGP_FEATURE_FLAG_PILOT_RUNTIME_ADAPTER_V1_MODE")
        original_builder = complaint_route.build_generation_context_snapshot
        original_resolver = complaint_route.resolve_pilot_complaint_runtime_context
        try:
            os.environ["OGP_FEATURE_FLAG_PILOT_RUNTIME_ADAPTER_V1_MODE"] = "all"
            self._register_verify_and_login("adapter_snapshot_user", "adapter_snapshot_user@example.com")
            response = self.client.put(
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
            self.assertEqual(response.status_code, 200)

            def fail_legacy_snapshot(*args, **kwargs):
                raise AssertionError("legacy snapshot builder should not be called when adapter flow is active")

            class FakeAdapterContext:
                def to_generation_context_snapshot(self):
                    return {
                        "server": {"id": "blackberry", "code": "blackberry"},
                        "template_version": {"id": "adapter_template"},
                        "law_version_set": {"hash": "adapter_law_hash"},
                        "validation_rules_version": {"hash": "adapter_validation_hash"},
                        "effective_config_snapshot": {"template_version": "adapter_template"},
                        "content_workflow": {"applied_published_versions": {"template_version": "adapter_template"}},
                    }

            complaint_route.build_generation_context_snapshot = fail_legacy_snapshot
            complaint_route.resolve_pilot_complaint_runtime_context = lambda store, user: FakeAdapterContext()

            response = self.client.post(
                "/api/generate",
                json={
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
                },
            )
            self.assertEqual(response.status_code, 200)
        finally:
            complaint_route.build_generation_context_snapshot = original_builder
            complaint_route.resolve_pilot_complaint_runtime_context = original_resolver
            if previous_adapter_mode is None:
                os.environ.pop("OGP_FEATURE_FLAG_PILOT_RUNTIME_ADAPTER_V1_MODE", None)
            else:
                os.environ["OGP_FEATURE_FLAG_PILOT_RUNTIME_ADAPTER_V1_MODE"] = previous_adapter_mode

    def test_document_builder_bundle_endpoint(self):
        self._register_verify_and_login("tester", "bundle_tester@example.com")
        response = self.client.get("/api/document-builder/bundle", params={"server_id": "blackberry", "document_type": "court_claim"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["bundle_version"], "1.0.0")
        self.assertEqual(payload["server"], "blackberry")
        self.assertEqual(payload["document_type"], "court_claim")
        self.assertIn("sections", payload)
        self.assertIn("fields", payload)
        self.assertIn("choice_sets", payload)
        self.assertIn("validators", payload)
        self.assertIn("template", payload)
        self.assertIn("ai_profile", payload)
        self.assertIn("features", payload)
        self.assertIn("status", payload)
        self.assertIn("allowed_actions", payload)
        self.assertIn("supreme", payload["choice_sets"]["claim_kind_by_court_type"])

    def test_document_builder_bundle_unknown_document_type(self):
        self._register_verify_and_login("tester", "bundle_tester_unknown@example.com")
        response = self.client.get("/api/document-builder/bundle", params={"server_id": "blackberry", "document_type": "unknown"})
        self.assertEqual(response.status_code, 404)

    def test_generate_creates_case_and_versions_append_only_in_bridge(self):
        self._register_verify_and_login("bridge_user", "bridge_user@example.com")
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
        payload = {
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
        first = self.client.post("/api/generate", json=payload)
        second = self.client.post("/api/generate", json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        state = self.store.repository.backend._state
        self.assertEqual(len(state["cases"]), 1)
        case = next(iter(state["cases"].values()))
        self.assertEqual(case["server_id"], "blackberry")
        self.assertEqual(len(state["case_documents"]), 1)
        versions = sorted(state["document_versions"].values(), key=lambda item: item["version_number"])
        self.assertEqual([item["version_number"] for item in versions], [1, 2])
        self.assertTrue(all(item.get("generation_snapshot_id") for item in versions))

    def test_document_version_validation_endpoint_returns_latest_run(self):
        self._register_verify_and_login("validation_user", "validation_user@example.com")
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
        response = self.client.post(
            "/api/generate",
            json={
                "appeal_no": "1234",
                "org": "LSPD",
                "subject_names": "John Doe",
                "situation_description": "Описание",
                "violation_short": "Нарушение",
                "event_dt": "08.04.2026 14:30",
                "today_date": "08.04.2026",
                "victim": {"name": "Victim", "passport": "BB", "address": "Addr", "phone": "7654321", "discord": "victim", "passport_scan_url": "https://example.com/victim"},
                "contract_url": "https://example.com/contract",
                "bar_request_url": "",
                "official_answer_url": "",
                "mail_notice_url": "",
                "arrest_record_url": "",
                "personnel_file_url": "",
                "video_fix_urls": [],
                "provided_video_urls": [],
            },
        )
        self.assertEqual(response.status_code, 200)
        version_id = max(self.store.repository.backend._state["document_versions"].keys())
        validation_response = self.client.get(f"/api/document-versions/{version_id}/validation")
        self.assertEqual(validation_response.status_code, 200)
        payload = validation_response.json()
        self.assertEqual(payload["target_type"], "document_version")
        self.assertEqual(int(payload["target_id"]), int(version_id))

    def test_generate_bridge_failure_returns_error_without_legacy_fallback(self):
        self._register_verify_and_login("shadow_user", "shadow_user@example.com")
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
        original = GenerationOrchestrator.write_generation_bridge
        try:
            GenerationOrchestrator.write_generation_bridge = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
            with self.assertRaises(RuntimeError):
                self.client.post(
                    "/api/generate",
                    json={
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
                    },
                )
        finally:
            GenerationOrchestrator.write_generation_bridge = original

    def test_generate_uses_new_domain_id_and_snapshot_lookup(self):
        self._register_verify_and_login("new_only_user", "new_only_user@example.com")
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
        response = self.client.post(
            "/api/generate",
            json={
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
            },
        )
        self.assertEqual(response.status_code, 200)
        generated_id = int(response.json()["generated_document_id"])
        self.assertGreaterEqual(
            generated_id,
            GenerationOrchestrator.SYNTHETIC_GENERATED_DOCUMENT_ID_OFFSET + 1,
        )
        self.assertEqual(len(self.store.repository.backend._state["generated_documents"]), 0)

        snapshot_response = self.client.get(f"/api/generated-documents/{generated_id}/snapshot")
        self.assertEqual(snapshot_response.status_code, 200)
        self.assertEqual(int(snapshot_response.json()["id"]), generated_id)

    def test_history_prefers_new_domain_and_deduplicates_legacy(self):
        self._register_verify_and_login("history_bridge_user", "history_bridge_user@example.com")
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
        response = self.client.post(
            "/api/generate",
            json={
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
            },
        )
        self.assertEqual(response.status_code, 200)
        history = self.client.get("/api/generated-documents/history")
        self.assertEqual(history.status_code, 200)
        ids = [int(item["id"]) for item in history.json()["items"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_generated_documents_history_normalizes_datetime_created_at(self):
        self._register_verify_and_login("history_datetime_user", "history_datetime@example.com")
        original = GenerationOrchestrator.list_history
        try:
            GenerationOrchestrator.list_history = lambda *args, **kwargs: [
                {
                    "id": 42,
                    "document_kind": "complaint",
                    "result_text": "text",
                    "created_at": datetime(2026, 4, 14, 1, 0, tzinfo=UTC),
                    "source": "new_domain",
                }
            ]
            response = self.client.get("/api/generated-documents/history")
        finally:
            GenerationOrchestrator.list_history = original
        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertIsInstance(item["created_at"], str)
        self.assertTrue(item["created_at"].startswith("2026-04-14T01:00:00"))

    def test_cases_flow_creates_events_and_append_only_versions(self):
        self._register_verify_and_login("cases_user", "cases_user@example.com")

        create_case = self.client.post(
            "/api/cases",
            json={"server_id": "blackberry", "title": "Case A", "case_type": "complaint"},
        )
        self.assertEqual(create_case.status_code, 200)
        case_id = int(create_case.json()["id"])

        create_document = self.client.post(
            f"/api/cases/{case_id}/documents",
            json={"document_type": "complaint_draft"},
        )
        self.assertEqual(create_document.status_code, 200)
        document_id = int(create_document.json()["id"])

        version_1 = self.client.post(
            f"/api/documents/{document_id}/versions",
            json={"content_json": {"text": "v1"}},
        )
        self.assertEqual(version_1.status_code, 200)
        self.assertEqual(version_1.json()["version_number"], 1)

        version_2 = self.client.post(
            f"/api/documents/{document_id}/versions",
            json={"content_json": {"text": "v2"}},
        )
        self.assertEqual(version_2.status_code, 200)
        self.assertEqual(version_2.json()["version_number"], 2)

        versions = self.client.get(f"/api/documents/{document_id}/versions")
        self.assertEqual(versions.status_code, 200)
        self.assertEqual([item["version_number"] for item in versions.json()["items"]], [1, 2])

        backend_state = self.store.repository.backend._state
        event_types = [item["event_type"] for item in backend_state["case_events"]]
        self.assertIn("case_created", event_types)
        self.assertIn("document_added", event_types)
        self.assertIn("document_version_created", event_types)

    def test_cannot_create_case_without_server_id(self):
        self._register_verify_and_login("no_server_user", "no_server@example.com")
        response = self.client.post(
            "/api/cases",
            json={"title": "Case A", "case_type": "complaint"},
        )
        self.assertEqual(response.status_code, 422)

    def test_cannot_add_document_to_non_existing_case(self):
        self._register_verify_and_login("missing_case_user", "missing_case@example.com")
        response = self.client.post(
            "/api/cases/999999/documents",
            json={"document_type": "complaint_draft"},
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_use_hidden_default_server_scope(self):
        self._register_verify_and_login("scope_user", "scope_user@example.com")
        response = self.client.post(
            "/api/cases",
            json={"server_id": "linden", "title": "Case A", "case_type": "complaint"},
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_overview_returns_metrics_for_admin_user(self):
        self._register_verify_and_login("12345", "admin@example.com")

        response = self.client.put(
            "/api/profile",
            json={
                "name": "Admin Rep",
                "passport": "AA",
                "address": "Addr",
                "phone": "1234567",
                "discord": "admin",
                "passport_scan_url": "https://example.com/admin-passport",
            },
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/api/generate",
            json={
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
            },
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/admin/overview")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["totals"]["users_total"], 1)
        self.assertGreaterEqual(payload["totals"]["complaints_total"], 1)
        self.assertTrue(any(item["username"] == "12345" for item in payload["users"]))
        self.assertIn("exam_import", payload)
        self.assertIn("pending_scores", payload["exam_import"])
        self.assertIn("recent_entries", payload["exam_import"])
        self.assertIn("failed_entries", payload["exam_import"])
        self.assertIsInstance(payload["exam_import"]["recent_entries"], list)
        self.assertIsInstance(payload["exam_import"]["failed_entries"], list)
        self.assertIn("error_explorer", payload)
        self.assertIn("items", payload["error_explorer"])
        self.assertIn("by_event_type", payload["error_explorer"])
        self.assertIn("by_path", payload["error_explorer"])
        self.assertIn("ai_estimated_cost_total_usd", payload["totals"])
        self.assertIn("ai_total_tokens_total", payload["totals"])
        self.assertIn("ai_generation_total", payload["totals"])
        self.assertIn("model_policy", payload)
        self.assertEqual(payload["model_policy"]["recommended_defaults"]["default_tier"], "gpt-5.4-mini")
        self.assertIn("law_qa", payload["model_policy"]["model_routing"])

    def test_admin_dashboard_returns_kpis_alerts_and_links(self):
        self._register_verify_and_login("12345", "admin-dashboard@example.com")

        response = self.client.get("/api/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIn("kpis", payload)
        self.assertIn("alerts", payload)
        self.assertIn("quick_links", payload)
        self.assertIn("recent_events", payload)
        self.assertIn("top_endpoints", payload)
        self.assertTrue(any(item["id"] == "users_total" for item in payload["kpis"]))
        self.assertTrue(any(item["label"] == "Пользователи" for item in payload["quick_links"]))

    def test_admin_overview_supports_user_sort_and_csv_exports(self):
        self._register_verify_and_login("alpha", "alpha@example.com")
        self.client.post("/api/auth/logout")
        self._register_verify_and_login("beta", "beta@example.com")
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
        self.client.post(
            "/api/generate",
            json={
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
            },
        )
        self.client.post("/api/auth/logout")
        self._register_verify_and_login("12345", "admin2@example.com")

        response = self.client.get("/api/admin/overview?user_sort=username")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        usernames = [item["username"] for item in payload["users"]]
        self.assertEqual(usernames, sorted(usernames))

        users_csv = self.client.get("/api/admin/users.csv?user_sort=username")
        self.assertEqual(users_csv.status_code, 200)
        self.assertIn("text/csv", users_csv.headers["content-type"])
        self.assertIn("username,email,created_at", users_csv.text)

        events_csv = self.client.get("/api/admin/events.csv")
        self.assertEqual(events_csv.status_code, 200)

        self.assertIn("text/csv", events_csv.headers["content-type"])
        self.assertIn("created_at,username,event_type,path", events_csv.text)

    def test_admin_performance_response_includes_legacy_compatible_fields(self):
        self._register_verify_and_login("12345", "admin-perf@example.com")

        response = self.client.get("/api/admin/performance?window_minutes=30&top_endpoints=6")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("latency", payload)
        self.assertIn("rates", payload)
        self.assertIn("top_endpoints", payload)
        self.assertIn("totals", payload)
        self.assertIn("total_requests", payload["totals"])
        self.assertIn("failed_requests", payload["totals"])
        self.assertTrue(response.headers.get("x-request-id"))

    def test_admin_overview_returns_partial_errors_when_exam_store_fails(self):
        self._register_verify_and_login("12345", "admin-partial@example.com")

        class BrokenExamStore:
            def count_entries_needing_scores(self):
                raise RuntimeError("broken_count")

            def list_entries(self, limit: int = 8):
                raise RuntimeError("broken_list_entries")

            def list_entries_with_failed_scores(self, limit: int = 5):
                raise RuntimeError("broken_failed_entries")

        original_exam_store = self.client.app.state.exam_answers_store
        self.client.app.state.exam_answers_store = BrokenExamStore()
        try:
            response = self.client.get("/api/admin/overview")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("partial_errors", payload)
            self.assertGreaterEqual(len(payload["partial_errors"]), 1)
            self.assertIn("exam_import", payload)
            self.assertIsInstance(payload["exam_import"].get("recent_entries"), list)
            self.assertIsInstance(payload["exam_import"].get("failed_entries"), list)
            self.assertIn("error_explorer", payload)
        finally:
            self.client.app.state.exam_answers_store = original_exam_store

    def test_admin_law_sources_preview_reports_duplicates_and_invalid_urls(self):
        self._register_verify_and_login("12345", "admin-law-preview@example.com")

        class DummyWorkflowService:
            repository = object()

        self.client.app.dependency_overrides[admin_route.get_content_workflow_service] = lambda: DummyWorkflowService()
        try:
            response = self.client.post(
                "/api/admin/law-sources/preview",
                json={
                    "source_urls": [
                        "https://example.com/law/a",
                        "ftp://example.com/law/a",
                        "https://example.com/law/a",
                        "invalid-url",
                        "http://example.com/law/b",
                    ],
                    "persist_sources": False,
                },
            )
        finally:
            self.client.app.dependency_overrides.pop(admin_route.get_content_workflow_service, None)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["accepted_urls"],
            [
                "https://example.com/law/a",
                "http://example.com/law/b",
            ],
        )
        self.assertEqual(
            payload["invalid_urls"],
            [
                "ftp://example.com/law/a",
                "invalid-url",
            ],
        )
        self.assertEqual(payload["duplicate_count"], 1)
        self.assertEqual(payload["accepted_count"], 2)
        self.assertEqual(payload["invalid_count"], 2)

    def test_admin_law_sources_rebuild_rejects_invalid_urls_with_examples(self):
        self._register_verify_and_login("12345", "admin-law-rebuild@example.com")

        class DummyWorkflowService:
            repository = object()

        self.client.app.dependency_overrides[admin_route.get_content_workflow_service] = lambda: DummyWorkflowService()
        try:
            response = self.client.post(
                "/api/admin/law-sources/rebuild",
                json={
                    "source_urls": [
                        "https://example.com/law/a",
                        "invalid-url",
                        "ftp://example.com/law/b",
                    ],
                    "persist_sources": False,
                },
            )
        finally:
            self.client.app.dependency_overrides.pop(admin_route.get_content_workflow_service, None)

        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"]
        self.assertEqual(len(detail), 1)
        self.assertIn("source_urls_invalid", detail[0])
        self.assertIn("invalid-url", detail[0])
        self.assertIn("ftp://example.com/law/b", detail[0])

    def test_admin_overview_forbidden_for_non_admin(self):
        self._register_verify_and_login("tester", "tester@example.com")
        response = self.client.get("/api/admin/overview")
        self.assertEqual(response.status_code, 403)

    def test_admin_law_sources_rebuild_async_returns_conflict_when_task_already_active(self):
        self._register_verify_and_login("12345", "admin-law-conflict@example.com")
        task_service = AdminTaskOpsService(tasks_path=Path(self.tmpdir.name) / "admin_tasks_test_conflict.json")
        task_service.put_task(
            {
                "task_id": "law-rebuild-active",
                "scope": "law_sources_rebuild",
                "server_code": "blackberry",
                "status": "running",
            }
        )
        self.client.app.dependency_overrides[admin_route.get_admin_task_ops_service] = lambda: task_service
        try:
            response = self.client.post(
                "/api/admin/law-sources/rebuild-async",
                json={"source_urls": ["https://example.com/law/1"], "persist_sources": True},
            )
            self.assertEqual(response.status_code, 409)
            detail = response.json().get("detail", [])
            self.assertTrue(any("law_rebuild_already_in_progress:law-rebuild-active" in str(item) for item in detail))
        finally:
            self.client.app.dependency_overrides.pop(admin_route.get_admin_task_ops_service, None)

    def test_admin_law_sources_task_status_forbidden_for_other_server_task(self):
        self._register_verify_and_login("12345", "admin-law-task@example.com")
        task_service = AdminTaskOpsService(tasks_path=Path(self.tmpdir.name) / "admin_tasks_test_foreign.json")
        task_service.put_task(
            {
                "task_id": "law-rebuild-foreign",
                "scope": "law_sources_rebuild",
                "server_code": "orange",
                "status": "running",
            }
        )
        self.client.app.dependency_overrides[admin_route.get_admin_task_ops_service] = lambda: task_service
        try:
            response = self.client.get("/api/admin/law-sources/tasks/law-rebuild-foreign")
            self.assertEqual(response.status_code, 403)
        finally:
            self.client.app.dependency_overrides.pop(admin_route.get_admin_task_ops_service, None)

    def test_admin_law_sources_task_status_exposes_canonical_status(self):
        self._register_verify_and_login("12345", "admin-law-task-ok@example.com")
        task_service = AdminTaskOpsService(tasks_path=Path(self.tmpdir.name) / "admin_tasks_test_ok.json")
        task_service.put_task(
            {
                "task_id": "law-rebuild-ok",
                "scope": "law_sources_rebuild",
                "server_code": "blackberry",
                "status": "finished",
            }
        )
        self.client.app.dependency_overrides[admin_route.get_admin_task_ops_service] = lambda: task_service
        try:
            response = self.client.get("/api/admin/law-sources/tasks/law-rebuild-ok")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "finished")
            self.assertEqual(payload["raw_status"], "finished")
            self.assertEqual(payload["canonical_status"], "succeeded")
        finally:
            self.client.app.dependency_overrides.pop(admin_route.get_admin_task_ops_service, None)

    def test_admin_task_status_exposes_canonical_status(self):
        self._register_verify_and_login("12345", "admin-task-status@example.com")
        task_service = AdminTaskOpsService(tasks_path=Path(self.tmpdir.name) / "admin_tasks_status.json")
        task_service.put_task(
            {
                "task_id": "admin-bulk-ok",
                "scope": "bulk_user_mutation",
                "server_code": "blackberry",
                "status": "finished",
            }
        )
        self.client.app.dependency_overrides[admin_route.get_admin_task_ops_service] = lambda: task_service
        try:
            response = self.client.get("/api/admin/tasks/admin-bulk-ok")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "finished")
            self.assertEqual(payload["raw_status"], "finished")
            self.assertEqual(payload["canonical_status"], "succeeded")
        finally:
            self.client.app.dependency_overrides.pop(admin_route.get_admin_task_ops_service, None)

    def test_admin_async_jobs_overview_exposes_problem_summary(self):
        self._register_verify_and_login("12345", "admin-async-overview@example.com")

        class DummyAsyncJobService:
            def list_jobs(self, *, server_id: str, limit: int = 50):
                self.server_id = server_id
                self.limit = limit
                return [
                    {
                        "id": 101,
                        "job_type": "content_reindex",
                        "status": "retry_scheduled",
                        "next_run_at": "2026-04-15T01:00:00+00:00",
                        "last_error_message": "temporary failure",
                    },
                    {
                        "id": 202,
                        "job_type": "content_reindex",
                        "status": "dead_lettered",
                        "next_run_at": "",
                        "last_error_message": "fatal failure",
                    },
                    {
                        "id": 303,
                        "job_type": "document_export",
                        "status": "processing",
                        "next_run_at": "",
                        "last_error_message": "",
                    },
                ]

        service = DummyAsyncJobService()
        with patch("ogp_web.routes.admin._get_async_job_service", return_value=service):
            response = self.client.get("/api/admin/async-jobs/overview")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(service.server_id, "blackberry")
        self.assertEqual(service.limit, 100)
        self.assertEqual(payload["summary"]["total_jobs"], 3)
        self.assertEqual(payload["summary"]["problem_jobs"], 2)
        self.assertEqual(payload["summary"]["failed_jobs"], 1)
        self.assertEqual(payload["summary"]["retry_scheduled_jobs"], 1)
        self.assertEqual(payload["summary"]["running_jobs"], 1)
        statuses = {item["raw_status"]: item["canonical_status"] for item in payload["problem_jobs"]}
        self.assertEqual(statuses["retry_scheduled"], "retry_scheduled")
        self.assertEqual(statuses["dead_lettered"], "failed")
        self.assertEqual(
            {item["job_type"]: item["count"] for item in payload["by_job_type"]},
            {"content_reindex": 2},
        )

    def test_admin_exam_import_overview_exposes_problem_summary(self):
        self._register_verify_and_login("12345", "admin-exam-import-overview@example.com")

        response = self.client.get("/api/admin/exam-import/overview")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("summary", payload)
        self.assertIn("pending_scores", payload["summary"])
        self.assertIn("failed_entries", payload["summary"])
        self.assertIn("problem_signals", payload["summary"])
        self.assertIn("failed_entries", payload)
        self.assertIn("recent_failures", payload)
        self.assertIn("recent_row_failures", payload)
        self.assertIsInstance(payload["failed_entries"], list)
        self.assertIsInstance(payload["recent_failures"], list)
        self.assertIsInstance(payload["recent_row_failures"], list)

    def test_law_sources_preview_forbidden_for_user_without_manage_laws_permission(self):
        self._register_verify_and_login("plainuser_preview", "plainuser-preview@example.com")
        response = self.client.post(
            "/api/admin/law-sources/preview",
            json={"source_urls": ["https://example.com/law/1"], "persist_sources": False},
        )
        self.assertEqual(response.status_code, 403)

    def test_law_sources_preview_forbidden_for_foreign_server_without_manage_servers(self):
        self._register_verify_and_login("law_manager_preview", "law-manager-preview@example.com")

        class DummyWorkflowService:
            repository = object()

        class DummyPermissionSet:
            def __init__(self, codes: set[str], server_code: str):
                self.codes = {str(code).strip().lower() for code in codes}
                self.server_code = server_code

            def has(self, permission: str) -> bool:
                normalized = str(permission or "").strip().lower()
                if not normalized:
                    return True
                return normalized in self.codes

        def fake_build_permission_set(_, __, server_config):
            return DummyPermissionSet({"manage_laws"}, getattr(server_config, "code", "blackberry"))

        self.client.app.dependency_overrides[admin_route.get_content_workflow_service] = lambda: DummyWorkflowService()
        try:
            with patch(
                "ogp_web.dependencies.build_permission_set",
                side_effect=fake_build_permission_set,
            ), patch(
                "ogp_web.services.server_context_service.build_permission_set",
                side_effect=fake_build_permission_set,
            ), patch(
                "ogp_web.services.server_context_service.get_server_config",
                side_effect=lambda server_code: type("Cfg", (), {"code": server_code})(),
            ):
                response = self.client.post(
                    "/api/admin/law-sources/preview",
                    json={
                        "server_code": "orange",
                        "source_urls": ["https://example.com/law/1"],
                        "persist_sources": False,
                    },
                )
        finally:
            self.client.app.dependency_overrides.pop(admin_route.get_content_workflow_service, None)

        self.assertEqual(response.status_code, 403)
        self.assertTrue(any("другого сервера" in str(item).lower() for item in response.json().get("detail", [])))

    def test_health_endpoint_reports_ok(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("version", payload)
        self.assertTrue(payload["checks"]["user_store"]["ok"])
        self.assertTrue(payload["checks"]["exam_answers_store"]["ok"])
        self.assertTrue(payload["checks"]["admin_metrics_store"]["ok"])
        self.assertTrue(payload["checks"]["exam_import_tasks_store"]["ok"])
        self.assertTrue(payload["checks"]["rate_limiter"]["ok"])

    def test_health_endpoint_returns_503_when_required_check_fails(self):
        tmp_path = Path(self.tmpdir.name)

        class UnhealthyAdminMetricsStore:
            def __init__(self):
                self.db_path = tmp_path / "unhealthy_admin_metrics.db"

            def healthcheck(self) -> dict[str, object]:
                return {"backend": "postgres", "ok": False, "error": "forced_failure"}

            def log_event(self, *args, **kwargs) -> bool:
                return False

        client = TestClient(
            create_app(self.store, self.exam_store, UnhealthyAdminMetricsStore(), self.task_registry),
            base_url="https://testserver",
        )
        try:
            response = client.get("/health")
            self.assertEqual(response.status_code, 503)
            payload = response.json()
            self.assertEqual(payload["status"], "degraded")
            self.assertFalse(payload["checks"]["admin_metrics_store"]["ok"])
        finally:
            client.close()
            client.app.state.rate_limiter.repository.close()
            client.app.state.user_store.repository.close()

    def test_complaint_draft_can_be_saved_loaded_and_cleared(self):
        self._register_verify_and_login("tester", "draft@example.com")

        draft = {
            "appeal_no": "1234",
            "org": "GOV",
            "subject_names": "Pavel Clayton",
            "situation_description": "Draft body",
            "violation_short": "Short text",
            "video_fix_urls": ["https://example.com/video"],
            "result": "BBCode result",
        }

        response = self.client.put("/api/complaint-draft", json={"draft": draft})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["draft"]["context.organization"], "GOV")

        response = self.client.get("/api/complaint-draft")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["draft"]["context.subject_names"], "Pavel Clayton")
        self.assertEqual(response.json()["draft"]["draft.result"], "BBCode result")
        self.assertTrue(response.json()["updated_at"])

        response = self.client.delete("/api/complaint-draft")
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/complaint-draft")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["draft"], {})


    def test_complaint_draft_rejects_unknown_keys(self):
        self._register_verify_and_login("tester_unknown", "draft-unknown@example.com")

        response = self.client.put("/api/complaint-draft", json={"draft": {"unknown.field": "x"}})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown complaint draft keys", str(response.json().get("detail", "")))

    def test_profile_selected_server_uses_shared_context_resolution_path(self):
        self._register_verify_and_login("tester_switch", "draft-switch@example.com")

        response = self.client.patch("/api/profile/selected-server", json={"server_code": "blackberry"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["server_code"], "blackberry")
        self.assertIn("Обновите страницу", payload["message"])
        self.assertIsInstance(payload.get("switch_actions"), list)

    def test_complaint_draft_accepts_envelope_payload_and_flattens_document(self):
        self._register_verify_and_login("tester_envelope", "draft-envelope@example.com")

        response = self.client.put(
            "/api/complaint-draft",
            json={
                "draft": {
                    "key": "draft:tester_envelope:blackberry:complaint",
                    "user_id": "tester_envelope",
                    "server_id": "blackberry",
                    "document_type": "complaint",
                    "profile": {},
                    "document": {
                        "draft": {
                            "org": "GOV",
                            "subject_names": "Pavel Clayton",
                            "situation_description": "Draft body",
                        },
                        "result": "BBCode result",
                    },
                    "metadata": {
                        "bundle_version": "complaint.v3",
                        "schema_hash": "complaint-schema-v3",
                        "status": "draft",
                        "allowed_actions": ["edit", "generate", "clear"],
                    },
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["draft"]["context.organization"], "GOV")
        self.assertEqual(payload["draft"]["context.subject_names"], "Pavel Clayton")
        self.assertEqual(payload["draft"]["draft.result"], "BBCode result")

    def test_admin_can_force_verify_email(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "plainuser", "email": "plainuser@example.com", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)

        login_response = self.client.post("/api/auth/login", json={"username": "plainuser", "password": "Password123!"})
        self.assertEqual(login_response.status_code, 400)

        self._register_verify_and_login("12345", "admin@example.com")
        response = self.client.post("/api/admin/users/plainuser/verify-email")
        self.assertEqual(response.status_code, 200)

        self.client.post("/api/auth/logout")
        login_response = self.client.post("/api/auth/login", json={"username": "plainuser", "password": "Password123!"})
        self.assertEqual(login_response.status_code, 200)

    def test_admin_can_block_and_unblock_user(self):
        self._register_verify_and_login("blockeduser", "blockeduser@example.com")
        self.client.post("/api/auth/logout")
        self._register_verify_and_login("12345", "admin@example.com")

        response = self.client.post("/api/admin/users/blockeduser/block", json={"reason": "test"})
        self.assertEqual(response.status_code, 200)

        self.client.post("/api/auth/logout")
        login_response = self.client.post("/api/auth/login", json={"username": "blockeduser", "password": "Password123!"})
        self.assertEqual(login_response.status_code, 400)

        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})
        response = self.client.post("/api/admin/users/blockeduser/unblock")
        self.assertEqual(response.status_code, 200)

        self.client.post("/api/auth/logout")
        login_response = self.client.post("/api/auth/login", json={"username": "blockeduser", "password": "Password123!"})
        self.assertEqual(login_response.status_code, 200)

    def test_admin_deactivate_and_reactivate_restores_access(self):
        self._register_verify_and_login("deactuser", "deactuser@example.com")
        self.client.post("/api/auth/logout")
        self._register_verify_and_login("12345", "admin@example.com")

        response = self.client.post("/api/admin/users/deactuser/deactivate", json={"reason": "policy"})
        self.assertEqual(response.status_code, 200)

        self.client.post("/api/auth/logout")
        login_response = self.client.post("/api/auth/login", json={"username": "deactuser", "password": "Password123!"})
        self.assertEqual(login_response.status_code, 400)

        self.client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})
        response = self.client.post("/api/admin/users/deactuser/reactivate")
        self.assertEqual(response.status_code, 200)

        self.client.post("/api/auth/logout")
        login_response = self.client.post("/api/auth/login", json={"username": "deactuser", "password": "Password123!"})
        self.assertEqual(login_response.status_code, 200)

    def test_api_quota_daily_blocks_after_limit(self):
        self._register_verify_and_login("quotauser", "quotauser@example.com")
        self.store.admin_set_daily_quota("quotauser", 1)

        first = self.client.get("/api/profile")
        self.assertEqual(first.status_code, 200)

        second = self.client.get("/api/profile")
        self.assertEqual(second.status_code, 429)

    def test_admin_overview_is_not_blocked_by_user_daily_quota(self):
        self._register_verify_and_login("12345", "admin-quota@example.com")
        self.store.admin_set_daily_quota("12345", 1)

        first = self.client.get("/api/profile")
        self.assertEqual(first.status_code, 200)

        admin_overview = self.client.get("/api/admin/overview")
        self.assertEqual(admin_overview.status_code, 200)

    def test_admin_quota_429_event_contains_policy_meta(self):
        previous_admin_quota = os.environ.get("OGP_WEB_ADMIN_API_QUOTA_DAILY")
        os.environ["OGP_WEB_ADMIN_API_QUOTA_DAILY"] = "1"
        try:
            self._register_verify_and_login("12345", "admin-policy@example.com")

            first = self.client.get("/api/admin/overview")
            self.assertEqual(first.status_code, 200)

            second = self.client.get("/api/admin/overview")
            self.assertEqual(second.status_code, 429)

            last_event = self.admin_store.backend._state["metric_events"][-1]
            self.assertEqual(last_event["status_code"], 429)
            self.assertEqual(last_event["path"], "/api/admin/overview")
            self.assertEqual(last_event["username"], "12345")
            meta = last_event["meta_json"]
            self.assertEqual(meta["policy_name"], "admin_quota_daily")
            self.assertEqual(meta["username"], "12345")
            self.assertTrue(meta["request_id"])
        finally:
            if previous_admin_quota is None:
                os.environ.pop("OGP_WEB_ADMIN_API_QUOTA_DAILY", None)
            else:
                os.environ["OGP_WEB_ADMIN_API_QUOTA_DAILY"] = previous_admin_quota

    def test_blocked_user_cannot_use_existing_session(self):
        self._register_verify_and_login("sessionuser", "sessionuser@example.com")
        session_client = self.client

        admin_client = TestClient(
            create_app(self.store, self.exam_store, self.admin_store, self.task_registry),
            base_url="https://testserver",
        )
        try:
            response = admin_client.post(
                "/api/auth/register",
                json={"username": "12345", "email": "admin@example.com", "password": "Password123!"},
            )
            verify_url = response.json()["verification_url"]
            split = urlsplit(verify_url)
            admin_client.get(f"{split.path}?{split.query}")
            admin_client.post("/api/auth/login", json={"username": "12345", "password": "Password123!"})
            response = admin_client.post("/api/admin/users/sessionuser/block", json={"reason": "test"})
            self.assertEqual(response.status_code, 200)
        finally:
            admin_client.close()
            admin_client.app.state.rate_limiter.repository.close()
            admin_client.app.state.user_store.repository.close()

        response = session_client.get("/api/auth/me")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_grant_tester_status(self):
        self._register_verify_and_login("plainuser", "plainuser@example.com")
        self.client.post("/api/auth/logout")
        self._register_verify_and_login("12345", "admin@example.com")

        response = self.client.post("/api/admin/users/plainuser/grant-tester")
        self.assertEqual(response.status_code, 200)
        payload = self.client.get("/api/admin/overview").json()
        target = next(item for item in payload["users"] if item["username"] == "plainuser")
        self.assertTrue(target["is_tester"])

    def test_bulk_set_daily_quota_requires_daily_limit(self):
        self._register_verify_and_login("plainbulk", "plainbulk@example.com")
        self.client.post("/api/auth/logout")
        self._register_verify_and_login("12345", "admin@example.com")

        response = self.client.post(
            "/api/admin/users/bulk-actions",
            json={"usernames": ["plainbulk"], "action": "set_daily_quota", "run_async": False},
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_can_change_email_and_reset_password(self):
        self._register_verify_and_login("emailuser", "emailold@example.com")
        self.client.post("/api/auth/logout")
        self._register_verify_and_login("12345", "admin@example.com")

        response = self.client.post("/api/admin/users/emailuser/email", json={"email": "emailnew@example.com"})
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/admin/users/emailuser/verify-email")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/admin/users/emailuser/reset-password", json={"password": "NewPassword456!"})
        self.assertEqual(response.status_code, 200)

        self.client.post("/api/auth/logout")
        login_response = self.client.post("/api/auth/login", json={"username": "emailnew@example.com", "password": "NewPassword456!"})
        self.assertEqual(login_response.status_code, 200)

    def test_admin_can_reset_exam_scores_for_specific_user(self):
        self.exam_store.import_rows(
            [
                {
                    "source_row": 2,
                    "submitted_at": "2026-04-10 10:00:00",
                    "full_name": "User One",
                    "discord_tag": "user.one#1",
                    "passport": "111111",
                    "exam_format": "remote",
                    "payload": {"Question F": "Ответ"},
                    "answer_count": 1,
                },
                {
                    "source_row": 3,
                    "submitted_at": "2026-04-10 10:01:00",
                    "full_name": "User Two",
                    "discord_tag": "user.two#2",
                    "passport": "222222",
                    "exam_format": "remote",
                    "payload": {"Question F": "Ответ"},
                    "answer_count": 1,
                },
            ]
        )
        self.exam_store.save_exam_scores(2, [{"column": "F", "score": 88, "rationale": "ok"}])
        self.exam_store.save_exam_scores(3, [{"column": "F", "score": 92, "rationale": "ok"}])

        self._register_verify_and_login("12345", "admin-reset@example.com")
        response = self.client.post(
            "/api/admin/exam-import/reset-scores",
            json={"discord_tag": "user.one#1"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["reset_count"], 1)

        target = self.exam_store.get_entry(2)
        other = self.exam_store.get_entry(3)
        self.assertIsNotNone(target)
        self.assertEqual(target.get("exam_scores"), [])
        self.assertIsNone(target.get("average_score"))
        self.assertIsNotNone(other)
        self.assertEqual(other.get("average_score"), 92.0)

    def test_admin_reset_exam_scores_requires_filter(self):
        self._register_verify_and_login("12345", "admin-reset-empty@example.com")
        response = self.client.post("/api/admin/exam-import/reset-scores", json={})
        self.assertEqual(response.status_code, 400)

    def test_generate_flow_survives_admin_metrics_write_failure(self):
        tmp_path = Path(self.tmpdir.name)

        class BrokenAdminMetricsStore(AdminMetricsStore):
            def __init__(self):
                self.db_path = tmp_path / "broken_admin_metrics.db"

            def _connect(self):
                raise RuntimeError("attempt to write a readonly database")

        broken_admin_store = BrokenAdminMetricsStore()
        client = TestClient(
            create_app(self.store, self.exam_store, broken_admin_store, self.task_registry),
            base_url="https://testserver",
        )
        try:
            response = client.post(
                "/api/auth/register",
                json={"username": "tester", "email": "tester-metrics@example.com", "password": "Password123!"},
            )
            self.assertEqual(response.status_code, 200)
            verify_url = response.json()["verification_url"]
            split = urlsplit(verify_url)
            client.get(f"{split.path}?{split.query}")
            response = client.post("/api/auth/login", json={"username": "tester", "password": "Password123!"})
            self.assertEqual(response.status_code, 200)

            response = client.put(
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
            self.assertEqual(response.status_code, 200)

            response = client.post(
                "/api/generate",
                json={
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
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("Обращение", response.json()["bbcode"])
        finally:
            client.close()
            client.app.state.rate_limiter.repository.close()
            client.app.state.user_store.repository.close()

    def test_login_requires_verified_email(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "tester2", "email": "tester2@example.com", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post("/api/auth/login", json={"username": "tester2", "password": "Password123!"})
        self.assertEqual(response.status_code, 400)

    def test_forgot_password_and_reset_flow(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "tester3", "email": "tester3@example.com", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)
        verify_url = response.json()["verification_url"]
        self.client.get(f"{urlsplit(verify_url).path}?{urlsplit(verify_url).query}")

        response = self.client.post("/api/auth/forgot-password", json={"email": "tester3@example.com"})
        self.assertEqual(response.status_code, 200)
        reset_url = response.json()["verification_url"]
        self.assertTrue(reset_url)

        split = urlsplit(reset_url)
        response = self.client.get(f"{split.path}?{split.query}")
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/api/auth/reset-password",
            json={"token": self._extract_token(reset_url), "password": "NewPassword456!"},
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post("/api/auth/login", json={"username": "tester3@example.com", "password": "NewPassword456!"})
        self.assertEqual(response.status_code, 200)

    def test_test_complaint_page_visible_only_for_test_user(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "tester", "email": "tester4@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        self.client.get(f"{urlsplit(verify_url).path}?{urlsplit(verify_url).query}")
        self.client.post("/api/auth/login", json={"username": "tester", "password": "Password123!"})

        response = self.client.get("/complaint-test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("complaint-preset", response.text)

    def test_extract_principal_endpoint_sets_dash_for_missing_address(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "tester", "email": "tester5@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        self.client.get(f"{urlsplit(verify_url).path}?{urlsplit(verify_url).query}")
        self.client.post("/api/auth/login", json={"username": "tester", "password": "Password123!"})

        original_extract = ai_service.extract_principal_fields_with_proxy_fallback

        def fake_extract_principal_fields_with_proxy_fallback(**kwargs):
            _ = kwargs
            return {
                "principal_name": "Principal Name",
                "principal_passport": "123456",
                "principal_phone": "7654321",
                "principal_address": "",
                "principal_discord": "principal",
                "source_summary": "found fields",
                "confidence": "high",
                "missing_fields": ["principal_address"],
            }

        ai_service.extract_principal_fields_with_proxy_fallback = fake_extract_principal_fields_with_proxy_fallback
        try:
            response = self.client.post("/api/ai/extract-principal", json={"image_data_url": "data:image/png;base64,AAAA"})
        finally:
            ai_service.extract_principal_fields_with_proxy_fallback = original_extract

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["principal_address"], "-")
        self.assertEqual(payload["principal_phone"], "7654321")

    def test_extract_principal_endpoint_rejects_non_image_payload(self):
        self._register_verify_and_login("tester", "tester6@example.com")

        response = self.client.post("/api/ai/extract-principal", json={"image_data_url": "data:text/plain;base64,AAAA"})
        self.assertEqual(response.status_code, 400)

    def test_auth_me_and_logout_flow(self):
        self._register_verify_and_login("tester", "tester8@example.com")

        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "tester")

        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_suggest_endpoint_returns_ai_text(self):
        self._register_verify_and_login("tester", "tester9@example.com")

        original_suggest = ai_service.suggest_description_with_proxy_fallback_result
        ai_service.suggest_description_with_proxy_fallback_result = lambda **kwargs: ai_service.TextGenerationResult(
            text="AI text",
            usage=ai_service.AiUsageSummary(input_tokens=8, output_tokens=3, total_tokens=11),
            cache_hit=False,
            attempt_path="direct",
            attempt_duration_ms=120,
            route_policy="direct_first",
        )
        try:
            response = self.client.post(
                "/api/ai/suggest",
                json={
                    "victim_name": "Victim",
                    "org": "LSPD",
                    "subject": "Officer",
                    "event_dt": "08.04.2026 14:30",
                    "raw_desc": "Draft",
                    "complaint_basis": "wrongful_article",
                    "main_focus": "Спорная квалификация",
                },
            )
        finally:
            ai_service.suggest_description_with_proxy_fallback_result = original_suggest

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "AI text")
        self.assertTrue(response.json()["generation_id"])
        self.assertIn(response.json()["guard_status"], {"pass", "warn"})

    def test_suggest_endpoint_runs_generation_via_threadpool(self):
        self._register_verify_and_login("tester_suggest_threadpool", "tester_suggest_threadpool@example.com")

        original_run_in_threadpool = complaint_route.run_in_threadpool
        original_suggest_details = complaint_route.ai_service.suggest_text_details
        original_limiter = complaint_route.SUGGEST_CONCURRENCY_LIMITER
        complaint_route.SUGGEST_CONCURRENCY_LIMITER = complaint_route.SuggestConcurrencyLimiter(max_concurrency=2, retry_after_seconds=5)
        captured: dict[str, object] = {}

        def fake_suggest_details(payload, *, server_code):
            captured["server_code"] = server_code
            return type(
                "SuggestTextResult",
                (),
                {
                    "text": "AI text",
                    "generation_id": "gen_suggest_threadpool",
                    "guard_status": "pass",
                    "contract_version": "legal_pipeline.v1",
                    "warnings": [],
                    "shadow": {"enabled": False, "profile": "", "diverged": False, "overlap_count": 0},
                    "telemetry": {},
                    "budget_status": "ok",
                    "budget_warnings": [],
                    "budget_policy": {"flow": "suggest"},
                    "retrieval_ms": 10,
                    "openai_ms": 20,
                    "total_suggest_ms": 30,
                },
            )()

        async def fake_run_in_threadpool(func, *args, **kwargs):
            captured["func"] = func
            captured["args"] = args
            captured["kwargs"] = kwargs
            return func(*args, **kwargs)

        complaint_route.ai_service.suggest_text_details = fake_suggest_details
        complaint_route.run_in_threadpool = fake_run_in_threadpool
        try:
            response = self.client.post(
                "/api/ai/suggest",
                json={
                    "victim_name": "Victim",
                    "org": "LSPD",
                    "subject": "Officer",
                    "event_dt": "08.04.2026 14:30",
                    "raw_desc": "Draft",
                    "complaint_basis": "wrongful_article",
                    "main_focus": "Спорная квалификация",
                },
            )
        finally:
            complaint_route.run_in_threadpool = original_run_in_threadpool
            complaint_route.ai_service.suggest_text_details = original_suggest_details
            complaint_route.SUGGEST_CONCURRENCY_LIMITER = original_limiter

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "AI text")
        self.assertIs(captured["func"], fake_suggest_details)
        self.assertEqual(captured["kwargs"]["server_code"], "blackberry")
        self.assertEqual(captured["server_code"], "blackberry")

    def test_suggest_endpoint_returns_429_when_limiter_is_saturated(self):
        self._register_verify_and_login("tester_suggest_overload", "tester_suggest_overload@example.com")

        original_limiter = complaint_route.SUGGEST_CONCURRENCY_LIMITER
        original_suggest_details = complaint_route.ai_service.suggest_text_details
        complaint_route.SUGGEST_CONCURRENCY_LIMITER = complaint_route.SuggestConcurrencyLimiter(max_concurrency=1, retry_after_seconds=7)
        called = {"suggest": False}

        def fake_suggest_details(payload, *, server_code):
            called["suggest"] = True
            return original_suggest_details(payload, server_code=server_code)

        complaint_route.ai_service.suggest_text_details = fake_suggest_details
        try:
            self.assertTrue(complaint_route.SUGGEST_CONCURRENCY_LIMITER.try_acquire())
            response = self.client.post(
                "/api/ai/suggest",
                json={
                    "victim_name": "Victim",
                    "org": "LSPD",
                    "subject": "Officer",
                    "event_dt": "08.04.2026 14:30",
                    "raw_desc": "Draft",
                    "complaint_basis": "wrongful_article",
                    "main_focus": "Спорная квалификация",
                },
            )
        finally:
            complaint_route.SUGGEST_CONCURRENCY_LIMITER.release()
            complaint_route.SUGGEST_CONCURRENCY_LIMITER = original_limiter
            complaint_route.ai_service.suggest_text_details = original_suggest_details

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers.get("Retry-After"), "7")
        self.assertFalse(called["suggest"])
        self.assertTrue(any("перегружен" in item.lower() for item in response.json()["detail"]))

    def test_law_qa_test_endpoint_returns_text_and_sources(self):
        self._register_verify_and_login("tester", "tester_law@example.com")

        original = complaint_route.ai_service.answer_law_question_details
        original_run_retrieval = complaint_route.run_retrieval
        original_save_answer_citations = complaint_route.save_answer_citations
        original_get_user_id = self.store.get_user_id
        original_create_law_qa_run = self.store.create_law_qa_run
        original_evaluate = complaint_route.FeatureFlagService.evaluate
        original_evaluate = complaint_route.FeatureFlagService.evaluate
        original_resolve_law_article_source = self.store.resolve_law_article_source
        self.store.get_user_id = lambda username: 1
        self.store.create_law_qa_run = lambda **kwargs: 77
        self.store.resolve_law_article_source = lambda **kwargs: {"source_id": 10, "source_version_id": 88}
        complaint_route.run_retrieval = lambda **kwargs: type("RetrievalResult", (), {"retrieval_run_id": 55})()
        complaint_route.save_answer_citations = lambda **kwargs: [
            {
                "id": 1,
                "retrieval_run_id": 55,
                "citation_type": "norm",
                "source_type": "law_article",
                "source_id": 10,
                "source_version_id": 88,
                "canonical_ref": "Кодекс Статья 20",
                "quoted_text": "Фрагмент",
                "usage_type": "supporting",
                "created_at": "2026-04-13T00:00:00+00:00",
            }
        ]
        complaint_route.ai_service.answer_law_question_details = lambda payload: type(
            "LawQaAnswerResult",
            (),
            {
                "text": "Ответ по нормам",
                "generation_id": "gen123",
                "used_sources": ["https://laws.example/base"],
                "indexed_documents": 3,
                "retrieval_confidence": "high",
                "retrieval_profile": "law_qa",
                "guard_status": "pass",
                "contract_version": "legal_pipeline.v1",
                "bundle_status": "fresh",
                "bundle_generated_at": "2026-04-11T12:00:00+00:00",
                "bundle_fingerprint": "abc123",
                "warnings": [],
                "shadow": {"enabled": False, "profile": "", "diverged": False, "overlap_count": 0},
                "telemetry": {
                    "model": "gpt-5.4",
                    "input_tokens": 120,
                    "output_tokens": 40,
                    "total_tokens": 160,
                    "estimated_cost_usd": 0.0009,
                },
                "budget_status": "ok",
                "budget_warnings": [],
                "budget_policy": {"flow": "law_qa"},
                "selected_norms": [
                    {
                        "source_url": "https://laws.example/base",
                        "document_title": "Кодекс",
                        "article_label": "Статья 20",
                        "score": 91,
                        "excerpt_preview": "Фрагмент",
                    }
                ],
            },
        )()
        try:
            response = self.client.post(
                "/api/ai/law-qa-test",
                json={
                    "server_code": "blackberry",
                    "model": "gpt-5.4",
                    "question": "Какая норма регулирует доступ адвоката?",
                    "max_answer_chars": 2000,
                    "law_version_id": 88,
                },
            )
        finally:
            complaint_route.ai_service.answer_law_question_details = original
            complaint_route.run_retrieval = original_run_retrieval
            complaint_route.save_answer_citations = original_save_answer_citations
            self.store.get_user_id = original_get_user_id
            self.store.create_law_qa_run = original_create_law_qa_run
            self.store.resolve_law_article_source = original_resolve_law_article_source

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["text"], "Ответ по нормам")
        self.assertEqual(payload["indexed_documents"], 3)
        self.assertEqual(payload["used_sources"], ["https://laws.example/base"])
        self.assertEqual(payload["retrieval_confidence"], "high")
        self.assertEqual(payload["retrieval_profile"], "law_qa")
        self.assertEqual(payload["selected_norms"][0]["article_label"], "Статья 20")
        self.assertEqual(payload["retrieval_run_id"], 55)
        self.assertEqual(payload["law_qa_run_id"], 77)
        self.assertEqual(len(payload["citations"]), 1)

    def test_law_qa_test_adds_missing_citations_warning_without_mutating_frozen_result(self):
        self._register_verify_and_login("tester", "tester_law_warn@example.com")

        original = complaint_route.ai_service.answer_law_question_details
        original_run_retrieval = complaint_route.run_retrieval
        original_save_answer_citations = complaint_route.save_answer_citations
        original_get_user_id = self.store.get_user_id
        original_create_law_qa_run = self.store.create_law_qa_run
        original_evaluate = complaint_route.FeatureFlagService.evaluate

        from dataclasses import dataclass

        @dataclass(frozen=True)
        class FrozenLawQaResult:
            text: str
            generation_id: str
            used_sources: list[str]
            indexed_documents: int
            retrieval_confidence: str
            retrieval_profile: str
            guard_status: str
            contract_version: str
            bundle_status: str
            bundle_generated_at: str
            bundle_fingerprint: str
            warnings: list[str]
            shadow: dict[str, object]
            selected_norms: list[dict[str, object]]
            telemetry: dict[str, object]
            budget_status: str
            budget_warnings: list[str]
            budget_policy: dict[str, object]
            selected_model: str = ""
            selection_reason: str = ""
            requested_model: str = ""

        self.store.get_user_id = lambda username: 1
        self.store.create_law_qa_run = lambda **kwargs: 77
        complaint_route.run_retrieval = lambda **kwargs: type("RetrievalResult", (), {"retrieval_run_id": 55})()
        complaint_route.save_answer_citations = lambda **kwargs: []
        complaint_route.FeatureFlagService.evaluate = lambda self, flag, context: type(
            "FlagDecision",
            (),
            {
                "use_new_flow": True if flag == "citations_required" else False,
                "enforcement": type("Enforcement", (), {"value": "soft"})(),
                "mode": type("Mode", (), {"value": "all"})(),
                "cohort": type("Cohort", (), {"value": "default"})(),
            },
        )()
        complaint_route.ai_service.answer_law_question_details = lambda payload: FrozenLawQaResult(
            text="Ответ по нормам",
            generation_id="gen123",
            used_sources=["https://laws.example/base"],
            indexed_documents=3,
            retrieval_confidence="high",
            retrieval_profile="law_qa",
            guard_status="pass",
            contract_version="legal_pipeline.v1",
            bundle_status="fresh",
            bundle_generated_at="2026-04-11T12:00:00+00:00",
            bundle_fingerprint="abc123",
            warnings=[],
            shadow={"enabled": False},
            selected_norms=[],
            telemetry={"model": "gpt-5.4"},
            budget_status="ok",
            budget_warnings=[],
            budget_policy={"flow": "law_qa"},
            selected_model="gpt-5.4",
            selection_reason="default",
            requested_model="gpt-5.4",
        )
        try:
            response = self.client.post(
                "/api/ai/law-qa-test",
                json={
                    "server_code": "blackberry",
                    "question": "test question",
                    "max_answer_chars": 2000,
                },
            )
        finally:
            complaint_route.ai_service.answer_law_question_details = original
            complaint_route.run_retrieval = original_run_retrieval
            complaint_route.save_answer_citations = original_save_answer_citations
            self.store.get_user_id = original_get_user_id
            self.store.create_law_qa_run = original_create_law_qa_run
            complaint_route.FeatureFlagService.evaluate = original_evaluate

        self.assertEqual(response.status_code, 200)
        self.assertIn("citations_required_warn:missing_citations", response.json()["warnings"])

    def test_law_qa_test_soft_missing_citations_does_not_call_citation_save(self):
        self._register_verify_and_login("tester", "tester_law_soft@example.com")

        original = complaint_route.ai_service.answer_law_question_details
        original_run_retrieval = complaint_route.run_retrieval
        original_save_answer_citations = complaint_route.save_answer_citations
        original_get_user_id = self.store.get_user_id
        original_create_law_qa_run = self.store.create_law_qa_run
        original_evaluate = complaint_route.FeatureFlagService.evaluate

        self.store.get_user_id = lambda username: 1
        self.store.create_law_qa_run = lambda **kwargs: 77
        complaint_route.run_retrieval = lambda **kwargs: type("RetrievalResult", (), {"retrieval_run_id": 55})()
        complaint_route.save_answer_citations = lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("save_answer_citations should not be called without citations")
        )
        complaint_route.FeatureFlagService.evaluate = lambda self, flag, context: type(
            "FlagDecision",
            (),
            {
                "use_new_flow": True if flag == "citations_required" else False,
                "enforcement": type("Enforcement", (), {"value": "soft"})(),
                "mode": type("Mode", (), {"value": "all"})(),
                "cohort": type("Cohort", (), {"value": "default"})(),
            },
        )()
        complaint_route.ai_service.answer_law_question_details = lambda payload: type(
            "LawQaAnswerResult",
            (),
            {
                "text": "Ответ без привязанных цитат",
                "generation_id": "gen-soft",
                "used_sources": ["https://laws.example/base"],
                "indexed_documents": 1,
                "retrieval_confidence": "medium",
                "retrieval_profile": "law_qa",
                "guard_status": "pass",
                "contract_version": "legal_pipeline.v1",
                "bundle_status": "fresh",
                "bundle_generated_at": "2026-04-11T12:00:00+00:00",
                "bundle_fingerprint": "soft123",
                "warnings": [],
                "shadow": {"enabled": False},
                "selected_norms": [],
                "telemetry": {"model": "gpt-5.4"},
                "budget_status": "ok",
                "budget_warnings": [],
                "budget_policy": {"flow": "law_qa"},
                "selected_model": "gpt-5.4",
                "selection_reason": "default",
                "requested_model": "gpt-5.4",
            },
        )()
        try:
            response = self.client.post(
                "/api/ai/law-qa-test",
                json={
                    "server_code": "blackberry",
                    "question": "test question",
                    "max_answer_chars": 2000,
                },
            )
        finally:
            complaint_route.ai_service.answer_law_question_details = original
            complaint_route.run_retrieval = original_run_retrieval
            complaint_route.save_answer_citations = original_save_answer_citations
            self.store.get_user_id = original_get_user_id
            self.store.create_law_qa_run = original_create_law_qa_run
            complaint_route.FeatureFlagService.evaluate = original_evaluate

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["citations"], [])
        self.assertIn("citations_required_warn:missing_citations", payload["warnings"])


    def test_generate_snapshot_includes_staged_citation_gate(self):
        self._register_verify_and_login("snapshot_gate", "snapshot_gate@example.com")
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
        response = self.client.post(
            "/api/generate",
            json={
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
            },
        )
        self.assertEqual(response.status_code, 200)
        snapshot_response = self.client.get(f"/api/generated-documents/{response.json()['generated_document_id']}/snapshot")
        self.assertEqual(snapshot_response.status_code, 200)
        self.assertEqual(
            snapshot_response.json()["context_snapshot"]["citations_policy_gate"]["status"],
            "flagged_no_citations",
        )

    def test_read_citations_api_uses_store_items(self):
        self._register_verify_and_login("tester", "citations_reader@example.com")
        original_doc = self.store.get_document_version_citations
        original_lawqa = self.store.get_law_qa_run_citations
        self.store.get_document_version_citations = lambda **kwargs: [{
            "id": 1,
            "retrieval_run_id": 2,
            "citation_type": "norm",
            "source_type": "law_article",
            "source_id": 3,
            "source_version_id": 4,
            "canonical_ref": "Ref",
            "quoted_text": "Text",
            "usage_type": "supporting",
            "created_at": "2026-04-13T00:00:00+00:00",
        }]
        self.store.get_law_qa_run_citations = lambda **kwargs: [{
            "id": 5,
            "retrieval_run_id": 6,
            "citation_type": "norm",
            "source_type": "law_article",
            "source_id": 7,
            "source_version_id": 8,
            "canonical_ref": "Ref2",
            "quoted_text": "Text2",
            "usage_type": "supporting",
            "created_at": "2026-04-13T00:00:00+00:00",
        }]
        try:
            response_doc = self.client.get("/api/document-versions/10/citations")
            response_lawqa = self.client.get("/api/law-qa-runs/11/citations")
        finally:
            self.store.get_document_version_citations = original_doc
            self.store.get_law_qa_run_citations = original_lawqa
        self.assertEqual(response_doc.status_code, 200)
        self.assertEqual(response_lawqa.status_code, 200)
        self.assertEqual(response_doc.json()["items"][0]["source_version_id"], 4)
        self.assertEqual(response_lawqa.json()["items"][0]["source_version_id"], 8)

    def test_document_version_provenance_endpoint_returns_trace(self):
        self._register_verify_and_login("tester", "provenance_reader@example.com")
        original_get_target = complaint_route.ValidationRepository.get_document_version_target
        original_get_validation = complaint_route.ValidationService.get_latest_target_validation
        original_get_version = complaint_route.DocumentRepository.get_document_version
        original_get_snapshot = self.store.get_generation_snapshot_by_id
        original_get_citations = self.store.get_document_version_citations

        complaint_route.ValidationRepository.get_document_version_target = lambda _self, version_id: {
            "id": version_id,
            "server_id": "blackberry",
            "document_type": "complaint",
        }
        complaint_route.ValidationService.get_latest_target_validation = lambda _self, **kwargs: {
            "id": 3001,
            "status": "passed",
        }
        complaint_route.DocumentRepository.get_document_version = lambda _self, version_id: {
            "id": version_id,
            "document_id": 10,
            "version_number": 2,
            "generation_snapshot_id": 501,
        }
        self.store.get_generation_snapshot_by_id = lambda snapshot_id: {
            "id": snapshot_id,
            "server_code": "blackberry",
            "document_kind": "complaint",
            "created_at": "2026-04-15T00:00:00+00:00",
            "context_snapshot": {
                "ai": {"provider": "openai", "model": "gpt-5.4"},
                "content_workflow": {"procedure": "complaint_law_index", "template": "complaint_template_v1"},
                "effective_versions": {"law_version_id": 35},
            },
            "effective_config_snapshot": {
                "server_config_version": "blackberry@2026-04-15",
                "law_set_version": "laws@35",
            },
            "content_workflow_ref": {
                "procedure": "complaint_law_index@v2",
                "template": "complaint_template_v1@v3",
                "prompt_version": "complaint_prompt_v4",
            },
        }
        self.store.get_document_version_citations = lambda **kwargs: [
            {"id": 901, "retrieval_run_id": 444, "source_version_id": 35},
            {"id": 902, "retrieval_run_id": 444, "source_version_id": 35},
        ]
        try:
            response = self.client.get("/api/document-versions/77/provenance")
        finally:
            complaint_route.ValidationRepository.get_document_version_target = original_get_target
            complaint_route.ValidationService.get_latest_target_validation = original_get_validation
            complaint_route.DocumentRepository.get_document_version = original_get_version
            self.store.get_generation_snapshot_by_id = original_get_snapshot
            self.store.get_document_version_citations = original_get_citations

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["document_version_id"], 77)
        self.assertEqual(payload["server_id"], "blackberry")
        self.assertEqual(payload["config"]["server_config_version"], "blackberry@2026-04-15")
        self.assertEqual(payload["retrieval"]["citation_ids"], [901, 902])
        self.assertEqual(payload["validation"]["latest_status"], "passed")

    def test_admin_generated_document_provenance_endpoint_bridges_to_latest_version(self):
        self._register_verify_and_login("snapshot_admin_source", "snapshot_admin_source@example.com")

        profile_response = self.client.put(
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
        self.assertEqual(profile_response.status_code, 200)
        generate_response = self.client.post(
            "/api/generate",
            json={
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
            },
        )
        self.assertEqual(generate_response.status_code, 200)
        generated_document_id = int(generate_response.json()["generated_document_id"])

        self.client.post("/api/auth/logout")
        self._register_verify_and_login("12345", "admin_provenance@example.com")

        response = self.client.get(f"/api/admin/generated-documents/{generated_document_id}/provenance")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["document_kind"], "complaint")
        self.assertIsInstance(payload["document_version_id"], int)
        self.assertIsNotNone(payload.get("generation_snapshot_id"))

    def test_admin_recent_generated_documents_endpoint_lists_latest_items(self):
        self._register_verify_and_login("recent_generated_user", "recent_generated_user@example.com")
        profile_response = self.client.put(
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
        self.assertEqual(profile_response.status_code, 200)
        generate_response = self.client.post(
            "/api/generate",
            json={
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
            },
        )
        self.assertEqual(generate_response.status_code, 200)
        generated_document_id = int(generate_response.json()["generated_document_id"])

        self.client.post("/api/auth/logout")
        self._register_verify_and_login("12345", "recent_generated_admin@example.com")

        response = self.client.get("/api/admin/generated-documents/recent?limit=5")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertTrue(any(int(item["id"]) == generated_document_id for item in items))
        match = next(item for item in items if int(item["id"]) == generated_document_id)
        self.assertEqual(match["document_kind"], "complaint")
        self.assertEqual(match["username"], "recent_generated_user")

    def test_admin_generated_document_review_context_returns_snapshot_validation_and_preview(self):
        self._register_verify_and_login("review_context_user", "review_context_user@example.com")
        profile_response = self.client.put(
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
        self.assertEqual(profile_response.status_code, 200)
        generate_response = self.client.post(
            "/api/generate",
            json={
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
            },
        )
        self.assertEqual(generate_response.status_code, 200)
        generated_document_id = int(generate_response.json()["generated_document_id"])

        self.client.post("/api/auth/logout")
        self._register_verify_and_login("12345", "review_context_admin@example.com")

        backend_state = self.store.repository.backend._state
        version_id = max(int(key) for key in backend_state["document_versions"].keys())
        attachment_id = backend_state["next_attachment_id"]
        backend_state["next_attachment_id"] += 1
        backend_state["attachments"][attachment_id] = {
            "id": attachment_id,
            "server_id": "blackberry",
            "uploaded_by": 1,
            "storage_key": "attachments/test.pdf",
            "filename": "test.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 1024,
            "checksum": "abc123",
            "upload_status": "uploaded",
            "metadata_json": {"document_version_id": version_id},
            "created_at": "2026-04-15T00:00:00+00:00",
        }
        backend_state["document_version_attachment_links"][1] = {
            "id": 1,
            "document_version_id": version_id,
            "attachment_id": attachment_id,
            "link_type": "supporting",
            "created_by": 1,
            "created_at": "2026-04-15T00:00:00+00:00",
        }
        export_id = backend_state["next_export_id"]
        backend_state["next_export_id"] += 1
        backend_state["exports"][export_id] = {
            "id": export_id,
            "document_version_id": version_id,
            "server_id": "blackberry",
            "format": "pdf",
            "status": "ready",
            "storage_key": "exports/test.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 4096,
            "checksum": "def456",
            "created_by": 1,
            "job_run_id": None,
            "metadata_json": {"origin": "test"},
            "created_at": "2026-04-15T00:00:00+00:00",
            "updated_at": "2026-04-15T00:00:00+00:00",
        }

        response = self.client.get(f"/api/admin/generated-documents/{generated_document_id}/review-context")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["generated_document"]["id"], generated_document_id)
        self.assertEqual(payload["generated_document"]["document_kind"], "complaint")
        self.assertIsInstance(payload["document_version"]["id"], int)
        self.assertIn("bbcode_preview", payload["document_version"])
        self.assertIn("latest_status", payload["validation_summary"])
        self.assertIsInstance(payload["validation_summary"]["issues"], list)
        self.assertIn("workflow_linkage", payload)
        self.assertEqual(payload["workflow_linkage"]["linkage_mode"], "snapshot_refs_only")
        self.assertIsInstance(payload["snapshot_summary"]["template_version"], str)
        self.assertFalse(payload["snapshot_summary"]["template_version"].startswith("{"))
        self.assertIsInstance(payload["snapshot_summary"]["law_version_set"], str)
        self.assertFalse(payload["snapshot_summary"]["law_version_set"].startswith("{"))
        self.assertIn("citations_summary", payload)
        self.assertIn("count", payload["citations_summary"])
        self.assertIsInstance(payload["citations_summary"]["items"], list)
        self.assertIn("artifact_summary", payload)
        self.assertEqual(payload["artifact_summary"]["exports_count"], 1)
        self.assertEqual(payload["artifact_summary"]["attachments_count"], 1)
        self.assertIn("provenance", payload)

    def test_ai_feedback_endpoint_records_normalized_feedback(self):
        self._register_verify_and_login("tester", "tester_feedback@example.com")

        response = self.client.post(
            "/api/ai/feedback",
            json={
                "generation_id": "gen_feedback_1",
                "flow": "law_qa",
                "issues": ["wronglaw", "fact"],
                "note": "Need a more precise article.",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["generation_id"], "gen_feedback_1")
        self.assertEqual(payload["flow"], "law_qa")
        self.assertEqual(payload["normalized_issues"], ["wrong_law", "wrong_fact"])

    def test_admin_ai_pipeline_endpoint_returns_generations_and_feedback(self):
        self.admin_store.log_ai_generation(
            username="tester",
            server_code="blackberry",
            flow="law_qa",
            generation_id="gen_admin_1",
            path="/api/ai/law-qa-test",
            meta={
                "guard_status": "warn",
                "bundle_status": "fresh",
                "latency_ms": 210,
                "retrieval_ms": 35,
                "openai_ms": 210,
                "total_suggest_ms": 245,
                "validation_errors": ["new_fact_detected", "unsupported_article_reference"],
                "validation_retry_count": 1,
                "safe_fallback_used": True,
            },
        )
        self.admin_store.log_ai_feedback(
            username="tester",
            server_code="blackberry",
            generation_id="gen_admin_1",
            flow="law_qa",
            normalized_issues=["wrong_law"],
            note="Article mismatch",
        )

        self._register_verify_and_login("12345", "admin_pipeline@example.com")
        response = self.client.get("/api/admin/ai-pipeline?flow=law_qa&issue_type=wrong_law")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["flow"], "law_qa")
        self.assertEqual(payload["issue_type"], "wrong_law")
        self.assertIn("summary", payload)
        self.assertIn("quality_summary", payload)
        self.assertIn("cost_tables", payload)
        self.assertIn("top_inaccurate_generations", payload)
        self.assertIn("policy_actions", payload)
        self.assertEqual(payload["summary"]["total_generations"], 1)
        self.assertEqual(payload["summary"]["latency_ms_p50"], 210)
        self.assertEqual(payload["summary"]["retrieval_ms_p50"], 35)
        self.assertEqual(payload["summary"]["openai_ms_p95"], 210)
        self.assertEqual(payload["summary"]["total_suggest_ms_p95"], 245)
        self.assertEqual(payload["quality_summary"]["guard_warn_rate"], 100.0)
        self.assertEqual(payload["quality_summary"]["wrong_law_rate"], 100.0)
        self.assertEqual(payload["quality_summary"]["new_fact_validation_rate"], 100.0)
        self.assertEqual(payload["quality_summary"]["unsupported_article_rate"], 100.0)
        self.assertEqual(payload["quality_summary"]["validation_retry_rate"], 100.0)
        self.assertEqual(payload["quality_summary"]["safe_fallback_rate"], 100.0)
        self.assertEqual(payload["quality_summary"]["bands"]["wrong_law_rate"], "red")
        self.assertEqual(payload["quality_summary"]["wrong_fact_rate"], 0.0)
        self.assertEqual(payload["quality_summary"]["bands"]["wrong_fact_rate"], "green")
        self.assertEqual(payload["quality_summary"]["bands"]["new_fact_validation_rate"], "red")
        self.assertEqual(payload["cost_tables"]["by_flow"][0]["flow"], "law_qa")
        self.assertEqual(payload["top_inaccurate_generations"][0]["generation_id"], "gen_admin_1")
        self.assertTrue(payload["policy_actions"])
        self.assertTrue(any("invented-fact spike" in item["title"].lower() for item in payload["policy_actions"]))
        self.assertTrue(any(item["meta"]["generation_id"] == "gen_admin_1" for item in payload["generations"]))
        self.assertTrue(any(item["meta"]["generation_id"] == "gen_admin_1" for item in payload["feedback"]))

    def test_admin_ai_pipeline_endpoint_handles_invalid_estimated_cost_values(self):
        self.admin_store.log_ai_generation(
            username="tester",
            server_code="blackberry",
            flow="law_qa",
            generation_id="gen_cost_invalid",
            path="/api/ai/law-qa-test",
            meta={
                "model": "gpt-5.4-mini",
                "estimated_cost_usd": "n/a",
                "total_tokens": 120,
            },
        )
        self.admin_store.log_ai_generation(
            username="tester",
            server_code="blackberry",
            flow="law_qa",
            generation_id="gen_cost_string",
            path="/api/ai/law-qa-test",
            meta={
                "model": "gpt-5.4-mini",
                "estimated_cost_usd": "1.25",
                "total_tokens": 240,
            },
        )
        self.admin_store.log_ai_feedback(
            username="tester",
            server_code="blackberry",
            generation_id="gen_cost_invalid",
            flow="law_qa",
            normalized_issues=["wrong_law"],
            note="Bad source",
        )

        self._register_verify_and_login("12345", "admin_pipeline_costs@example.com")
        response = self.client.get("/api/admin/ai-pipeline?flow=law_qa&issue_type=wrong_law")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        by_flow = payload["cost_tables"]["by_flow"][0]
        self.assertEqual(by_flow["flow"], "law_qa")
        self.assertEqual(by_flow["estimated_cost_total_usd"], 1.25)
        self.assertEqual(by_flow["avg_cost_per_request_usd"], 0.625)
        self.assertEqual(payload["top_inaccurate_generations"][0]["generation_id"], "gen_cost_invalid")
        self.assertEqual(payload["top_inaccurate_generations"][0]["estimated_cost_usd"], 0.0)

    def test_admin_ai_pipeline_quality_summary_allows_zero_feedback_samples(self):
        self.admin_store.log_ai_generation(
            username="tester",
            server_code="blackberry",
            flow="law_qa",
            generation_id="gen_feedback_zero_1",
            path="/api/ai/law-qa-test",
            meta={"guard_status": "pass"},
        )

        self._register_verify_and_login("12345", "admin_pipeline_zero_feedback@example.com")
        response = self.client.get("/api/admin/ai-pipeline?flow=law_qa")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        quality_summary = payload["quality_summary"]
        self.assertEqual(quality_summary["generation_samples"], 1)
        self.assertEqual(quality_summary["feedback_samples"], 0)
        self.assertIsNone(quality_summary["wrong_law_rate"])
        self.assertIsNone(quality_summary["hallucination_rate"])
        self.assertFalse(payload.get("partial_errors"))

    def test_safe_float_parsing_cases(self):
        self.assertEqual(admin_ai_pipeline_service.safe_float("12.5"), 12.5)
        with self.assertLogs("ogp_web.services.admin_ai_pipeline_service", level="WARNING") as captured:
            self.assertEqual(admin_ai_pipeline_service.safe_float(None, generation_id="gen_none"), 0.0)
            self.assertEqual(admin_ai_pipeline_service.safe_float("", generation_id="gen_empty"), 0.0)
            self.assertEqual(admin_ai_pipeline_service.safe_float("n/a", generation_id="gen_na"), 0.0)
            self.assertEqual(admin_ai_pipeline_service.safe_float({"bad": "object"}, generation_id="gen_obj"), 0.0)
        self.assertTrue(any("generation_id=gen_none" in item for item in captured.output))
        self.assertTrue(any("generation_id=gen_empty" in item for item in captured.output))
        self.assertTrue(any("generation_id=gen_na" in item for item in captured.output))
        self.assertTrue(any("generation_id=gen_obj" in item for item in captured.output))

    def test_admin_ai_pipeline_quality_summary_does_not_count_cache_as_fallback(self):
        generations = [
            {"meta": {"attempt_path": "cache", "guard_status": "pass"}},
            {"meta": {"attempt_path": "direct_after_proxy", "guard_status": "warn"}},
            {"meta": {"context_compacted": True, "guard_status": "pass"}},
        ]

        payload = admin_ai_pipeline_service.build_ai_pipeline_quality_summary(generations=generations, feedback=[])

        self.assertEqual(payload["generation_samples"], 3)
        self.assertEqual(payload["fallback_rate"], 66.67)
        self.assertEqual(payload["guard_warn_rate"], 33.33)

    def test_admin_ai_pipeline_recent_filter_excludes_old_rows_from_flow_summary(self):
        now = datetime.now(UTC)
        recent_generation = {
            "created_at": (now - timedelta(hours=2)).isoformat(),
            "meta": {
                "model": "gpt-5.4-mini",
                "latency_ms": 100,
                "estimated_cost_usd": "0.02",
                "total_tokens": 100,
            },
        }
        old_generation = {
            "created_at": (now - timedelta(hours=72)).isoformat(),
            "meta": {
                "model": "gpt-5.4",
                "latency_ms": 9999,
                "estimated_cost_usd": "n/a",
                "total_tokens": "bad",
            },
        }

        filtered = admin_ai_pipeline_service.filter_recent_metric_items(
            [recent_generation, old_generation],
            since_hours=24,
        )
        summary = admin_ai_pipeline_service.summarize_generation_rows(filtered)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(summary["total_generations"], 1)
        self.assertEqual(summary["latency_ms_p95"], 100)
        self.assertEqual(summary["estimated_cost_total_usd"], 0.02)

    def test_law_qa_test_page_available_for_tester(self):
        self._register_verify_and_login("tester", "tester_law_page@example.com")
        response = self.client.get("/law-qa-test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("law-server-code", response.text)
        self.assertIn("gpt-5.4-mini", response.text)
        self.assertIn("Ручной выбор отключен", response.text)
        self.assertNotIn("law-model", response.text)
        self.assertNotIn("laws-root-url", response.text)

    def test_law_qa_test_endpoint_forbidden_for_user_without_tester_access(self):
        self._register_verify_and_login("plainlawuser", "plainlawuser@example.com")

        response = self.client.post(
            "/api/ai/law-qa-test",
            json={
                "server_code": "blackberry",
                "model": "gpt-5.4",
                "question": "test question",
                "max_answer_chars": 2000,
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_law_qa_test_endpoint_returns_json_when_unexpected_error_happens(self):
        self._register_verify_and_login("tester", "tester_law_failure@example.com")

        original = complaint_route.ai_service.answer_law_question_details
        complaint_route.ai_service.answer_law_question_details = lambda payload: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            response = self.client.post(
                "/api/ai/law-qa-test",
                json={
                    "server_code": "blackberry",
                    "question": "test question",
                    "max_answer_chars": 2000,
                },
            )
        finally:
            complaint_route.ai_service.answer_law_question_details = original

        self.assertEqual(response.status_code, 502)
        self.assertTrue(str(response.headers.get("content-type", "")).startswith("application/json"))
        self.assertIn("Law QA request failed: RuntimeError.", response.json()["detail"][0])

    def test_generate_rehab_flow_uses_saved_profile(self):
        self._register_verify_and_login("tester", "tester10@example.com")

        response = self.client.put(
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
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/api/generate-rehab",
            json={
                "principal_name": "Victim",
                "principal_passport": "BB",
                "principal_passport_scan_url": "https://example.com/principal",
                "served_seven_days": True,
                "contract_url": "https://example.com/contract",
                "today_date": "08.04.2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        bbcode = response.json()["bbcode"]
        self.assertIn("Rep", bbcode)
        self.assertIn("Victim", bbcode)

    def test_rehab_generation_exposes_admin_review_and_provenance_parity(self):
        self._register_verify_and_login("rehab_review_user", "rehab_review_user@example.com")

        profile_response = self.client.put(
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
        self.assertEqual(profile_response.status_code, 200)

        generate_response = self.client.post(
            "/api/generate-rehab",
            json={
                "principal_name": "Victim",
                "principal_passport": "BB",
                "principal_passport_scan_url": "https://example.com/principal",
                "served_seven_days": True,
                "contract_url": "https://example.com/contract",
                "today_date": "08.04.2026",
            },
        )
        self.assertEqual(generate_response.status_code, 200)
        generated_document_id = int(generate_response.json()["generated_document_id"])

        self.client.post("/api/auth/logout")
        self._register_verify_and_login("12345", "rehab_review_admin@example.com")

        provenance_response = self.client.get(f"/api/admin/generated-documents/{generated_document_id}/provenance")
        self.assertEqual(provenance_response.status_code, 200)
        provenance_payload = provenance_response.json()
        self.assertEqual(provenance_payload["document_kind"], "rehab")
        self.assertIsInstance(provenance_payload["document_version_id"], int)

        review_response = self.client.get(f"/api/admin/generated-documents/{generated_document_id}/review-context")
        self.assertEqual(review_response.status_code, 200)
        review_payload = review_response.json()
        self.assertEqual(review_payload["generated_document"]["document_kind"], "rehab")
        self.assertIsInstance(review_payload["document_version"]["id"], int)
        self.assertIn("latest_status", review_payload["validation_summary"])
        self.assertTrue(str(review_payload["validation_summary"]["latest_status"] or "").strip())
        self.assertIn("provenance", review_payload)
        self.assertEqual(review_payload["provenance"]["document_kind"], "rehab")

    def test_profile_get_returns_saved_data(self):
        self._register_verify_and_login("tester", "tester11@example.com")

        save_response = self.client.put(
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
        self.assertEqual(save_response.status_code, 200)

        get_response = self.client.get("/api/profile")
        self.assertEqual(get_response.status_code, 200)
        payload = get_response.json()["representative"]
        self.assertEqual(payload["name"], "Rep")
        self.assertEqual(payload["phone"], "1234567")

    def test_profile_and_generate_accept_realistic_passport_and_phone_values(self):
        self._register_verify_and_login("tester_realistic", "tester-realistic@example.com")

        profile_response = self.client.put(
            "/api/profile",
            json={
                "name": "Rep",
                "passport": "1111 222222",
                "address": "Addr",
                "phone": "+7 (999) 000-00-00",
                "discord": "disc",
                "passport_scan_url": "https://example.com/rep",
            },
        )
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.json()["representative"]["phone"], "79990000000")

        response = self.client.post(
            "/api/generate",
            json={
                "appeal_no": "1234",
                "org": "LSPD",
                "subject_names": "Officer",
                "situation_description": "Draft body",
                "violation_short": "Short text",
                "event_dt": "08.04.2026 14:30",
                "today_date": "08.04.2026",
                "victim": {
                    "name": "Victim",
                    "passport": "4444 555555",
                    "address": "Addr",
                    "phone": "+7 999 111-22-33",
                    "discord": "victim",
                    "passport_scan_url": "https://example.com/victim",
                },
                "contract_url": "https://example.com/contract",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["bbcode"])

    def test_exam_import_page_imports_new_rows_and_supports_row_scoring(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "tester", "email": "tester7@example.com", "password": "Password123!"},
        )
        verify_url = response.json()["verification_url"]
        self.client.get(f"{urlsplit(verify_url).path}?{urlsplit(verify_url).query}")
        self.client.post("/api/auth/login", json={"username": "tester", "password": "Password123!"})

        page_response = self.client.get("/exam-import-test")
        self.assertEqual(page_response.status_code, 200)

        original_fetch = exam_import_route.fetch_exam_sheet_rows
        original_score = exam_import_route.score_exam_answers_batch_with_proxy_fallback
        original_single_score = exam_import_route.score_exam_answer_with_proxy_fallback
        original_single_score = exam_import_route.score_exam_answer_with_proxy_fallback
        original_single_score = exam_import_route.score_exam_answer_with_proxy_fallback

        def fake_fetch_exam_sheet_rows(force_refresh=False):
            return [
                {
                    "source_row": 2,
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Student One",
                    "discord_tag": "student1",
                    "passport": "111111",
                    "exam_format": "Очно",
                    "payload": {
                        "Отметка времени": "2026-04-08 12:00:00",
                        "Ваше Имя/Фамилия?": "Student One",
                        "Ваш DiscordTag": "student1",
                        "Ваш номер паспорта?": "111111",
                        "Формат экзамена": "Очно",
                        "Вопрос F": "Ответ F",
                        "Вопрос G": "Выберу наибольшую стоимость залога из указанный статей",
                        "Вопрос H": "Залог запрещен",
                    },
                    "answer_count": 3,
                },
                {
                    "source_row": 3,
                    "submitted_at": "2026-04-08 13:00:00",
                    "full_name": "Student Two",
                    "discord_tag": "student2",
                    "passport": "222222",
                    "exam_format": "Дистанционно",
                    "payload": {
                        "Отметка времени": "2026-04-08 13:00:00",
                        "Ваше Имя/Фамилия?": "Student Two",
                        "Ваш DiscordTag": "student2",
                        "Ваш номер паспорта?": "222222",
                        "Формат экзамена": "Дистанционно",
                        "Вопрос F": "Ответ F2",
                        "Вопрос G": "Нужно сложить все суммы залога.",
                        "Вопрос H": "Ответ H2",
                    },
                    "answer_count": 3,
                },
            ]

        exam_import_route.fetch_exam_sheet_rows = fake_fetch_exam_sheet_rows

        def fake_batch_score(**kwargs):
            payload = {
                "F": {"score": 35, "rationale": "Неполный ответ."},
                "G": {"score": 88, "rationale": "Логика в основном совпадает."},
                "H": {"score": 100, "rationale": "Полное совпадение."},
            }
            if kwargs.get("return_stats"):
                return payload, {
                    "answer_count": 3,
                    "heuristic_count": 1,
                    "cache_hit_count": 1,
                    "llm_count": 1,
                    "llm_calls": 1,
                }
            return payload

        exam_import_route.score_exam_answers_batch_with_proxy_fallback = fake_batch_score
        try:
            import_response = self.client.post("/api/exam-import/sync")
            duplicate_import_response = self.client.post("/api/exam-import/sync")
            row_score_response = self.client.post("/api/exam-import/rows/2/score")
            score_response = self.client.post("/api/exam-import/score")
            detail_response = self.client.get("/api/exam-import/rows/2")
        finally:
            exam_import_route.fetch_exam_sheet_rows = original_fetch
            exam_import_route.score_exam_answers_batch_with_proxy_fallback = original_score

        self.assertEqual(import_response.status_code, 200)
        import_payload = import_response.json()
        self.assertEqual(import_payload["inserted_count"], 2)
        self.assertEqual(import_payload["skipped_count"], 0)
        self.assertEqual(import_payload["scored_count"], 0)
        self.assertIsNone(import_payload["latest_entries"][0]["average_score"])

        self.assertEqual(duplicate_import_response.status_code, 200)
        duplicate_payload = duplicate_import_response.json()
        self.assertEqual(duplicate_payload["inserted_count"], 0)
        self.assertEqual(duplicate_payload["skipped_count"], 2)

        self.assertEqual(row_score_response.status_code, 200)
        row_score_payload = row_score_response.json()
        self.assertEqual(row_score_payload["source_row"], 2)
        self.assertEqual(row_score_payload["question_g_score"], 88)
        self.assertIsNotNone(row_score_payload["average_score"])

        self.assertEqual(score_response.status_code, 200)
        score_payload = score_response.json()
        self.assertEqual(score_payload["scored_count"], 1)
        self.assertIsNotNone(score_payload["latest_entries"][0]["average_score"])

        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["source_row"], 2)
        self.assertEqual(detail["question_g_score"], 88)
        self.assertIsNotNone(detail["average_score"])

        overview_response = self.client.get("/api/admin/overview")
        self.assertEqual(overview_response.status_code, 403)

    def test_exam_import_entries_support_pagination(self):
        self._register_verify_and_login("tester", "tester-entries@example.com")
        rows = []
        for source_row in range(2, 27):
            rows.append(
                {
                    "source_row": source_row,
                    "submitted_at": f"2026-04-08 12:{source_row:02d}:00",
                    "full_name": f"Student {source_row}",
                    "discord_tag": f"student{source_row}",
                    "passport": f"{source_row:06d}",
                    "exam_format": "Очно",
                    "payload": {
                        "Ваше Имя/Фамилия?": f"Student {source_row}",
                        "Ваш DiscordTag": f"student{source_row}",
                        "Ваш номер паспорта?": f"{source_row:06d}",
                        "Формат экзамена": "Очно",
                        "Вопрос F": "Ответ F",
                    },
                    "answer_count": 1,
                }
            )
        self.exam_store.import_rows(rows)

        first_page = self.client.get("/api/exam-import/entries?limit=10&offset=0")
        self.assertEqual(first_page.status_code, 200)
        first_payload = first_page.json()
        self.assertEqual(first_payload["total"], 25)
        self.assertEqual(first_payload["limit"], 10)
        self.assertEqual(first_payload["offset"], 0)
        self.assertTrue(first_payload["has_next"])
        self.assertEqual(len(first_payload["items"]), 10)
        self.assertEqual(first_payload["items"][0]["source_row"], 26)

        second_page = self.client.get("/api/exam-import/entries?limit=10&offset=10")
        self.assertEqual(second_page.status_code, 200)
        second_payload = second_page.json()
        self.assertEqual(second_payload["total"], 25)
        self.assertEqual(second_payload["offset"], 10)
        self.assertTrue(second_payload["has_next"])
        self.assertEqual(len(second_payload["items"]), 10)

        last_page = self.client.get("/api/exam-import/entries?limit=10&offset=20")
        self.assertEqual(last_page.status_code, 200)
        last_payload = last_page.json()
        self.assertEqual(last_payload["total"], 25)
        self.assertEqual(last_payload["offset"], 20)
        self.assertFalse(last_payload["has_next"])
        self.assertEqual(len(last_payload["items"]), 5)

    def test_exam_import_background_tasks_support_row_and_bulk_scoring(self):
        self._register_verify_and_login("tester", "tester-task@example.com")
        self.exam_store.import_rows(
            [
                {
                    "source_row": 2,
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Student One",
                    "discord_tag": "student1",
                    "passport": "111111",
                    "exam_format": "Очнo",
                    "payload": {
                        "Отметка времени": "2026-04-08 12:00:00",
                        "Ваше Имя/Фамилия?": "Student One",
                        "Ваш DiscordTag": "student1",
                        "Ваш номер паспорта?": "111111",
                        "Формат экзамена": "Очнo",
                        "Вопрос F": "Ответ F",
                        "Вопрос G": "Ответ G",
                    },
                    "answer_count": 2,
                },
                {
                    "source_row": 3,
                    "submitted_at": "2026-04-08 13:00:00",
                    "full_name": "Student Two",
                    "discord_tag": "student2",
                    "passport": "222222",
                    "exam_format": "Дистанционно",
                    "payload": {
                        "Отметка времени": "2026-04-08 13:00:00",
                        "Ваше Имя/Фамилия?": "Student Two",
                        "Ваш DiscordTag": "student2",
                        "Ваш номер паспорта?": "222222",
                        "Формат экзамена": "Дистанционно",
                        "Вопрос F": "Ответ F2",
                        "Вопрос G": "Ответ G2",
                    },
                    "answer_count": 2,
                },
            ]
        )

        original_score = exam_import_route.score_exam_answers_batch_with_proxy_fallback
        original_single_score = exam_import_route.score_exam_answer_with_proxy_fallback

        def fake_batch_score(**kwargs):
            payload = {
                "F": {"score": 77, "rationale": "Нормально."},
                "G": {"score": 1, "rationale": "Модель не вернула корректную оценку по этому пункту."},
            }
            if kwargs.get("return_stats"):
                return payload, {
                    "answer_count": 2,
                    "heuristic_count": 0,
                    "cache_hit_count": 0,
                    "llm_count": 2,
                    "llm_calls": 1,
                }
            return payload

        def fake_single_score(**kwargs):
            if kwargs["user_answer"] == "Ответ G":
                return {"score": 92, "rationale": "Хорошо."}
            if kwargs["user_answer"] == "Ответ G2":
                return {"score": 89, "rationale": "Исправлено повторной проверкой."}
            return {"score": 50, "rationale": "Fallback."}

        exam_import_route.score_exam_answers_batch_with_proxy_fallback = fake_batch_score
        exam_import_route.score_exam_answer_with_proxy_fallback = fake_single_score
        try:
            row_task = self.client.post("/api/exam-import/rows/2/score/tasks")
            self.assertEqual(row_task.status_code, 200)
            row_task_id = row_task.json()["task_id"]

            row_result = None
            for _ in range(20):
                poll = self.client.get(f"/api/exam-import/tasks/{row_task_id}")
                self.assertEqual(poll.status_code, 200)
                row_result = poll.json()
                if row_result["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.05)
            self.assertIsNotNone(row_result)
            self.assertEqual(row_result["status"], "completed")
            self.assertEqual(row_result["raw_status"], "completed")
            self.assertEqual(row_result["canonical_status"], "succeeded")
            self.assertEqual(row_result["result"]["source_row"], 2)
            self.assertEqual(row_result["result"]["question_g_score"], 92)
            self.assertEqual(len(row_result["result"]["failed_fields"]), 2)
            self.assertEqual(row_result["result"]["failed_fields"][0]["column"], "F")
            self.assertEqual(row_result["result"]["failed_fields"][1]["column"], "G")
            self.assertEqual(row_result["result"]["failed_fields"][1]["score"], 92)

            bulk_task = self.client.post("/api/exam-import/score/tasks")
            self.assertEqual(bulk_task.status_code, 200)
            bulk_task_id = bulk_task.json()["task_id"]

            bulk_result = None
            for _ in range(20):
                poll = self.client.get(f"/api/exam-import/tasks/{bulk_task_id}")
                self.assertEqual(poll.status_code, 200)
                bulk_result = poll.json()
                if bulk_result["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.05)
            self.assertIsNotNone(bulk_result)
            self.assertEqual(bulk_result["status"], "completed")
            self.assertEqual(bulk_result["raw_status"], "completed")
            self.assertEqual(bulk_result["canonical_status"], "succeeded")
            self.assertEqual(bulk_result["result"]["scored_count"], 1)
            self.assertEqual(len(bulk_result["result"]["latest_entries"]), 2)
            self.assertEqual(bulk_result["result"]["failed_field_count"], 4)
            self.assertEqual(len(bulk_result["result"]["failed_rows"]), 2)
            g_scores = sorted(row["failed_fields"][1]["score"] for row in bulk_result["result"]["failed_rows"])
            self.assertEqual(g_scores, [89, 92])
        finally:
            exam_import_route.score_exam_answers_batch_with_proxy_fallback = original_score
            exam_import_route.score_exam_answer_with_proxy_fallback = original_single_score

    def test_exam_import_can_clear_all_scores_for_row(self):
        self._register_verify_and_login("tester", "tester-clear-scores@example.com")
        self.exam_store.import_rows(
            [
                {
                    "source_row": 2,
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Student One",
                    "discord_tag": "student1",
                    "passport": "111111",
                    "exam_format": "Очнo",
                    "payload": {
                        "Вопрос F": "Ответ F",
                        "Вопрос G": "Ответ G",
                    },
                    "answer_count": 2,
                },
            ]
        )
        self.exam_store.save_exam_scores(
            2,
            [
                {
                    "column": "F",
                    "header": "Вопрос F",
                    "user_answer": "Ответ F",
                    "correct_answer": "Эталон F",
                    "score": 60,
                    "rationale": "ok",
                },
                {
                    "column": "G",
                    "header": "Вопрос G",
                    "user_answer": "Ответ G",
                    "correct_answer": "Эталон G",
                    "score": 90,
                    "rationale": "ok",
                },
            ],
        )

        response = self.client.delete("/api/exam-import/rows/2/scores")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_row"], 2)
        self.assertEqual(payload["exam_scores"], [])
        self.assertIsNone(payload["average_score"])

    def test_exam_import_task_concurrency_limit_is_enforced(self):
        self._register_verify_and_login("tester", "tester13@example.com")
        self.exam_store.import_rows(
            [
                {
                    "source_row": 2,
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Student One",
                    "discord_tag": "student1",
                    "passport": "111111",
                    "exam_format": "РћС‡РЅo",
                    "payload": {"Р’РѕРїСЂРѕСЃ F": "РћС‚РІРµС‚ F", "Р’РѕРїСЂРѕСЃ G": "РћС‚РІРµС‚ G"},
                    "answer_count": 2,
                },
            ]
        )

        original_bulk_score = exam_import_route._build_bulk_scoring_result
        block = threading.Event()
        resume = threading.Event()
        task_registry = self.client.app.state.exam_import_task_registry
        original_limit = task_registry.max_concurrent_tasks
        task_registry.max_concurrent_tasks = 1

        def slow_bulk_score(*, user, store, metrics_store, progress_callback=None):
            block.set()
            progress_callback({"state": "running"})
            resume.wait(timeout=2.0)
            return {
                "sheet_url": "https://example.com",
                "total_rows": 1,
                "inserted_count": 0,
                "updated_count": 0,
                "skipped_count": 0,
                "scored_count": 0,
                "latest_entries": [],
            }

        exam_import_route._build_bulk_scoring_result = slow_bulk_score
        try:
            first = self.client.post("/api/exam-import/score/tasks")
            self.assertEqual(first.status_code, 200)
            first_task_id = first.json()["task_id"]

            task_status = {}
            for _ in range(40):
                poll = self.client.get(f"/api/exam-import/tasks/{first_task_id}")
                self.assertEqual(poll.status_code, 200)
                task_status = poll.json()
                if task_status.get("status") == "running":
                    break
                time.sleep(0.05)
            self.assertEqual(task_status.get("status"), "running")
            self.assertTrue(block.wait(1.0))

            second = self.client.post("/api/exam-import/score/tasks")
            self.assertEqual(second.status_code, 429)
            self.assertTrue(second.json().get("detail"))
        finally:
            resume.set()
            time.sleep(0.05)
            exam_import_route._build_bulk_scoring_result = original_bulk_score
            task_registry.max_concurrent_tasks = original_limit

    def test_exam_import_task_registry_persists_and_marks_interrupted_tasks(self):
        local_tmpdir = make_temporary_directory()
        try:
            db_path = Path(local_tmpdir.name) / "exam_import_tasks.db"
            backend = FakeExamImportTasksPostgresBackend()
            registry = ExamImportTaskRegistry(db_path, backend=backend)
            task = registry.create_task(task_type="bulk_score", runner=lambda: {"ok": True})

            record = None
            for _ in range(20):
                record = registry.get_task(task.id)
                if record and record.status == "completed":
                    break
                time.sleep(0.05)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, "completed")
            self.assertEqual(record.result, {"ok": True})

            backend._state["rows"]["interrupted-task"] = {
                "id": "interrupted-task",
                "task_type": "row_score",
                "source_row": 14,
                "status": "running",
                "created_at": "2026-04-09T10:00:00+00:00",
                "started_at": "2026-04-09T10:00:01+00:00",
                "finished_at": "",
                "error": "",
                "progress_json": {},
                "result_json": {},
            }

            reopened = ExamImportTaskRegistry(db_path, backend=backend)
            interrupted = reopened.get_task("interrupted-task")
            self.assertIsNotNone(interrupted)
            self.assertEqual(interrupted.status, "failed")
            self.assertIn("перезапущен", interrupted.error.lower())
            del registry
            del reopened
        finally:
            local_tmpdir.cleanup()

    def test_exam_import_background_task_returns_readable_error_details(self):
        self._register_verify_and_login("tester", "tester-task-error@example.com")
        self.exam_store.import_rows(
            [
                {
                    "source_row": 2,
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Student One",
                    "discord_tag": "student1",
                    "passport": "111111",
                    "exam_format": "РћС‡РЅo",
                    "payload": {
                        "Р’РѕРїСЂРѕСЃ F": "РћС‚РІРµС‚ F",
                        "Р’РѕРїСЂРѕСЃ G": "РћС‚РІРµС‚ G",
                    },
                    "answer_count": 2,
                }
            ]
        )

        original_bulk_score = exam_import_route._build_bulk_scoring_result

        def failing_bulk_score(*, user, store, metrics_store, progress_callback=None):
            _ = (user, store, metrics_store, progress_callback)
            raise RuntimeError("Проверка ответов превысила время ожидания. Строка импорта: 2")

        exam_import_route._build_bulk_scoring_result = failing_bulk_score
        try:
            task_response = self.client.post("/api/exam-import/score/tasks")
            self.assertEqual(task_response.status_code, 200)
            task_id = task_response.json()["task_id"]

            final_status = None
            for _ in range(20):
                poll = self.client.get(f"/api/exam-import/tasks/{task_id}")
                self.assertEqual(poll.status_code, 200)
                final_status = poll.json()
                if final_status["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.05)

            self.assertIsNotNone(final_status)
            self.assertEqual(final_status["status"], "failed")
            self.assertIn("Строка импорта: 2", final_status["error"])
            self.assertIn("время ожидания", final_status["error"])
        finally:
            exam_import_route._build_bulk_scoring_result = original_bulk_score

    def test_exam_import_score_returns_readable_error_when_batch_fails(self):
        self._register_verify_and_login("tester", "tester12@example.com")
        self.exam_store.import_rows(
            [
                {
                    "source_row": 2,
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Student One",
                    "discord_tag": "student1",
                    "passport": "111111",
                    "exam_format": "Очнo",
                    "payload": {
                        "Вопрос F": "Ответ F",
                        "Вопрос G": "Ответ G",
                    },
                    "answer_count": 2,
                }
            ]
        )

        original_score_if_needed = exam_import_route._score_exam_answers_if_needed

        def fake_score_exam_answers_if_needed(store, entry):
            _ = (store, entry)
            raise RuntimeError("network timeout while scoring")

        exam_import_route._score_exam_answers_if_needed = fake_score_exam_answers_if_needed
        try:
            response = self.client.post("/api/exam-import/score")
        finally:
            exam_import_route._score_exam_answers_if_needed = original_score_if_needed

        self.assertEqual(response.status_code, 502)
        details = response.json()["detail"]
        self.assertTrue(any("время ожидания" in item.lower() for item in details))
        self.assertTrue(any("Строка импорта: 2" in item for item in details))


    def test_rate_limit_blocks_excessive_login_attempts(self):
        # 10 allowed, 11th must be 429
        for _ in range(10):
            self.client.post("/api/auth/login", json={"username": "x", "password": "y"})
        response = self.client.post("/api/auth/login", json={"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 429)
        self.assertTrue(any("300" in item or "слишком много" in item.lower() for item in response.json()["detail"]))

    def test_csrf_origin_check_blocks_unknown_origin(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "x", "password": "y"},
            headers={"origin": "https://evil.example.com"},
        )
        self.assertEqual(response.status_code, 403)

    def test_csrf_origin_check_allows_no_origin(self):
        # Direct API calls without Origin header must not be blocked
        response = self.client.post("/api/auth/login", json={"username": "x", "password": "y"})
        self.assertNotEqual(response.status_code, 403)

    def test_user_store_validate_columns_rejects_unknown(self):
        from ogp_web.storage.user_store import _validate_columns
        with self.assertRaises(ValueError):
            _validate_columns("username; DROP TABLE users--")
        with self.assertRaises(ValueError):
            _validate_columns("nonexistent_col")
        # Valid cases must not raise
        self.assertEqual(_validate_columns("*"), "*")
        self.assertEqual(_validate_columns("username, email"), "username, email")

if __name__ == "__main__":
    unittest.main()
