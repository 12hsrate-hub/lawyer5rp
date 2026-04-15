from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.server_context_service import resolve_user_server_context


class _DummyUserStore:
    def __init__(self, server_code: str = "blackberry"):
        self._server_code = server_code

    def get_server_code(self, username: str) -> str:
        return self._server_code


class ServerContextServiceTests(unittest.TestCase):
    def test_resolve_user_server_context_uses_store_server_by_default(self):
        store = _DummyUserStore("blackberry")
        config = type("Cfg", (), {"code": "blackberry"})()
        permissions = object()

        with patch(
            "ogp_web.services.server_context_service.get_server_config",
            return_value=config,
        ) as get_server_config_mock, patch(
            "ogp_web.services.server_context_service.build_permission_set",
            return_value=permissions,
        ) as build_permission_set_mock:
            resolved_config, resolved_permissions = resolve_user_server_context(store, "tester")

        self.assertIs(resolved_config, config)
        self.assertIs(resolved_permissions, permissions)
        get_server_config_mock.assert_called_once_with("blackberry")
        build_permission_set_mock.assert_called_once_with(store, "tester", config)

    def test_resolve_user_server_context_honors_explicit_server_code(self):
        store = _DummyUserStore("blackberry")
        config = type("Cfg", (), {"code": "orange"})()
        permissions = object()

        with patch(
            "ogp_web.services.server_context_service.get_server_config",
            return_value=config,
        ) as get_server_config_mock, patch(
            "ogp_web.services.server_context_service.build_permission_set",
            return_value=permissions,
        ):
            resolved_config, resolved_permissions = resolve_user_server_context(
                store,
                "tester",
                server_code="Orange",
            )

        self.assertIs(resolved_config, config)
        self.assertIs(resolved_permissions, permissions)
        get_server_config_mock.assert_called_once_with("orange")
