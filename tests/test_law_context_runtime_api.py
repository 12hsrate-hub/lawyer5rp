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
from ogp_web.routes import complaint as complaint_route
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_repository import UserRepository
from ogp_web.storage.user_store import UserStore
from tests.second_server_fixtures import blackberry_published_pack
from tests.temp_helpers import make_temporary_directory
from tests.test_web_storage import (
    FakeAdminMetricsPostgresBackend,
    FakeExamAnswersPostgresBackend,
    FakeExamImportTasksPostgresBackend,
    PostgresBackend,
)


class _FakeReadiness:
    def __init__(self, payload):
        self.payload = dict(payload)
        self.is_ready = bool(payload.get("is_ready"))
        self.reason_code = str(payload.get("reason_code") or "")
        self.reason_detail = str(payload.get("reason_detail") or "")

    def to_payload(self):
        return dict(self.payload)


class _FakeReadinessService:
    def __init__(self, payload):
        self.payload = dict(payload)

    def get_readiness(self, *, server_code: str, requested_law_version_id=None):
        _ = (server_code, requested_law_version_id)
        return _FakeReadiness(self.payload)


class LawContextRuntimeApiTests(unittest.TestCase):
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
        login_response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(login_response.status_code, 200)

    def test_law_qa_submit_fails_closed_when_law_context_is_not_ready(self):
        self._register_verify_and_login("tester", "tester-law-blocked@example.com")

        original_builder = complaint_route.build_law_context_readiness_service
        original_ai = complaint_route.ai_service.answer_law_question_details
        complaint_route.build_law_context_readiness_service = lambda **kwargs: _FakeReadinessService(
            {
                "is_ready": False,
                "reason_code": "runtime_drift",
                "reason_detail": "Projection bridge does not match the active runtime version.",
            }
        )
        complaint_route.ai_service.answer_law_question_details = lambda payload: (_ for _ in ()).throw(
            AssertionError("AI call must not happen when law context is blocked")
        )
        try:
            with patch(
                "ogp_web.server_config.registry._load_effective_pack_from_db",
                side_effect=lambda *, server_code, at_timestamp=None: blackberry_published_pack() if server_code == "blackberry" else None,
            ):
                response = self.client.post(
                    "/api/ai/law-qa-test",
                    json={
                        "server_code": "blackberry",
                        "question": "test question",
                        "max_answer_chars": 2000,
                    },
                )
        finally:
            complaint_route.build_law_context_readiness_service = original_builder
            complaint_route.ai_service.answer_law_question_details = original_ai

        self.assertEqual(response.status_code, 409)
        self.assertIn("runtime_drift", " ".join(response.json()["detail"]))


if __name__ == "__main__":
    unittest.main()
