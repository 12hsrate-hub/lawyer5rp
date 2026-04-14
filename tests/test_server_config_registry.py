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

    def test_runtime_fallback_config_is_neutral_for_db_only_server(self):
        with patch("ogp_web.server_config.registry._load_codes_from_config_repo", return_value=None), patch(
            "ogp_web.server_config.registry._load_server_rows_from_db",
            return_value=[
                {"code": "orange", "title": "Orange City", "is_active": True},
            ],
        ):
            runtime_configs = registry._load_runtime_server_configs()

        self.assertIn("orange", runtime_configs)
        self.assertIn(registry.DEFAULT_SERVER_CODE, runtime_configs)
        orange = runtime_configs["orange"]
        self.assertEqual(orange.code, "orange")
        self.assertEqual(orange.name, "Orange City")
        self.assertEqual(orange.app_title, "Orange City")
        self.assertEqual(orange.law_qa_sources, ())
        self.assertEqual(orange.feature_flags, frozenset())
        self.assertEqual(orange.enabled_pages, frozenset())
        self.assertEqual(orange.complaint_forum_url, "")
        self.assertEqual(orange.exam_sheet_url, "")
        self.assertEqual(orange.procedure_types, ())
        self.assertEqual(orange.form_schema, {})
        self.assertEqual(orange.validation_profiles, {})
        self.assertEqual(orange.template_bindings, {})
        self.assertEqual(orange.terminology, {})


if __name__ == "__main__":
    unittest.main()
