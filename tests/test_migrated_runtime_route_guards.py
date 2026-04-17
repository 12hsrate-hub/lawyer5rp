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

from fastapi import HTTPException
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


class MigratedRuntimeRouteGuardsTests(unittest.TestCase):
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
        self._register_verify_and_login("tester", "tester@example.com")

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

    def test_generate_route_uses_runtime_requirement_guard(self):
        with patch(
            "ogp_web.routes.complaint.ensure_section_runtime_requirement",
            side_effect=HTTPException(status_code=409, detail=["Published runtime requirement failed."]),
        ):
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

        self.assertEqual(response.status_code, 409)

    def test_document_builder_bundle_route_uses_runtime_requirement_guard(self):
        with patch(
            "ogp_web.routes.document_builder.ensure_section_runtime_requirement",
            side_effect=HTTPException(status_code=409, detail=["Published runtime requirement failed."]),
        ):
            response = self.client.get(
                "/api/document-builder/bundle",
                params={"server_id": "blackberry", "document_type": "court_claim"},
            )

        self.assertEqual(response.status_code, 409)

    def test_law_qa_route_uses_runtime_requirement_guard(self):
        with patch(
            "ogp_web.routes.complaint.ensure_section_runtime_requirement",
            side_effect=HTTPException(status_code=409, detail=["Published runtime requirement failed."]),
        ):
            response = self.client.post(
                "/api/ai/law-qa-test",
                json={"question": "Какая норма применяется?", "server_code": "blackberry"},
            )

        self.assertEqual(response.status_code, 409)

    def test_law_qa_page_uses_runtime_requirement_guard(self):
        with patch(
            "ogp_web.routes.pages.ensure_section_runtime_requirement",
            side_effect=HTTPException(status_code=409, detail=["Published runtime requirement failed."]),
        ):
            response = self.client.get("/law-qa-test")

        self.assertEqual(response.status_code, 409)

    def test_court_claim_page_uses_runtime_requirement_guard(self):
        with patch(
            "ogp_web.routes.pages.ensure_section_runtime_requirement",
            side_effect=HTTPException(status_code=409, detail=["Published runtime requirement failed."]),
        ):
            response = self.client.get("/court-claim-test")

        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
