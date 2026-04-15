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

from ogp_web.services.server_context_service import (
    extract_server_law_context_settings,
    resolve_server_config,
    resolve_server_law_bundle_path,
    resolve_server_law_sources,
    resolve_user_server_context,
)


class _DummyUserStore:
    def __init__(self, server_code: str = "blackberry"):
        self._server_code = server_code

    def get_server_code(self, username: str) -> str:
        return self._server_code


class ServerContextServiceTests(unittest.TestCase):
    def test_resolve_server_config_uses_fallback_when_server_code_missing(self):
        config = type("Cfg", (), {"code": "blackberry"})()

        with patch(
            "ogp_web.services.server_context_service.get_server_config",
            return_value=config,
        ) as get_server_config_mock:
            resolved = resolve_server_config(fallback_server_code="blackberry")

        self.assertIs(resolved, config)
        get_server_config_mock.assert_called_once_with("blackberry")

    def test_resolve_server_law_bundle_path_uses_shared_server_config(self):
        config = type("Cfg", (), {"law_qa_bundle_path": "/tmp/laws.json"})()

        with patch(
            "ogp_web.services.server_context_service.resolve_server_config",
            return_value=config,
        ) as resolve_server_config_mock:
            bundle_path = resolve_server_law_bundle_path(server_code="blackberry")

        self.assertEqual(bundle_path, "/tmp/laws.json")
        resolve_server_config_mock.assert_called_once_with(server_code="blackberry", fallback_server_code="blackberry")

    def test_resolve_server_law_sources_normalizes_values(self):
        config = type("Cfg", (), {"law_qa_sources": (" https://example.com/a ", "", "https://example.com/a ")})()

        with patch(
            "ogp_web.services.server_context_service.resolve_server_config",
            return_value=config,
        ) as resolve_server_config_mock:
            source_urls = resolve_server_law_sources(server_code="blackberry")

        self.assertEqual(source_urls, ("https://example.com/a",))
        resolve_server_config_mock.assert_called_once_with(server_code="blackberry", fallback_server_code="blackberry")

    def test_extract_server_law_context_settings_collects_bundle_and_sources(self):
        config = type(
            "Cfg",
            (),
            {
                "law_qa_sources": (" https://example.com/a ", "https://example.com/a ", "https://example.com/b "),
                "law_qa_bundle_path": " /tmp/law-bundle.json ",
                "law_qa_bundle_max_age_hours": 72,
            },
        )()

        settings = extract_server_law_context_settings(config)

        self.assertEqual(settings.source_urls, ("https://example.com/a", "https://example.com/b"))
        self.assertEqual(settings.bundle_path, "/tmp/law-bundle.json")
        self.assertEqual(settings.bundle_max_age_hours, 72)

    def test_resolve_user_server_context_uses_store_server_by_default(self):
        store = _DummyUserStore("blackberry")
        config = type("Cfg", (), {"code": "blackberry"})()
        permissions = object()

        with patch(
            "ogp_web.services.server_context_service.resolve_server_config",
            return_value=config,
        ) as resolve_server_config_mock, patch(
            "ogp_web.services.server_context_service.build_permission_set",
            return_value=permissions,
        ) as build_permission_set_mock:
            resolved_config, resolved_permissions = resolve_user_server_context(store, "tester")

        self.assertIs(resolved_config, config)
        self.assertIs(resolved_permissions, permissions)
        resolve_server_config_mock.assert_called_once_with(server_code="", fallback_server_code="blackberry")
        build_permission_set_mock.assert_called_once_with(store, "tester", config)

    def test_resolve_user_server_context_honors_explicit_server_code(self):
        store = _DummyUserStore("blackberry")
        config = type("Cfg", (), {"code": "orange"})()
        permissions = object()

        with patch(
            "ogp_web.services.server_context_service.resolve_server_config",
            return_value=config,
        ) as resolve_server_config_mock, patch(
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
        resolve_server_config_mock.assert_called_once_with(server_code="Orange", fallback_server_code="blackberry")
