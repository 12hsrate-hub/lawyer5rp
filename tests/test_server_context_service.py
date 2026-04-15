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
    build_allowed_nav_items,
    extract_server_ai_context_settings,
    extract_server_feature_flags,
    extract_server_identity_settings,
    extract_server_law_context_settings,
    extract_server_shell_context,
    resolve_server_config,
    resolve_server_law_bundle_path,
    resolve_server_law_sources,
    resolve_user_server_context,
    server_has_feature,
)


class _DummyUserStore:
    def __init__(self, server_code: str = "blackberry"):
        self._server_code = server_code

    def get_server_code(self, username: str) -> str:
        return self._server_code


class ServerContextServiceTests(unittest.TestCase):
    class _DummyPermissions:
        def __init__(self, allowed: set[str]):
            self.allowed = allowed

        def allows(self, permission: str) -> bool:
            return permission in self.allowed

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

    def test_extract_server_ai_context_settings_normalizes_modes_and_profiles(self):
        config = type(
            "Cfg",
            (),
            {
                "shadow_law_qa_profile": " law_shadow ",
                "shadow_suggest_profile": " suggest_shadow ",
                "suggest_prompt_mode": " Data_Driven ",
                "suggest_low_confidence_policy": " Soft_Fail ",
            },
        )()

        settings = extract_server_ai_context_settings(config)

        self.assertEqual(settings.shadow_law_qa_profile, "law_shadow")
        self.assertEqual(settings.shadow_suggest_profile, "suggest_shadow")
        self.assertEqual(settings.suggest_prompt_mode, "data_driven")
        self.assertEqual(settings.suggest_low_confidence_policy, "soft_fail")

    def test_extract_server_identity_settings_normalizes_code_and_name(self):
        config = type("Cfg", (), {"code": " Orange ", "name": " Orange County "})()

        settings = extract_server_identity_settings(config, fallback_server_code="blackberry")

        self.assertEqual(settings.code, "orange")
        self.assertEqual(settings.name, "Orange County")

    def test_extract_server_feature_flags_sorts_and_deduplicates_values(self):
        config = type("Cfg", (), {"feature_flags": (" beta_mode ", "", "alpha_mode", "beta_mode")})()

        feature_flags = extract_server_feature_flags(config)

        self.assertEqual(feature_flags, ("alpha_mode", "beta_mode"))

    def test_server_has_feature_uses_feature_flags_when_checker_missing(self):
        config = type("Cfg", (), {"feature_flags": ("law_qa_nano_enabled",)})()

        self.assertTrue(server_has_feature(config, "law_qa_nano_enabled"))
        self.assertFalse(server_has_feature(config, "suggest_nano_enabled"))

    def test_build_allowed_nav_items_filters_by_permission(self):
        permissions = self._DummyPermissions({"allowed"})
        nav_items = (
            type("Nav", (), {"key": "one", "label": "One", "href": "/one", "permission": "allowed"})(),
            type("Nav", (), {"key": "two", "label": "Two", "href": "/two", "permission": "blocked"})(),
        )

        payload = build_allowed_nav_items(nav_items, permissions)

        self.assertEqual(payload, [{"key": "one", "label": "One", "href": "/one"}])

    def test_extract_server_shell_context_includes_filtered_nav_and_form_fields(self):
        permissions = self._DummyPermissions({"allowed"})
        server_config = type(
            "Cfg",
            (),
            {
                "code": "blackberry",
                "name": "BlackBerry",
                "app_title": "OGP Builder",
                "page_nav_items": (
                    type("Nav", (), {"key": "one", "label": "One", "href": "/one", "permission": "allowed"})(),
                ),
                "complaint_nav_items": (
                    type("Nav", (), {"key": "two", "label": "Two", "href": "/two", "permission": "allowed"})(),
                ),
                "complaint_bases": ("basis",),
                "evidence_fields": ("field",),
                "complaint_forum_url": "https://forum.example",
            },
        )()

        payload = extract_server_shell_context(server_config, permissions)

        self.assertEqual(payload["server_code"], "blackberry")
        self.assertEqual(payload["server_name"], "BlackBerry")
        self.assertEqual(payload["app_title"], "OGP Builder")
        self.assertEqual(payload["page_nav_items"], [{"key": "one", "label": "One", "href": "/one"}])
        self.assertEqual(payload["complaint_nav_items"], [{"key": "two", "label": "Two", "href": "/two"}])
        self.assertEqual(payload["complaint_bases"], ("basis",))
        self.assertEqual(payload["evidence_fields"], ("field",))
        self.assertEqual(payload["complaint_forum_url"], "https://forum.example")

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
