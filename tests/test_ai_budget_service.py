from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from shared.ogp_ai import AiUsageSummary
from ogp_web.services.ai_budget_service import build_ai_telemetry, evaluate_budget


class AiBudgetServiceTests(unittest.TestCase):
    def test_build_ai_telemetry_uses_actual_usage_when_available(self):
        telemetry = build_ai_telemetry(
            model_name="gpt-5.4",
            prompt_text="x" * 400,
            output_text="y" * 160,
            usage=AiUsageSummary(input_tokens=100, output_tokens=40, total_tokens=140),
            latency_ms=850,
            cache_hit=False,
        )

        self.assertEqual(telemetry.input_tokens, 100)
        self.assertEqual(telemetry.output_tokens, 40)
        self.assertEqual(telemetry.total_tokens, 140)
        self.assertEqual(telemetry.usage_source, "actual")
        self.assertEqual(telemetry.pricing_source, "official_default")
        self.assertGreater(telemetry.estimated_cost_usd or 0.0, 0.0)

    def test_build_ai_telemetry_marks_local_cache_as_zero_cost(self):
        telemetry = build_ai_telemetry(
            model_name="gpt-5.4",
            prompt_text="cached prompt",
            output_text="cached answer",
            usage=AiUsageSummary(),
            latency_ms=5,
            cache_hit=True,
        )

        self.assertEqual(telemetry.estimated_cost_usd, 0.0)
        self.assertEqual(telemetry.pricing_source, "local_cache")

    def test_evaluate_budget_warns_when_thresholds_are_exceeded(self):
        telemetry = build_ai_telemetry(
            model_name="gpt-5.4",
            prompt_text="x" * 70000,
            output_text="y" * 9000,
            usage=AiUsageSummary(),
            latency_ms=1200,
            cache_hit=False,
        )

        assessment = evaluate_budget(flow="suggest", telemetry=telemetry)

        self.assertEqual(assessment.status, "warn")
        self.assertIn("budget_prompt_warn", assessment.warnings)
        self.assertIn("budget_total_warn", assessment.warnings)


if __name__ == "__main__":
    unittest.main()
