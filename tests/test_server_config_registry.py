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

from ogp_web.server_config import registry
from tests.second_server_fixtures import orange_published_pack


class ServerConfigRegistryTests(unittest.TestCase):
    def test_effective_server_pack_uses_bootstrap_fallback(self):
        pack = registry.effective_server_pack("blackberry")
        self.assertEqual(pack["server_code"], "blackberry")
        self.assertEqual(pack["status"], "published")
        self.assertTrue(pack.get("metadata"))

    def test_effective_server_pack_uses_db_when_available(self):
        with patch(
            "ogp_web.server_config.registry._load_effective_pack_from_db",
            return_value={
                "server_code": "blackberry",
                "version": 7,
                "status": "published",
                "metadata": {"organizations": ["FIB"]},
            },
        ):
            pack = registry.effective_server_pack("blackberry")
        self.assertEqual(pack["version"], 7)
        self.assertEqual(pack["metadata"]["organizations"], ["FIB"])

    def test_runtime_resolution_snapshot_marks_neutral_fallback_for_db_only_server(self):
        with patch("ogp_web.server_config.registry._load_effective_pack_from_db", return_value=None):
            snapshot = registry.build_runtime_resolution_snapshot(server_code="orange", title="Orange City")

        self.assertEqual(snapshot["resolution_mode"], "neutral_fallback")
        self.assertTrue(snapshot["requires_explicit_runtime_pack"])
        self.assertFalse(snapshot["is_runtime_addressable"])
        self.assertFalse(snapshot["has_runtime_metadata"])
        self.assertFalse(snapshot["has_identity_capabilities"])

    def test_effective_server_pack_uses_published_pack_for_second_server(self):
        with patch(
            "ogp_web.server_config.registry._load_effective_pack_from_db",
            side_effect=lambda *, server_code, at_timestamp=None: orange_published_pack() if server_code == "orange" else None,
        ):
            pack = registry.effective_server_pack("orange")

        self.assertEqual(pack["server_code"], "orange")
        self.assertEqual(pack["status"], "published")
        self.assertEqual(pack["metadata"]["template_bindings"]["complaint"]["template_key"], "complaint_orange_v1")

    def test_bootstrap_pack_without_base_config_is_not_runtime_addressable(self):
        original_bootstrap = dict(registry._BOOTSTRAP_SERVER_PACKS)
        registry._BOOTSTRAP_SERVER_PACKS["orange"] = {
            "server_code": "orange",
            "version": 1,
            "status": "published",
            "metadata": {"organizations": ["GOV"], "procedure_types": []},
        }
        try:
            snapshot = registry.build_runtime_resolution_snapshot(server_code="orange", title="Orange City")
            self.assertEqual(snapshot["resolution_mode"], "bootstrap_pack")
            self.assertFalse(snapshot["is_runtime_addressable"])
            with patch("ogp_web.server_config.registry._load_codes_from_config_repo", return_value=None), patch(
                "ogp_web.server_config.registry._load_server_rows_from_db",
                return_value=[{"code": "orange", "title": "Orange City", "is_active": True}],
            ):
                with self.assertRaises(registry.ServerUnavailableError):
                    registry.get_server_config("orange")
        finally:
            registry._BOOTSTRAP_SERVER_PACKS.clear()
            registry._BOOTSTRAP_SERVER_PACKS.update(original_bootstrap)

    def test_db_only_server_is_no_longer_runtime_addressable_through_neutral_fallback(self):
        with patch("ogp_web.server_config.registry._load_codes_from_config_repo", return_value=None), patch(
            "ogp_web.server_config.registry._load_server_rows_from_db",
            return_value=[
                {"code": "orange", "title": "Orange City", "is_active": True},
            ],
        ):
            runtime_configs = registry._load_runtime_server_configs()

        self.assertNotIn("orange", runtime_configs)
        self.assertIn(registry.DEFAULT_SERVER_CODE, runtime_configs)

    def test_get_server_config_rejects_db_only_server_without_runtime_pack(self):
        with patch("ogp_web.server_config.registry._load_codes_from_config_repo", return_value=None), patch(
            "ogp_web.server_config.registry._load_server_rows_from_db",
            return_value=[
                {"code": "orange", "title": "Orange City", "is_active": True},
            ],
        ):
            with self.assertRaises(registry.ServerUnavailableError):
                registry.get_server_config("orange")

    def test_inactive_db_only_server_is_not_runtime_addressable(self):
        with patch("ogp_web.server_config.registry._load_codes_from_config_repo", return_value=None), patch(
            "ogp_web.server_config.registry._load_server_rows_from_db",
            return_value=[
                {"code": "orange", "title": "Orange City", "is_active": False},
            ],
        ):
            runtime_configs = registry._load_runtime_server_configs()

        self.assertNotIn("orange", runtime_configs)
        self.assertIn(registry.DEFAULT_SERVER_CODE, runtime_configs)

    def test_published_pack_second_server_is_runtime_addressable_with_its_own_metadata(self):
        with patch("ogp_web.server_config.registry._load_codes_from_config_repo", return_value=None), patch(
            "ogp_web.server_config.registry._load_server_rows_from_db",
            return_value=[
                {"code": "orange", "title": "Orange City", "is_active": True},
            ],
        ), patch(
            "ogp_web.server_config.registry._load_effective_pack_from_db",
            side_effect=lambda *, server_code, at_timestamp=None: orange_published_pack() if server_code == "orange" else None,
        ):
            orange = registry.get_server_config("orange")

        self.assertEqual(orange.code, "orange")
        self.assertEqual(orange.name, "Orange City")
        self.assertEqual(orange.organizations, ("GOV", "DOJ"))
        self.assertEqual(orange.procedure_types, ("appeal", "review"))
        self.assertEqual(
            orange.template_bindings["complaint"]["template_key"],
            "complaint_orange_v1",
        )
        self.assertEqual(orange.law_qa_sources, ("https://forum.gta5rp.com/forums/zakonodatelnaja-baza.102/",))
        self.assertEqual(orange.law_qa_bundle_path, "law_bundles/orange.json")
        self.assertEqual(orange.document_builder["choice_sets"]["claim_kind_by_court_type"]["appeal"][0]["value"], "orange_appeal_admin_claim")

    def test_resolve_document_builder_config_uses_bootstrap_metadata(self):
        document_builder = registry.resolve_document_builder_config("blackberry")

        self.assertIn("choice_sets", document_builder)
        self.assertIn("validators", document_builder)
        self.assertIn("supreme", document_builder["choice_sets"]["claim_kind_by_court_type"])

    def test_resolve_document_builder_config_returns_empty_for_db_only_server(self):
        with patch("ogp_web.server_config.registry._load_effective_pack_from_db", return_value=None):
            document_builder = registry.resolve_document_builder_config("orange")

        self.assertEqual(document_builder, {})

    def test_runtime_resolution_snapshot_marks_published_pack_without_explicit_fallback(self):
        with patch(
            "ogp_web.server_config.registry._load_effective_pack_from_db",
            side_effect=lambda *, server_code, at_timestamp=None: orange_published_pack() if server_code == "orange" else None,
        ):
            snapshot = registry.build_runtime_resolution_snapshot(server_code="orange", title="Orange City")

        self.assertEqual(snapshot["resolution_mode"], "published_pack")
        self.assertFalse(snapshot["requires_explicit_runtime_pack"])
        self.assertTrue(snapshot["is_runtime_addressable"])
        self.assertTrue(snapshot["has_runtime_metadata"])
        self.assertTrue(snapshot["has_identity_capabilities"])


if __name__ == "__main__":
    unittest.main()
