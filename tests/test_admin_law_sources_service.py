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

from ogp_web.services.admin_law_sources_service import (
    require_law_sources_task_status_payload,
    resolve_law_sources_target_server_code,
)
from ogp_web.services.auth_service import AuthUser


class _Permissions:
    def __init__(self, allowed: set[str]):
        self.allowed = allowed

    def has(self, permission: str) -> bool:
        return permission in self.allowed


class _FakeUserStore:
    pass


class AdminLawSourcesServiceTests(unittest.TestCase):
    def test_resolve_law_sources_target_server_code_allows_same_server(self):
        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")
        resolved = resolve_law_sources_target_server_code(
            user=user,
            user_store=_FakeUserStore(),
            requested_server_code="",
        )
        self.assertEqual(resolved, "blackberry")

    def test_resolve_law_sources_target_server_code_requires_cross_server_permissions(self):
        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")

        from unittest.mock import patch

        with patch(
            "ogp_web.services.admin_law_sources_service.resolve_user_server_permissions",
            side_effect=[_Permissions({"manage_laws"}), _Permissions({"manage_laws"})],
        ):
            with self.assertRaises(HTTPException) as exc:
                resolve_law_sources_target_server_code(
                    user=user,
                    user_store=_FakeUserStore(),
                    requested_server_code="orange",
                )
        self.assertEqual(exc.exception.status_code, 403)

    def test_require_law_sources_task_status_payload_validates_scope_and_server(self):
        task_loader = lambda task_id: {"task_id": task_id, "scope": "law_sources_rebuild", "server_code": "blackberry", "status": "finished"}
        payload = require_law_sources_task_status_payload(
            task_id="t1",
            target_server_code="blackberry",
            task_loader=task_loader,
        )
        self.assertEqual(payload["status"], "finished")
        self.assertEqual(payload["canonical_status"], "succeeded")

        with self.assertRaises(HTTPException) as missing_exc:
            require_law_sources_task_status_payload(
                task_id="missing",
                target_server_code="blackberry",
                task_loader=lambda _task_id: None,
            )
        self.assertEqual(missing_exc.exception.status_code, 404)

        with self.assertRaises(HTTPException) as server_exc:
            require_law_sources_task_status_payload(
                task_id="foreign",
                target_server_code="blackberry",
                task_loader=lambda task_id: {"task_id": task_id, "scope": "law_sources_rebuild", "server_code": "orange", "status": "running"},
            )
        self.assertEqual(server_exc.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
