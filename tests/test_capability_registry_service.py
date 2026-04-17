from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.capability_registry_service import (
    get_capability_definition,
    list_capability_definitions,
)


class CapabilityRegistryServiceTests(unittest.TestCase):
    def test_registry_contains_primary_sections_as_thin_contracts(self):
        definitions = {item.section_code: item for item in list_capability_definitions()}

        self.assertEqual(set(definitions), {"complaint", "court_claim", "law_qa"})
        complaint = definitions["complaint"]
        self.assertEqual(complaint.capability_code, "complaint.compose")
        self.assertEqual(complaint.executor_code, "complaint")
        self.assertEqual(complaint.required_artifacts, ("form", "template", "validation", "access"))
        self.assertEqual(complaint.current_truth, "hybrid")
        self.assertEqual(complaint.target_truth, "published_pack")
        self.assertIn("/api/generate", complaint.read_inventory.route_entries)
        self.assertTrue(definitions["court_claim"].default_strict_cutover)
        self.assertFalse(definitions["complaint"].default_strict_cutover)

    def test_get_capability_definition_rejects_unknown_section(self):
        with self.assertRaises(KeyError):
            get_capability_definition("unknown")


if __name__ == "__main__":
    unittest.main()
