from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.auth_service import AuthUser
from ogp_web.services.complaint_runtime_service import ComplaintRuntimeService, SuggestConcurrencyLimiter
from ogp_web.services.feature_flags import Cohort, EnforcementMode, FlagDecision, RolloutMode


class ComplaintRuntimeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ComplaintRuntimeService(
            suggest_concurrency_limiter=SuggestConcurrencyLimiter(max_concurrency=1),
        )

    def _validation_flag(self, *, use_new_flow: bool) -> FlagDecision:
        return FlagDecision(
            flag="validation_gate_v1",
            mode=RolloutMode.ALL,
            cohort=Cohort.DEFAULT,
            use_new_flow=use_new_flow,
            enforcement=EnforcementMode.WARN,
        )

    def test_maybe_validate_law_qa_result_uses_store_user_lookup(self):
        store = types.SimpleNamespace(
            backend=types.SimpleNamespace(),
            get_user_id=lambda username: 42,
        )
        metrics_store = types.SimpleNamespace()
        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")
        result = types.SimpleNamespace(
            text="answer",
            used_sources=["https://example.com/law/a"],
            selected_norms=[{"article_label": "1"}],
            generation_id="gen-1",
        )

        with patch("ogp_web.services.complaint_runtime_service.ValidationRepository.create_law_qa_run") as fake_create, \
            patch("ogp_web.services.complaint_runtime_service.ValidationService.run_validation") as fake_run, \
            patch("ogp_web.services.complaint_runtime_service.record_validation_fail_rate") as fake_metric:
            fake_create.return_value = {"id": 7}
            fake_run.return_value = types.SimpleNamespace(run={"status": "success"})

            self.service.maybe_validate_law_qa_result(
                store=store,
                metrics_store=metrics_store,
                user=user,
                effective_server_code="blackberry",
                question="What law applies?",
                result=result,
                validation_flag=self._validation_flag(use_new_flow=True),
            )

        fake_create.assert_called_once()
        self.assertEqual(fake_create.call_args.kwargs["user_id"], 42)
        fake_run.assert_called_once_with(target_type="law_qa_run", target_id=7)
        fake_metric.assert_called_once()

    def test_maybe_validate_law_qa_result_skips_when_user_lookup_missing(self):
        backend = types.SimpleNamespace(
            connect=lambda: (_ for _ in ()).throw(AssertionError("direct backend lookup should not happen"))
        )
        store = types.SimpleNamespace(
            backend=backend,
            get_user_id=lambda username: None,
        )
        metrics_store = types.SimpleNamespace()
        user = AuthUser(username="missing", email="missing@example.com", server_code="blackberry")
        result = types.SimpleNamespace(
            text="answer",
            used_sources=[],
            selected_norms=[],
            generation_id="gen-2",
        )

        with patch("ogp_web.services.complaint_runtime_service.ValidationRepository.create_law_qa_run") as fake_create, \
            patch("ogp_web.services.complaint_runtime_service.ValidationService.run_validation") as fake_run:
            self.service.maybe_validate_law_qa_result(
                store=store,
                metrics_store=metrics_store,
                user=user,
                effective_server_code="blackberry",
                question="What law applies?",
                result=result,
                validation_flag=self._validation_flag(use_new_flow=True),
            )

        fake_create.assert_not_called()
        fake_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
