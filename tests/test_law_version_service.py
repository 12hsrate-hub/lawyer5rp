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

from ogp_web.services import law_version_service


class _FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.executed = None

    def execute(self, query, params):
        self.executed = (query, params)
        return self

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeBackend:
    def __init__(self, rows):
        self.connection = _FakeConnection(rows)

    def connect(self):
        return self.connection


class LawVersionServiceTests(unittest.TestCase):
    def test_list_recent_law_versions_clamps_limit_and_maps_rows(self):
        backend = _FakeBackend(
            [
                {
                    "id": 7,
                    "server_code": "blackberry",
                    "generated_at_utc": "2026-04-14T12:00:00+00:00",
                    "effective_from": "2026-04-14T12:00:00+00:00",
                    "effective_to": None,
                    "fingerprint": "abc",
                    "chunk_count": 42,
                }
            ]
        )
        with patch("ogp_web.services.law_version_service.get_database_backend", return_value=backend):
            rows = law_version_service.list_recent_law_versions(server_code="blackberry", limit=999)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, 7)
        self.assertEqual(rows[0].chunk_count, 42)
        _, params = backend.connection.executed
        self.assertEqual(params[0], "blackberry")
        self.assertEqual(params[1], 100)


if __name__ == "__main__":
    unittest.main()
