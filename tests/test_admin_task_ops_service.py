from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

from fastapi import HTTPException

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_WEB_SECRET", "test-secret")
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
os.environ.setdefault("OGP_SKIP_DEFAULT_APP_INIT", "1")

from ogp_web.schemas import AdminBulkActionPayload
from ogp_web.services.admin_task_ops_service import AdminTaskOpsService
from ogp_web.services.auth_service import AuthUser
from tests.temp_helpers import make_temporary_directory


class _FakeMetricsStore:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def log_event(self, **kwargs):
        self.events.append(kwargs)


class AdminTaskOpsServiceTests(unittest.TestCase):
    def test_claim_law_rebuild_task_returns_active_task_when_running_exists(self):
        tempdir = make_temporary_directory()
        try:
            service = AdminTaskOpsService(tasks_path=Path(tempdir.name) / "admin_tasks.json")
            service.put_task(
                {
                    "task_id": "law-rebuild-active",
                    "scope": "law_sources_rebuild",
                    "server_code": "blackberry",
                    "status": "running",
                }
            )

            active_task, queued_task = service.claim_law_rebuild_task(server_code="blackberry")

            self.assertIsNotNone(active_task)
            self.assertIsNone(queued_task)
            self.assertEqual(active_task["task_id"], "law-rebuild-active")
        finally:
            tempdir.cleanup()

    def test_start_bulk_action_task_updates_progress_and_result(self):
        tempdir = make_temporary_directory()
        try:
            progress_updates: list[tuple[int, int]] = []

            def fake_executor(**kwargs):
                callback = kwargs.get("progress_callback")
                if callback:
                    callback(1, 2)
                    callback(2, 2)
                progress_updates.extend([(1, 2), (2, 2)])
                return {"success_count": 2}

            service = AdminTaskOpsService(
                tasks_path=Path(tempdir.name) / "admin_tasks.json",
                bulk_action_executor=fake_executor,
            )
            payload = AdminBulkActionPayload(
                usernames=["alice", "bob"],
                action="grant_tester",
                run_async=True,
            )
            result = service.start_bulk_action_task(
                payload=payload,
                user=AuthUser(username="admin", email="admin@example.com", server_code="blackberry"),
                metrics_store=_FakeMetricsStore(),
                user_store=object(),
            )

            task = None
            for _ in range(40):
                task = service.load_task(result["task_id"])
                if task and task.get("status") == "finished":
                    break
                time.sleep(0.05)

            self.assertIsNotNone(task)
            self.assertEqual(task["status"], "finished")
            self.assertEqual(task["progress"], {"done": 2, "total": 2})
            self.assertEqual(task["result"], {"success_count": 2})
            self.assertEqual(progress_updates, [(1, 2), (2, 2)])
        finally:
            tempdir.cleanup()

    def test_start_law_sources_rebuild_task_logs_conflict(self):
        tempdir = make_temporary_directory()
        try:
            service = AdminTaskOpsService(tasks_path=Path(tempdir.name) / "admin_tasks.json")
            service.put_task(
                {
                    "task_id": "law-rebuild-active",
                    "scope": "law_sources_rebuild",
                    "server_code": "blackberry",
                    "status": "running",
                }
            )
            metrics = _FakeMetricsStore()

            with self.assertRaises(HTTPException) as raised:
                service.start_law_sources_rebuild_task(
                    server_code="blackberry",
                    user=AuthUser(username="admin", email="admin@example.com", server_code="blackberry"),
                    metrics_store=metrics,
                    rebuild_callback=lambda: {"ok": True},
                )

            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(metrics.events[-1]["event_type"], "admin_law_sources_rebuild_async_conflict")
        finally:
            tempdir.cleanup()


if __name__ == "__main__":
    unittest.main()
