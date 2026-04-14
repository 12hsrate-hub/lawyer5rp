from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.law_sources_validation import (
    canonicalize_source_url,
    normalize_source_urls,
    validate_source_urls,
)


class LawSourcesValidationTests(unittest.TestCase):
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

    def test_canonicalize_source_url_drops_query_fragment_and_trailing_slash(self):
        canonical = canonicalize_source_url("https://example.com/law/a/?q=1#fragment")
        self.assertEqual(canonical, "https://example.com/law/a")

    def test_validate_source_urls_reports_invalid_and_duplicates(self):
        validation = validate_source_urls(
            [
                "https://example.com/law/a?foo=1",
                "ftp://example.com/law/a",
                "https://example.com/law/a/",
                "invalid-url",
                "http://user:pass@",
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
                "http://user:pass@",
            ),
        )
        self.assertEqual(validation.duplicate_count, 1)
        self.assertEqual(validation.duplicate_urls, ("https://example.com/law/a",))
        self.assertEqual(
            validation.invalid_details,
            (
                {"url": "ftp://example.com/law/a", "reason": "unsupported_scheme"},
                {"url": "invalid-url", "reason": "unsupported_scheme"},
                {"url": "http://user:pass@", "reason": "missing_host"},
            ),
        )


if __name__ == "__main__":
    unittest.main()
