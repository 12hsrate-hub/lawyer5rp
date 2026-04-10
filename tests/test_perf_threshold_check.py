from __future__ import annotations

import argparse
import json
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from scripts import perf_threshold_check


class PerfThresholdCheckTests(unittest.TestCase):
    def _write_snapshot(self, payload: dict) -> str:
        with NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
            return stream.name

    def _base_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            input="",
            top_endpoints=10,
            windows=(15, 60),
            output="",
            max_p95_growth=0.20,
            error_rate_delta=0.005,
            max_throughput_drop_ratio=0.10,
            min_requests=10,
            baseline="",
        )

    def test_load_windows_parses_numeric_payload(self):
        payload = {
            "windows": {
                "15": {"p50_ms": 10, "p95_ms": 100, "error_rate": 0.01, "throughput_rps": 2.5, "total_api_requests": 100},
                "invalid": {"error_rate": 0.1},
                "60": {"p95_ms": 120, "error_rate": 0.02, "throughput_rps": 1.2, "total_api_requests": 20},
            }
        }
        windows = perf_threshold_check.load_windows(payload)
        self.assertIn(15, windows)
        self.assertIn(60, windows)
        self.assertNotIn("invalid", windows)

    def test_parse_windows_skips_invalid_values(self):
        windows = perf_threshold_check._parse_windows("15,abc,60,, -1,120")
        self.assertEqual(windows, (15, 60, 120))

    def test_threshold_fails_on_p95_regression(self):
        baseline = self._write_snapshot(
            {
                "windows": {
                    "15": {
                        "p95_ms": 100,
                        "error_rate": 0.01,
                        "throughput_rps": 10,
                        "total_api_requests": 100,
                    }
                }
            }
        )
        current = self._write_snapshot(
            {
                "windows": {
                    "15": {
                        "p95_ms": 130,
                        "error_rate": 0.01,
                        "throughput_rps": 10,
                        "total_api_requests": 100,
                    }
                }
            }
        )
        try:
            args = self._base_args()
            args.input = current
            args.baseline = baseline
            ok, errors, warnings = perf_threshold_check._evaluate(args)
            self.assertFalse(ok)
            self.assertTrue(any("p95_ms" in item for item in errors))
            self.assertFalse(warnings)
        finally:
            Path(baseline).unlink()
            Path(current).unlink()

    def test_threshold_succeeds_for_stable_metrics(self):
        baseline = self._write_snapshot(
            {
                "windows": {
                    "15": {
                        "p95_ms": 100,
                        "error_rate": 0.01,
                        "throughput_rps": 10,
                        "total_api_requests": 100,
                    }
                }
            }
        )
        current = self._write_snapshot(
            {
                "windows": {
                    "15": {
                        "p95_ms": 108,
                        "error_rate": 0.014,
                        "throughput_rps": 9.5,
                        "total_api_requests": 120,
                    }
                }
            }
        )
        try:
            args = self._base_args()
            args.input = current
            args.baseline = baseline
            ok, errors, warnings = perf_threshold_check._evaluate(args)
            self.assertTrue(ok)
            self.assertFalse(errors)
            self.assertFalse(warnings)
        finally:
            Path(baseline).unlink()
            Path(current).unlink()

    def test_low_sample_windows_are_skipped(self):
        baseline = self._write_snapshot(
            {
                "windows": {
                    "15": {
                        "p95_ms": 100,
                        "error_rate": 0.01,
                        "throughput_rps": 10,
                        "total_api_requests": 5,
                    }
                }
            }
        )
        current = self._write_snapshot(
            {
                "windows": {
                    "15": {
                        "p95_ms": 250,
                        "error_rate": 0.5,
                        "throughput_rps": 1,
                        "total_api_requests": 6,
                    }
                }
            }
        )
        try:
            args = self._base_args()
            args.input = current
            args.baseline = baseline
            ok, errors, warnings = perf_threshold_check._evaluate(args)
            self.assertTrue(ok)
            self.assertFalse(errors)
            self.assertTrue(any("insufficient request sample" in item for item in warnings))
        finally:
            Path(baseline).unlink()
            Path(current).unlink()

    def test_missing_baseline_window_marks_failure(self):
        baseline = self._write_snapshot(
            {
                "windows": {
                    "15": {
                        "p95_ms": 100,
                        "error_rate": 0.01,
                        "throughput_rps": 10,
                        "total_api_requests": 100,
                    }
                }
            }
        )
        current = self._write_snapshot(
            {
                "windows": {
                    "30": {
                        "p95_ms": 100,
                        "error_rate": 0.01,
                        "throughput_rps": 10,
                        "total_api_requests": 100,
                    }
                }
            }
        )
        try:
            args = self._base_args()
            args.input = current
            args.baseline = baseline
            ok, errors, warnings = perf_threshold_check._evaluate(args)
            self.assertFalse(ok)
            self.assertTrue(any("no baseline snapshot" in item for item in warnings))
            self.assertFalse(errors)
        finally:
            Path(baseline).unlink()
            Path(current).unlink()


if __name__ == "__main__":
    unittest.main()
