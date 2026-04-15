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

from ogp_web.services.admin_user_mutations_service import execute_bulk_user_mutation_action
from ogp_web.services.auth_service import AuthUser


class _FakeUserStore:
    def admin_mark_email_verified(self, username: str):
        return {"username": username}

    def admin_set_access_blocked(self, username: str, reason: str = ""):
        return {"username": username, "reason": reason}

    def admin_clear_access_blocked(self, username: str):
        return {"username": username}

    def admin_set_tester_status(self, username: str, is_tester: bool):
        return {"username": username, "is_tester": is_tester}

    def admin_set_gka_status(self, username: str, is_gka: bool):
        return {"username": username, "is_gka": is_gka}

    def admin_deactivate_user(self, username: str, reason: str = ""):
        return {"username": username, "reason": reason}

    def admin_reactivate_user(self, username: str):
        return {"username": username}

    def admin_set_daily_quota(self, username: str, daily_limit: int):
        return {"username": username, "api_quota_daily": daily_limit}


class _FakeMetricsStore:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def log_event(self, **kwargs):
        self.events.append(kwargs)


class _Payload:
    def __init__(self, **kwargs):
        self.usernames = kwargs.get("usernames", [])
        self.action = kwargs.get("action", "")
        self.reason = kwargs.get("reason", "")
        self.daily_limit = kwargs.get("daily_limit")


class AdminBulkUserMutationsServiceTests(unittest.TestCase):
    def test_execute_bulk_user_mutation_action_logs_events_and_progress(self):
        metrics = _FakeMetricsStore()
        progress: list[tuple[int, int]] = []
        result = execute_bulk_user_mutation_action(
            payload=_Payload(usernames=["alice", "bob"], action="grant_tester"),
            user=AuthUser(username="admin", email="admin@example.com", server_code="blackberry"),
            metrics_store=metrics,
            user_store=_FakeUserStore(),
            progress_callback=lambda done, total: progress.append((done, total)),
        )

        self.assertEqual(result["success_count"], 2)
        self.assertEqual(len(metrics.events), 2)
        self.assertEqual(progress, [(1, 2), (2, 2)])

    def test_execute_bulk_user_mutation_action_requires_daily_limit(self):
        with self.assertRaises(Exception):
            execute_bulk_user_mutation_action(
                payload=_Payload(usernames=["alice"], action="set_daily_quota"),
                user=AuthUser(username="admin", email="admin@example.com", server_code="blackberry"),
                metrics_store=_FakeMetricsStore(),
                user_store=_FakeUserStore(),
            )


if __name__ == "__main__":
    unittest.main()
