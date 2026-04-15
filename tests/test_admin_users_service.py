from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_WEB_SECRET", "test-secret")
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
os.environ.setdefault("OGP_SKIP_DEFAULT_APP_INIT", "1")

from fastapi import HTTPException

from ogp_web.services.admin_users_service import (
    build_admin_role_history_payload,
    build_admin_user_details_payload,
    build_admin_users_csv_content,
    build_admin_users_payload,
    normalize_optional_positive_int,
)


class _FakeUserStore:
    def list_users(self, *, limit: int | None = None):
        users = [
            {"username": "alice", "email": "alice@example.com", "created_at": "2026-01-01", "server_code": "blackberry"},
            {"username": "bob", "email": "bob@example.com", "created_at": "2026-01-02", "server_code": "blackberry"},
        ]
        return users[:limit] if limit else users

    def get_permission_codes(self, username: str, *, server_code: str | None = None):
        if username == "alice":
            return frozenset({"manage_servers", "manage_laws", "view_analytics"})
        return frozenset({"exam_import"})


class _FakeMetricsStore:
    def get_overview(self, *, users, search: str = "", blocked_only: bool = False, tester_only: bool = False, gka_only: bool = False, unverified_only: bool = False, user_sort: str = "complaints", **kwargs):
        filtered = users
        if search:
            filtered = [item for item in users if search in str(item.get("username", "")).lower()]
        enriched = []
        for item in filtered:
            enriched.append(
                {
                    **item,
                    "api_requests": 3,
                    "failed_api_requests": 1,
                    "complaints": 2,
                    "rehabs": 1,
                    "ai_suggestions": 4,
                    "ai_ocr_requests": 0,
                    "resource_units": 9,
                    "risk_score": 1,
                    "risk_flags": ["flag-a"],
                }
            )
        return {
            "users": enriched,
            "recent_events": [
                {"username": "alice", "event_type": "admin_grant_tester", "status_code": 200, "meta": {"target_username": "alice"}},
                {"username": "alice", "event_type": "api_request", "status_code": 500, "meta": {}},
                {"username": "bob", "event_type": "admin_revoke_gka", "status_code": 200, "meta": {"target_username": "bob"}},
            ],
        }

    def export_users_csv(self, *, users, **kwargs):
        return "username,email,created_at\n" + "\n".join(f"{item['username']},{item['email']},{item['created_at']}" for item in users)


class AdminUsersServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user_store = _FakeUserStore()
        self.metrics_store = _FakeMetricsStore()

    def test_build_admin_users_payload_paginates(self):
        payload = build_admin_users_payload(
            metrics_store=self.metrics_store,
            user_store=self.user_store,
            user_sort="username",
            limit=1,
            offset=1,
        )
        self.assertEqual(payload["total"], 2)
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["username"], "bob")

    def test_build_admin_user_details_payload(self):
        payload = build_admin_user_details_payload(
            metrics_store=self.metrics_store,
            user_store=self.user_store,
            username="alice",
        )
        self.assertEqual(payload["user"]["username"], "alice")
        self.assertTrue(payload["effective_permissions"]["manage_servers"])
        self.assertEqual(payload["activity_snapshot"]["recent_errors_count"], 1)

        with self.assertRaises(HTTPException) as exc:
            build_admin_user_details_payload(
                metrics_store=self.metrics_store,
                user_store=self.user_store,
                username="missing",
            )
        self.assertEqual(exc.exception.status_code, 404)

    def test_build_admin_role_history_and_csv(self):
        history = build_admin_role_history_payload(
            metrics_store=self.metrics_store,
            user_store=self.user_store,
            limit=10,
        )
        csv_content = build_admin_users_csv_content(
            metrics_store=self.metrics_store,
            user_store=self.user_store,
            users_limit="1",
            user_sort="username",
        )
        self.assertEqual(history["total"], 2)
        self.assertIn("username,email,created_at", csv_content)
        self.assertIn("alice,alice@example.com,2026-01-01", csv_content)

    def test_normalize_optional_positive_int(self):
        self.assertEqual(normalize_optional_positive_int("5"), 5)
        self.assertIsNone(normalize_optional_positive_int("0"))
        self.assertIsNone(normalize_optional_positive_int("bad"))


if __name__ == "__main__":
    unittest.main()
