from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.law_versions_repository import LawVersionsRepository


class _FakeConnection:
    def __init__(self, *, fail_on_second_execute: bool = False):
        self.fail_on_second_execute = fail_on_second_execute
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.commit_called = False
        self.rollback_called = False
        self.close_called = False

    def execute(self, query, params=()):
        self.executed.append((query, params))
        if self.fail_on_second_execute and len(self.executed) == 2:
            raise RuntimeError("boom")
        return self

    def commit(self):
        self.commit_called = True

    def rollback(self):
        self.rollback_called = True

    def close(self):
        self.close_called = True


class _FakeBackend:
    def __init__(self, conn: _FakeConnection):
        self.conn = conn

    def connect(self):
        return self.conn


class LawVersionsRepositoryTests(unittest.TestCase):
    def test_rollback_active_version_runs_both_updates_in_one_transaction(self):
        conn = _FakeConnection()
        repository = LawVersionsRepository(_FakeBackend(conn))

        repository.rollback_active_version(server_code="blackberry", target_version_id=10)

        self.assertEqual(len(conn.executed), 2)
        self.assertTrue(conn.commit_called)
        self.assertFalse(conn.rollback_called)
        self.assertTrue(conn.close_called)
        self.assertEqual(conn.executed[0][1], ("blackberry", 10))
        self.assertEqual(conn.executed[1][1], (10, "blackberry"))

    def test_rollback_active_version_rolls_back_on_failure(self):
        conn = _FakeConnection(fail_on_second_execute=True)
        repository = LawVersionsRepository(_FakeBackend(conn))

        with self.assertRaises(RuntimeError):
            repository.rollback_active_version(server_code="blackberry", target_version_id=10)

        self.assertFalse(conn.commit_called)
        self.assertTrue(conn.rollback_called)
        self.assertTrue(conn.close_called)


if __name__ == "__main__":
    unittest.main()
