from __future__ import annotations

import json
import unittest
from pathlib import Path

from shared import ogp_ai


ROOT_DIR = Path(__file__).resolve().parents[1]
GOLDEN_BASELINE_PATH = ROOT_DIR / "tests" / "fixtures" / "exam_scoring_golden_baseline.json"


class ExamScoringGoldenTests(unittest.TestCase):
    def test_golden_baseline_shape_is_valid(self):
        payload = json.loads(GOLDEN_BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertTrue(str(payload.get("version") or "").strip())
        self.assertIsInstance(payload.get("cases"), list)
        self.assertGreaterEqual(len(payload["cases"]), 1)
        self.assertIsInstance(payload.get("max_regression_cases"), int)

        for case in payload["cases"]:
            self.assertTrue(str(case.get("id") or "").strip())
            self.assertIn("user_answer", case)
            self.assertIn("correct_answer", case)
            self.assertIsInstance(case.get("expected_score_min"), int)
            self.assertIsInstance(case.get("expected_score_max"), int)
            self.assertLessEqual(case["expected_score_min"], case["expected_score_max"])

    def test_golden_scoring_regression_gate(self):
        payload = json.loads(GOLDEN_BASELINE_PATH.read_text(encoding="utf-8"))
        max_regression_cases = int(payload.get("max_regression_cases") or 0)
        regressions: list[str] = []

        for case in payload.get("cases", []):
            expected_estimator_available = bool(case.get("expected_estimator_available", True))
            estimated = ogp_ai._estimate_exam_score_without_llm(
                user_answer=str(case.get("user_answer") or ""),
                correct_answer=str(case.get("correct_answer") or ""),
            )
            if not isinstance(estimated, dict):
                if expected_estimator_available:
                    regressions.append(f"{case.get('id')}: estimator returned None")
                continue
            if not expected_estimator_available:
                regressions.append(f"{case.get('id')}: estimator returned score for llm-required case")
                continue

            score = int(estimated.get("score") or 0)
            expected_min = int(case["expected_score_min"])
            expected_max = int(case["expected_score_max"])
            if score < expected_min or score > expected_max:
                regressions.append(f"{case.get('id')}: score={score} expected=[{expected_min},{expected_max}]")

        self.assertLessEqual(
            len(regressions),
            max_regression_cases,
            msg="Golden drift regression threshold exceeded: " + "; ".join(regressions),
        )


if __name__ == "__main__":
    unittest.main()
