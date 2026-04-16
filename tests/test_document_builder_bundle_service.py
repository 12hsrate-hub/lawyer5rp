from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.document_builder_bundle_service import build_document_builder_bundle


class DocumentBuilderBundleServiceTests(unittest.TestCase):
    def test_blackberry_bundle_uses_config_owned_document_builder_metadata(self):
        payload = build_document_builder_bundle(server_id="blackberry", document_type="court_claim")

        self.assertEqual(payload["server"], "blackberry")
        self.assertEqual(payload["template"]["name"], "court_claim_bbcode_v1")
        self.assertIn("supreme", payload["choice_sets"]["claim_kind_by_court_type"])
        self.assertEqual(
            payload["validators"]["required_fields_by_claim_kind"]["__default__"],
            ["plaintiff_name", "defendant_name", "situation_description", "closing_request"],
        )

    def test_unknown_server_keeps_neutral_fallback_without_blackberry_overrides(self):
        payload = build_document_builder_bundle(server_id="orange", document_type="court_claim")

        self.assertEqual(payload["server"], "orange")
        self.assertEqual(payload["choice_sets"]["claim_kind_by_court_type"], {})
        self.assertEqual(payload["validators"]["required_fields_by_claim_kind"], {})


if __name__ == "__main__":
    unittest.main()
