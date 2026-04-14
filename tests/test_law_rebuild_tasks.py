from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.law_rebuild_tasks import find_active_law_rebuild_task


class LawRebuildTasksTests(unittest.TestCase):
    def test_find_active_law_rebuild_task_returns_running_for_same_server(self):
        tasks = {
            "t1": {"task_id": "t1", "scope": "law_sources_rebuild", "server_code": "blackberry", "status": "running"},
            "t2": {"task_id": "t2", "scope": "law_sources_rebuild", "server_code": "orange", "status": "queued"},
        }
        item = find_active_law_rebuild_task(tasks=tasks, server_code="blackberry")
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["task_id"], "t1")

    def test_find_active_law_rebuild_task_ignores_finished(self):
        tasks = {
            "t1": {"task_id": "t1", "scope": "law_sources_rebuild", "server_code": "blackberry", "status": "finished"},
            "t2": {"task_id": "t2", "scope": "law_sources_rebuild", "server_code": "blackberry", "status": "failed"},
        }
        item = find_active_law_rebuild_task(tasks=tasks, server_code="blackberry")
        self.assertIsNone(item)


if __name__ == "__main__":
    unittest.main()
