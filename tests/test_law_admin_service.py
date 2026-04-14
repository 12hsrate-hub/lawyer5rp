from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.law_admin_service import LawAdminService, normalize_source_urls, validate_source_urls


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

    def test_list_recent_versions_returns_serialized_payload(self):
        service = LawAdminService(workflow_service=types.SimpleNamespace(repository=types.SimpleNamespace()))
        with patch("ogp_web.services.law_admin_service.list_recent_law_versions") as fake_list:
            fake_list.return_value = (
                types.SimpleNamespace(
                    id=12,
                    server_code="blackberry",
                    generated_at_utc="2026-04-14T12:00:00+00:00",
                    effective_from="2026-04-14T12:00:00+00:00",
                    effective_to="",
                    fingerprint="abc123",
                    chunk_count=345,
                ),
            )
            payload = service.list_recent_versions(server_code="blackberry", limit=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["id"], 12)
        self.assertEqual(payload["items"][0]["chunk_count"], 345)


if __name__ == "__main__":
    unittest.main()
