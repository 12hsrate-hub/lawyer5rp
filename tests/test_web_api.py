from __future__ import annotations

import os
import sqlite3
import threading
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_WEB_SECRET", "test-secret")
os.environ.setdefault("OGP_DB_BACKEND", "sqlite")

from fastapi.testclient import TestClient

from ogp_web.app import create_app
from ogp_web.db.backends.sqlite import SQLiteBackend
from ogp_web.storage.user_repository import UserRepository
from ogp_web.rate_limit import reset_for_testing as reset_rate_limit
from ogp_web.routes import complaint as complaint_route
from ogp_web.routes import exam_import as exam_import_route
from ogp_web.services import ai_service
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_store import UserStore
from tests.temp_helpers import make_temporary_directory


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = make_temporary_directory()
        root = Path(self.tmpdir.name)
        self.prev_test_users = os.environ.get("OGP_WEB_TEST_USERS")
        os.environ["OGP_WEB_TEST_USERS"] = "tester"
        self.store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(SQLiteBackend(root / "app.db")),
        )
        self.exam_store = ExamAnswersStore(root / "exam_answers.db", backend=SQLiteBackend(root / "exam_answers.db"))
        self.admin_store = AdminMetricsStore(root / "admin_metrics.db", backend=SQLiteBackend(root / "admin_metrics.db"))
        self.client = TestClient(create_app(self.store, self.exam_store, self.admin_store), base_url="https://testserver")
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

    def test_admin_overview_forbidden_for_non_admin(self):
        self._register_verify_and_login("tester", "tester@example.com")
        response = self.client.get("/api/admin/overview")
        self.assertEqual(response.status_code, 403)

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
                return {"backend": "sqlite", "ok": False, "error": "forced_failure"}

            def log_event(self, *args, **kwargs) -> bool:
                return False

        client = TestClient(create_app(self.store, self.exam_store, UnhealthyAdminMetricsStore()), base_url="https://testserver")
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
        self.assertEqual(response.json()["draft"]["org"], "GOV")

        response = self.client.get("/api/complaint-draft")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["draft"]["subject_names"], "Pavel Clayton")
        self.assertTrue(response.json()["updated_at"])

        response = self.client.delete("/api/complaint-draft")
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/complaint-draft")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["draft"], {})

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

    def test_blocked_user_cannot_use_existing_session(self):
        self._register_verify_and_login("sessionuser", "sessionuser@example.com")
        session_client = self.client

        admin_client = TestClient(create_app(self.store, self.exam_store, self.admin_store), base_url="https://testserver")
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

    def test_generate_flow_survives_admin_metrics_write_failure(self):
        tmp_path = Path(self.tmpdir.name)

        class BrokenAdminMetricsStore(AdminMetricsStore):
            def __init__(self):
                self.db_path = tmp_path / "broken_admin_metrics.db"

            def _connect(self):
                raise sqlite3.OperationalError("attempt to write a readonly database")

        broken_admin_store = BrokenAdminMetricsStore()
        client = TestClient(create_app(self.store, self.exam_store, broken_admin_store), base_url="https://testserver")
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

        original_suggest = ai_service.suggest_description_with_proxy_fallback
        ai_service.suggest_description_with_proxy_fallback = lambda **kwargs: "AI text"
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
            ai_service.suggest_description_with_proxy_fallback = original_suggest

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "AI text")

    def test_law_qa_test_endpoint_returns_text_and_sources(self):
        self._register_verify_and_login("tester", "tester_law@example.com")

        original = complaint_route.answer_law_question
        complaint_route.answer_law_question = lambda payload: ("Ответ по нормам", ["https://laws.example/base"], 3)
        try:
            response = self.client.post(
                "/api/ai/law-qa-test",
                json={
                    "laws_root_url": "https://laws.example/base",
                    "question": "Какая норма регулирует доступ адвоката?",
                    "max_answer_chars": 2000,
                },
            )
        finally:
            complaint_route.answer_law_question = original

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["text"], "Ответ по нормам")
        self.assertEqual(payload["indexed_documents"], 3)
        self.assertEqual(payload["used_sources"], ["https://laws.example/base"])

    def test_law_qa_test_page_available_for_tester(self):
        self._register_verify_and_login("tester", "tester_law_page@example.com")
        response = self.client.get("/law-qa-test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Q&A по законодательной базе", response.text)

    def test_law_qa_test_endpoint_forbidden_for_user_without_tester_access(self):
        self._register_verify_and_login("plainlawuser", "plainlawuser@example.com")

        response = self.client.post(
            "/api/ai/law-qa-test",
            json={
                "laws_root_url": "https://laws.example/base",
                "question": "test question",
                "max_answer_chars": 2000,
            },
        )

        self.assertEqual(response.status_code, 403)

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
            self.assertEqual(bulk_result["result"]["scored_count"], 1)
            self.assertEqual(len(bulk_result["result"]["latest_entries"]), 2)
            self.assertEqual(bulk_result["result"]["failed_field_count"], 4)
            self.assertEqual(len(bulk_result["result"]["failed_rows"]), 2)
            g_scores = sorted(row["failed_fields"][1]["score"] for row in bulk_result["result"]["failed_rows"])
            self.assertEqual(g_scores, [89, 92])
        finally:
            exam_import_route.score_exam_answers_batch_with_proxy_fallback = original_score
            exam_import_route.score_exam_answer_with_proxy_fallback = original_single_score

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
            registry = ExamImportTaskRegistry(db_path, backend=SQLiteBackend(db_path))
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

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO exam_import_tasks (
                        id, task_type, source_row, status, created_at, started_at, finished_at, error, result_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "interrupted-task",
                        "row_score",
                        14,
                        "running",
                        "2026-04-09T10:00:00+00:00",
                        "2026-04-09T10:00:01+00:00",
                        "",
                        "",
                        "",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            reopened = ExamImportTaskRegistry(db_path, backend=SQLiteBackend(db_path))
            interrupted = reopened.get_task("interrupted-task")
            self.assertIsNotNone(interrupted)
            self.assertEqual(interrupted.status, "failed")
            self.assertIn("перезапущен", interrupted.error.lower())
            del registry
            del reopened
        finally:
            local_tmpdir.cleanup()

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
