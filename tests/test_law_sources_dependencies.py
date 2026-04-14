from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.law_sources_dependencies import build_sources_dependency_payload


class LawSourcesDependenciesTests(unittest.TestCase):
    def test_build_sources_dependency_payload_reports_shared_sources_by_server(self):
        payload = build_sources_dependency_payload(
            [
                {
                    "server_code": "blackberry",
                    "server_name": "Blackberry",
                    "source_origin": "content_workflow",
                    "source_urls": ["https://law.example/a", "https://law.example/b"],
                    "active_law_version_id": 10,
                },
                {
                    "server_code": "orange",
                    "server_name": "Orange",
                    "source_origin": "server_config",
                    "source_urls": ["https://law.example/a"],
                    "active_law_version_id": 11,
                },
            ]
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["server_count"], 2)
        self.assertEqual(payload["source_count"], 2)

        blackberry = next(item for item in payload["servers"] if item["server_code"] == "blackberry")
        orange = next(item for item in payload["servers"] if item["server_code"] == "orange")
        self.assertEqual(blackberry["shared_source_count"], 1)
        self.assertEqual(blackberry["shared_with_servers"], ["orange"])
        self.assertEqual(orange["shared_source_count"], 1)
        self.assertEqual(orange["shared_with_servers"], ["blackberry"])


if __name__ == "__main__":
    unittest.main()
