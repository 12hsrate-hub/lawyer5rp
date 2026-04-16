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

import scripts.sync_server_bootstrap_pack as sync_script


class _FakeConn:
    def __init__(self, *, server_exists: bool):
        self.server_exists = server_exists
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params=()):
        normalized = " ".join(str(query).split())
        self.executed.append((normalized, tuple(params)))
        if "SELECT code FROM servers" in normalized:
            return _FakeResult({"code": params[0]} if self.server_exists else None)
        raise AssertionError(f"unexpected query: {normalized}")

    def close(self):
        return None


class _FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _FakeBackend:
    def __init__(self, *, server_exists: bool):
        self.conn = _FakeConn(server_exists=server_exists)

    def connect(self):
        return self.conn


class SyncServerBootstrapPackTests(unittest.TestCase):
    def test_sync_server_pack_skips_when_runtime_server_row_is_missing(self):
        backend = _FakeBackend(server_exists=False)

        with patch.object(sync_script, "_load_pack_payload", return_value={"metadata": {"organizations": ["GOV"]}}), patch.object(
            sync_script,
            "get_database_backend",
            return_value=backend,
        ), patch.object(sync_script, "load_web_env"):
            result = sync_script.sync_server_pack(server_code="orange")

        self.assertEqual(
            result,
            {
                "server_code": "orange",
                "changed": False,
                "version": 0,
                "reason": "server_missing",
            },
        )
        self.assertEqual(len(backend.conn.executed), 1)


if __name__ == "__main__":
    unittest.main()
