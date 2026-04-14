from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.law_admin_service import normalize_source_urls, validate_source_urls


class LawAdminServiceHelpersTests(unittest.TestCase):
    def test_normalize_source_urls_removes_empty_and_duplicates(self):
        normalized = normalize_source_urls(
            [
                "",
                "  ",
                "https://example.com/law/a",
                "https://example.com/law/a",
                "https://example.com/law/b",
            ]
        )
        self.assertEqual(
            normalized,
            (
                "https://example.com/law/a",
                "https://example.com/law/b",
            ),
        )

    def test_validate_source_urls_reports_invalid_and_duplicates(self):
        validation = validate_source_urls(
            [
                "https://example.com/law/a",
                "ftp://example.com/law/a",
                "https://example.com/law/a",
                "invalid-url",
                "http://example.com/law/b",
            ]
        )

        self.assertEqual(
            validation.accepted_urls,
            (
                "https://example.com/law/a",
                "http://example.com/law/b",
            ),
        )
        self.assertEqual(
            validation.invalid_urls,
            (
                "ftp://example.com/law/a",
                "invalid-url",
            ),
        )
        self.assertEqual(validation.duplicate_count, 1)


if __name__ == "__main__":
    unittest.main()
