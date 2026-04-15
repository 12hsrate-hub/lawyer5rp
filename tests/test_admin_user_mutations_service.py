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

from ogp_web.services.admin_user_mutations_service import (
    block_admin_user_payload,
    deactivate_admin_user_payload,
    grant_gka_payload,
    grant_tester_payload,
    reactivate_admin_user_payload,
    reset_admin_user_password_payload,
    revoke_gka_payload,
    revoke_tester_payload,
    run_admin_user_mutation,
    set_admin_user_daily_quota_payload,
    unblock_admin_user_payload,
    update_admin_user_email_payload,
    verify_admin_user_email_payload,
)
from ogp_web.services.auth_service import AuthError


class _FakeUserStore:
    def admin_mark_email_verified(self, username: str):
        return {"username": username, "email_verified_at": "now"}

    def admin_set_access_blocked(self, username: str, reason: str = ""):
        return {"username": username, "access_blocked_reason": reason}

    def admin_clear_access_blocked(self, username: str):
        return {"username": username, "access_blocked_reason": None}

    def admin_set_tester_status(self, username: str, is_tester: bool):
        return {"username": username, "is_tester": is_tester}

    def admin_set_gka_status(self, username: str, is_gka: bool):
        return {"username": username, "is_gka": is_gka}

    def admin_update_email(self, username: str, email: str):
        return {"username": username, "email": email}

    def admin_reset_password(self, username: str, new_password: str):
        return {"username": username, "password_reset": True}

    def admin_deactivate_user(self, username: str, reason: str = ""):
        return {"username": username, "deactivated_reason": reason}

    def admin_reactivate_user(self, username: str):
        return {"username": username, "deactivated_reason": None}

    def admin_set_daily_quota(self, username: str, daily_limit: int):
        return {"username": username, "api_quota_daily": daily_limit}


class AdminUserMutationsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _FakeUserStore()

    def test_payload_builders_return_uniform_ok_shape(self):
        self.assertTrue(verify_admin_user_email_payload(user_store=self.store, username="alice")["ok"])
        self.assertEqual(block_admin_user_payload(user_store=self.store, username="alice", reason="test")["user"]["access_blocked_reason"], "test")
        self.assertFalse(unblock_admin_user_payload(user_store=self.store, username="alice")["user"]["access_blocked_reason"])
        self.assertTrue(grant_tester_payload(user_store=self.store, username="alice")["user"]["is_tester"])
        self.assertFalse(revoke_tester_payload(user_store=self.store, username="alice")["user"]["is_tester"])
        self.assertTrue(grant_gka_payload(user_store=self.store, username="alice")["user"]["is_gka"])
        self.assertFalse(revoke_gka_payload(user_store=self.store, username="alice")["user"]["is_gka"])
        self.assertEqual(update_admin_user_email_payload(user_store=self.store, username="alice", email="a@example.com")["user"]["email"], "a@example.com")
        self.assertTrue(reset_admin_user_password_payload(user_store=self.store, username="alice", password="Secret123!")["user"]["password_reset"])
        self.assertEqual(deactivate_admin_user_payload(user_store=self.store, username="alice", reason="policy")["user"]["deactivated_reason"], "policy")
        self.assertIsNone(reactivate_admin_user_payload(user_store=self.store, username="alice")["user"]["deactivated_reason"])
        self.assertEqual(set_admin_user_daily_quota_payload(user_store=self.store, username="alice", daily_limit=5)["user"]["api_quota_daily"], 5)

    def test_run_admin_user_mutation_maps_auth_error_to_value_error(self):
        with self.assertRaisesRegex(ValueError, "broken_user"):
            run_admin_user_mutation(lambda: (_ for _ in ()).throw(AuthError("broken_user")))


if __name__ == "__main__":
    unittest.main()
