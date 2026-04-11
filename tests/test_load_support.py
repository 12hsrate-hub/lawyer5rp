from __future__ import annotations

import unittest
from pathlib import Path

from load.suggest_load_support import (
    build_artifact_dir,
    build_k6_env,
    build_report_markdown,
    normalize_profile_name,
    normalize_vus,
)


class LoadSupportTests(unittest.TestCase):
    def test_normalize_profile_name_rejects_unknown_profile(self):
        with self.assertRaises(ValueError):
            normalize_profile_name("unknown")

    def test_normalize_vus_requires_positive_number(self):
        with self.assertRaises(ValueError):
            normalize_vus(0)

    def test_build_artifact_dir_uses_run_id_and_profile(self):
        artifact_dir = build_artifact_dir(artifacts_root="artifacts/load", run_id="run123", profile="mid")

        self.assertEqual(artifact_dir, Path("artifacts/load").resolve() / "run123" / "mid")

    def test_build_k6_env_includes_summary_path_and_thresholds(self):
        env = build_k6_env(
            base_url="https://lawyer5rp.online/",
            session_cookie="cookie-value",
            profile="short",
            vus=10,
            duration="45s",
            artifact_dir=Path("artifacts/load/run123/short"),
            threshold_p95_ms=2500,
            threshold_error_rate=0.05,
        )

        self.assertEqual(env["BASE_URL"], "https://lawyer5rp.online")
        self.assertEqual(env["PROFILE"], "short")
        self.assertEqual(env["VUS"], "10")
        self.assertEqual(env["DURATION"], "45s")
        self.assertEqual(Path(env["SUMMARY_PATH"]), Path("artifacts/load/run123/short/summary.json"))
        self.assertEqual(env["THRESHOLD_P95_MS"], "2500")
        self.assertEqual(env["THRESHOLD_ERROR_RATE"], "0.05")

    def test_build_report_markdown_renders_core_metrics(self):
        summary = {
            "metrics": {
                "http_req_duration": {"values": {"avg": 123.4, "p(95)": 456.7, "p(99)": 789.0}},
                "http_req_failed": {"values": {"rate": 0.02}},
                "suggest_ok": {"values": {"count": 120}},
                "suggest_overload": {"values": {"count": 4}},
                "suggest_error": {"values": {"count": 1}},
            }
        }

        report = build_report_markdown(
            summary,
            profile="long",
            vus=30,
            duration="2m",
            base_url="https://lawyer5rp.online",
            run_id="run123",
        )

        self.assertIn("Suggest Load Test Report", report)
        self.assertIn("`run123`", report)
        self.assertIn("`long`", report)
        self.assertIn("`30`", report)
        self.assertIn("`456.7`", report)
        self.assertIn("`120`", report)


if __name__ == "__main__":
    unittest.main()
