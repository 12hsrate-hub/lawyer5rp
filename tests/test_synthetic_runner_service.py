from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.synthetic_runner_service import SyntheticRunnerService


class FakeMetricsStore:
    def __init__(self):
        self.events: list[dict] = []

    def log_event(self, **kwargs):
        self.events.append(kwargs)
        return True


class SyntheticRunnerServiceTests(unittest.TestCase):
    def test_smoke_suite_emits_run_and_step_events(self):
        store = FakeMetricsStore()
        service = SyntheticRunnerService(store)  # type: ignore[arg-type]
        payload = service.run_suite(suite="smoke", server_code="blackberry", trigger="test")
        self.assertEqual(payload["suite"], "smoke")
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(len(payload["steps"]), 10)
        run_events = [item for item in store.events if item.get("event_type") == "synthetic_run"]
        step_events = [item for item in store.events if item.get("event_type") == "synthetic_step"]
        self.assertEqual(len(run_events), 1)
        self.assertEqual(len(step_events), 10)

    def test_fault_suite_contains_required_guardrails(self):
        store = FakeMetricsStore()
        service = SyntheticRunnerService(store)  # type: ignore[arg-type]
        payload = service.run_suite(suite="fault", server_code="blackberry", trigger="test")
        steps = {item["step_code"] for item in payload["steps"]}
        self.assertIn("transient_retry", steps)
        self.assertIn("permanent_failure_dlq", steps)
        self.assertIn("idempotency", steps)
        self.assertIn("cross_server_isolation", steps)


if __name__ == "__main__":
    unittest.main()
