from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from fastapi import HTTPException

from ogp_web.server_config import PermissionSet
from ogp_web.services.capability_registry_service import get_capability_definition
from ogp_web.services.section_access_service import ensure_section_access, resolve_section_access_verdict


class SectionAccessServiceTests(unittest.TestCase):
    def test_access_verdict_allows_authenticated_complaint_section(self):
        verdict = resolve_section_access_verdict(
            capability=get_capability_definition("complaint"),
            permissions=PermissionSet(codes=frozenset(), server_code="blackberry"),
        )

        self.assertTrue(verdict.is_allowed)
        self.assertEqual(verdict.reason_code, "no_explicit_permission_required")

    def test_access_verdict_blocks_missing_permission(self):
        verdict = resolve_section_access_verdict(
            capability=get_capability_definition("law_qa"),
            permissions=PermissionSet(codes=frozenset(), server_code="blackberry"),
        )

        self.assertFalse(verdict.is_allowed)
        self.assertEqual(verdict.reason_code, "permission_missing")
        with self.assertRaises(HTTPException) as raised:
            ensure_section_access(verdict)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("court_claims", raised.exception.detail[0])


if __name__ == "__main__":
    unittest.main()
