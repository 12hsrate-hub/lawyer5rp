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
os.environ.setdefault("OGP_DB_BACKEND", "sqlite")

from fastapi.testclient import TestClient

from ogp_web.app import create_app
from ogp_web.db.backends.sqlite import SQLiteBackend
from ogp_web.rate_limit import reset_for_testing as reset_rate_limit
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_repository import UserRepository
from ogp_web.storage.user_store import UserStore
from tests.temp_helpers import make_temporary_directory


class WebPagesSmokeTests(unittest.TestCase):
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

    def test_login_redirects_authenticated_user(self):
        response = self.client.get("/login", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/complaint")

    def test_admin_page_requires_admin_user(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 403)

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
