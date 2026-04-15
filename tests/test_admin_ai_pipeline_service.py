from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_WEB_SECRET", "test-secret")
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
os.environ.setdefault("OGP_SKIP_DEFAULT_APP_INIT", "1")

from ogp_web.services.admin_ai_pipeline_service import AdminAiPipelineService


class _FakeMetricsStore:
    def summarize_ai_generation_logs(self, *, flow="", retrieval_context_mode="", guard_warning="", limit=0):
        return {"total_generations": 1, "latency_ms_p50": 210}

    def list_ai_generation_logs(self, *, flow="", retrieval_context_mode="", guard_warning="", limit=0):
        model = "gpt-5.4-mini"
        if flow == "suggest":
            model = "gpt-5.4"
        return [
            {
                "created_at": "2026-04-15T10:00:00+00:00",
                "meta": {
                    "generation_id": f"{flow or 'law_qa'}_1",
                    "flow": flow or "law_qa",
                    "model": model,
                    "guard_status": "warn" if flow in {"", "law_qa"} else "pass",
                    "latency_ms": 210,
                    "retrieval_ms": 35,
                    "openai_ms": 210,
                    "total_suggest_ms": 245,
                    "validation_errors": ["new_fact_detected"],
                    "validation_retry_count": 1,
                    "safe_fallback_used": True,
                    "estimated_cost_usd": "1.25",
                    "total_tokens": 240,
                },
            }
        ]

    def list_ai_feedback(self, *, flow="", issue_type="", limit=0):
        return [
            {
                "created_at": "2026-04-15T10:05:00+00:00",
                "meta": {
                    "generation_id": f"{flow or 'law_qa'}_1",
                    "flow": flow or "law_qa",
                    "issues": [issue_type or "wrong_law"],
                    "note": "Article mismatch",
                },
            }
        ]


def test_build_payload_contains_summary_quality_cost_and_policy_actions():
    service = AdminAiPipelineService()

    payload = service.build_payload(
        metrics_store=_FakeMetricsStore(),
        flow="law_qa",
        issue_type="wrong_law",
        limit=20,
    )

    assert payload["flow"] == "law_qa"
    assert payload["issue_type"] == "wrong_law"
    assert payload["summary"]["total_generations"] == 1
    assert payload["quality_summary"]["wrong_law_rate"] == 100.0
    assert payload["cost_tables"]["by_flow"][0]["flow"] == "law_qa"
    assert payload["top_inaccurate_generations"][0]["generation_id"] == "law_qa_1"
    assert payload["policy_actions"]
