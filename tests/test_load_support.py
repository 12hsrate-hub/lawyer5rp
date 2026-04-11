from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from load.suggest_load_support import (
    DEFAULT_COLLATERAL_P95_GROWTH_LIMIT,
    DEFAULT_COLLATERAL_P99_GROWTH_LIMIT,
    DEFAULT_SINGLE_ERROR_RATE_THRESHOLD,
    DEFAULT_SINGLE_P95_THRESHOLD_MS,
    build_parallel_report_markdown,
    build_parallel_summary,
    build_artifact_dir,
    build_k6_env,
    build_mixed_k6_env,
    build_mixed_report_markdown,
    build_mixed_summary,
    build_rollout_report_markdown,
    build_rollout_summary,
    build_report_markdown,
    default_profile_vus_map,
    evaluate_sla,
    evaluate_mixed_impact,
    evaluate_single_summary,
    normalize_profile_name,
    normalize_vus,
    summarize_server_metrics_csv,
    summarize_mixed_phase_run,
    summarize_profile_run,
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

    def test_summarize_server_metrics_csv_computes_peaks_and_deltas(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "server_metrics.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "timestamp_utc",
                        "cpu_percent",
                        "memory_percent",
                        "memory_used_mb",
                        "load_1m",
                        "load_5m",
                        "load_15m",
                        "disk_read_mb",
                        "disk_write_mb",
                        "net_sent_mb",
                        "net_recv_mb",
                        "process_count",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "timestamp_utc": "2026-04-12T10:00:00Z",
                        "cpu_percent": "10",
                        "memory_percent": "50",
                        "memory_used_mb": "1024",
                        "load_1m": "0.50",
                        "load_5m": "0.40",
                        "load_15m": "0.30",
                        "disk_read_mb": "100",
                        "disk_write_mb": "200",
                        "net_sent_mb": "300",
                        "net_recv_mb": "400",
                        "process_count": "120",
                    }
                )
                writer.writerow(
                    {
                        "timestamp_utc": "2026-04-12T10:00:02Z",
                        "cpu_percent": "90",
                        "memory_percent": "70",
                        "memory_used_mb": "1536",
                        "load_1m": "1.50",
                        "load_5m": "1.20",
                        "load_15m": "0.90",
                        "disk_read_mb": "140",
                        "disk_write_mb": "260",
                        "net_sent_mb": "360",
                        "net_recv_mb": "470",
                        "process_count": "180",
                    }
                )

            summary = summarize_server_metrics_csv(csv_path)

        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["cpu_peak"], 90.0)
        self.assertEqual(summary["memory_percent_peak"], 70.0)
        self.assertEqual(summary["disk_read_mb_delta"], 40.0)
        self.assertEqual(summary["net_recv_mb_delta"], 70.0)
        self.assertEqual(summary["process_count_peak"], 180.0)

    def test_build_report_markdown_includes_server_metrics_when_present(self):
        summary = {
            "metrics": {
                "http_req_duration": {"values": {"avg": 123.4, "p(95)": 456.7, "p(99)": 789.0}},
                "http_req_failed": {"values": {"rate": 0.02}},
                "suggest_ok": {"values": {"count": 120}},
                "suggest_overload": {"values": {"count": 4}},
                "suggest_error": {"values": {"count": 1}},
            }
        }
        server_metrics = {
            "sample_count": 3,
            "start_utc": "2026-04-12T10:00:00Z",
            "end_utc": "2026-04-12T10:00:03Z",
            "cpu_avg": 40.0,
            "cpu_p95": 80.0,
            "cpu_peak": 85.0,
            "memory_percent_peak": 72.0,
            "memory_used_mb_peak": 2048.0,
            "load_1m_peak": 1.5,
            "process_count_peak": 220.0,
            "disk_read_mb_delta": 50.0,
            "disk_write_mb_delta": 20.0,
            "net_recv_mb_delta": 100.0,
            "net_sent_mb_delta": 60.0,
        }

        report = build_report_markdown(
            summary,
            profile="mid",
            vus=10,
            duration="1m",
            base_url="https://lawyer5rp.online",
            run_id="run123",
            server_metrics_summary=server_metrics,
        )

        self.assertIn("Server Telemetry", report)
        self.assertIn("App / Server Correlation", report)
        self.assertIn("`85.0`", report)

    def test_evaluate_single_summary_flags_threshold_breach(self):
        summary = {
            "metrics": {
                "http_req_duration": {"values": {"avg": 120.0, "p(95)": 2600.0, "p(99)": 3000.0}},
                "http_req_failed": {"values": {"rate": 0.06}},
                "suggest_ok": {"values": {"count": 100}},
                "suggest_overload": {"values": {"count": 3}},
                "suggest_error": {"values": {"count": 2}},
            }
        }

        evaluation = evaluate_single_summary(
            summary,
            threshold_p95_ms=DEFAULT_SINGLE_P95_THRESHOLD_MS,
            threshold_error_rate=DEFAULT_SINGLE_ERROR_RATE_THRESHOLD,
        )

        self.assertFalse(evaluation["pass"])
        self.assertIn("p95_exceeded", evaluation["breaches"])
        self.assertIn("error_rate_exceeded", evaluation["breaches"])

    def test_build_mixed_k6_env_sets_group_a_and_group_b(self):
        env = build_mixed_k6_env(
            base_url="https://lawyer5rp.online/",
            session_cookie="cookie-value",
            group_a_profile="long",
            group_a_vus=30,
            group_b_vus=10,
            duration="90s",
            artifact_dir=Path("artifacts/load/run123/mixed/baseline_group_b"),
        )

        self.assertEqual(env["BASE_URL"], "https://lawyer5rp.online")
        self.assertEqual(env["GROUP_A_PROFILE"], "long")
        self.assertEqual(env["GROUP_A_VUS"], "30")
        self.assertEqual(env["GROUP_B_VUS"], "10")
        self.assertEqual(env["DURATION"], "90s")
        self.assertEqual(Path(env["SUMMARY_PATH"]), Path("artifacts/load/run123/mixed/baseline_group_b/summary.json"))

    def test_default_profile_vus_map_uses_recommended_tiers(self):
        mapping = default_profile_vus_map(["short", "mid", "long"])

        self.assertEqual(mapping, {"short": 5, "mid": 10, "long": 30})

    def test_evaluate_sla_reports_threshold_breaches(self):
        profile_summary = {
            "exit_code": 0,
            "p95_ms": 3100,
            "fail_rate": 0.08,
        }

        sla = evaluate_sla(profile_summary, threshold_p95_ms=2500, threshold_error_rate=0.05)

        self.assertFalse(sla["pass"])
        self.assertEqual(sla["breaches"], ["p95_exceeded", "error_rate_exceeded"])

    def test_build_parallel_summary_and_report_include_profile_runs(self):
        single = summarize_profile_run(
            {
                "metrics": {
                    "http_req_duration": {"values": {"avg": 100.0, "p(95)": 220.0, "p(99)": 300.0}},
                    "http_req_failed": {"values": {"rate": 0.01}},
                    "suggest_ok": {"values": {"count": 42}},
                    "suggest_overload": {"values": {"count": 2}},
                    "suggest_error": {"values": {"count": 1}},
                }
            },
            profile="short",
            vus=5,
            duration="1m",
            base_url="https://lawyer5rp.online",
            artifact_dir="artifacts/load/run123/short",
            exit_code=0,
        )
        single["sla"] = evaluate_sla(single, threshold_p95_ms=500, threshold_error_rate=0.05)

        summary = build_parallel_summary(
            run_id="run123",
            profile_runs=[single],
            base_url="https://lawyer5rp.online",
            duration="1m",
            artifacts_root="artifacts/load",
            server_metrics_summary={
                "sample_count": 4,
                "cpu_peak": 75.0,
                "memory_percent_peak": 66.0,
            },
        )
        report = build_parallel_report_markdown(summary)

        self.assertEqual(summary["profile_run_count"], 1)
        self.assertTrue(summary["all_sla_pass"])
        self.assertEqual(summary["failing_profiles"], [])
        self.assertEqual(summary["profiles"][0]["profile"], "short")
        self.assertEqual(summary["server_metrics"]["cpu_peak"], 75.0)
        self.assertIn("Parallel Suggest Load Report", report)
        self.assertIn("Server Telemetry", report)
        self.assertIn("short (5 VUs)", report)
        self.assertIn("SLA pass", report)

    def test_evaluate_mixed_impact_reports_growth_breach(self):
        baseline = {
            "exit_code": 0,
            "group_b_p95_ms": 200.0,
            "group_b_p99_ms": 300.0,
        }
        mixed = {
            "exit_code": 0,
            "group_b_p95_ms": 280.0,
            "group_b_p99_ms": 420.0,
        }

        impact = evaluate_mixed_impact(
            baseline,
            mixed,
            p95_growth_limit=DEFAULT_COLLATERAL_P95_GROWTH_LIMIT,
            p99_growth_limit=DEFAULT_COLLATERAL_P99_GROWTH_LIMIT,
        )

        self.assertFalse(impact["pass"])
        self.assertIn("group_b_p95_growth_exceeded", impact["breaches"])
        self.assertIn("group_b_p99_growth_exceeded", impact["breaches"])
        self.assertEqual(impact["p95_growth_ratio"], 0.4)

    def test_build_mixed_summary_and_report_include_delta(self):
        baseline_phase = summarize_mixed_phase_run(
            {
                "metrics": {
                    "group_b_req_duration": {"values": {"avg": 90.0, "p(95)": 180.0, "p(99)": 240.0}},
                    "group_b_req_failed": {"values": {"rate": 0.01}},
                    "group_b_ok": {"values": {"count": 120}},
                    "group_b_error": {"values": {"count": 2}},
                }
            },
            phase="baseline_group_b",
            group_a_profile="long",
            group_a_vus=0,
            group_b_vus=10,
            duration="1m",
            base_url="https://lawyer5rp.online",
            artifact_dir="artifacts/load/run123/mixed/baseline_group_b",
            exit_code=0,
            server_metrics_summary={"sample_count": 2, "cpu_peak": 44.0, "memory_percent_peak": 55.0},
        )
        mixed_phase = summarize_mixed_phase_run(
            {
                "metrics": {
                    "group_a_req_duration": {"values": {"avg": 400.0, "p(95)": 900.0, "p(99)": 1100.0}},
                    "group_a_ok": {"values": {"count": 40}},
                    "group_a_overload": {"values": {"count": 3}},
                    "group_a_error": {"values": {"count": 1}},
                    "group_b_req_duration": {"values": {"avg": 120.0, "p(95)": 210.0, "p(99)": 260.0}},
                    "group_b_req_failed": {"values": {"rate": 0.02}},
                    "group_b_ok": {"values": {"count": 100}},
                    "group_b_error": {"values": {"count": 4}},
                }
            },
            phase="mixed_group_ab",
            group_a_profile="long",
            group_a_vus=30,
            group_b_vus=10,
            duration="1m",
            base_url="https://lawyer5rp.online",
            artifact_dir="artifacts/load/run123/mixed/mixed_group_ab",
            exit_code=0,
            server_metrics_summary={"sample_count": 3, "cpu_peak": 88.0, "memory_percent_peak": 77.0},
        )
        impact = evaluate_mixed_impact(baseline_phase, mixed_phase, p95_growth_limit=0.25, p99_growth_limit=0.25)
        summary = build_mixed_summary(
            run_id="run123",
            base_url="https://lawyer5rp.online",
            duration="1m",
            artifacts_root="artifacts/load",
            group_a_profile="long",
            group_a_vus=30,
            group_b_vus=10,
            baseline_phase=baseline_phase,
            mixed_phase=mixed_phase,
            impact_sla=impact,
        )
        report = build_mixed_report_markdown(summary)

        self.assertEqual(summary["group_a_profile"], "long")
        self.assertEqual(summary["mixed_phase"]["group_a_overload"], 3)
        self.assertAlmostEqual(summary["impact_sla"]["p95_growth_ratio"], (210.0 - 180.0) / 180.0)
        self.assertIn("Mixed Load Impact Report", report)
        self.assertIn("Collateral Impact", report)
        self.assertIn("Server Telemetry", report)

    def test_build_rollout_summary_and_report_capture_blockers(self):
        single_evaluation = {
            "pass": True,
            "breaches": [],
            "p95_ms": 1200.0,
            "p99_ms": 1800.0,
            "fail_rate": 0.01,
            "suggest_overload": 0,
        }
        parallel_summary = {
            "all_sla_pass": True,
            "failing_profiles": [],
        }
        mixed_summary = {
            "impact_sla": {
                "pass": False,
                "breaches": ["group_b_p95_growth_exceeded"],
                "p95_growth_ratio": 0.31,
                "p99_growth_ratio": 0.18,
            }
        }

        rollout = build_rollout_summary(
            stage="optimization",
            single_evaluation=single_evaluation,
            parallel_summary=parallel_summary,
            mixed_summary=mixed_summary,
        )
        report = build_rollout_report_markdown(rollout)

        self.assertFalse(rollout["pass"])
        self.assertEqual(rollout["next_action"], "rollback_or_hold")
        self.assertIn("mixed_summary_failed", rollout["blockers"])
        self.assertIn("Suggest Rollout Safety Report", report)
        self.assertIn("rollback_or_hold", report)


if __name__ == "__main__":
    unittest.main()
