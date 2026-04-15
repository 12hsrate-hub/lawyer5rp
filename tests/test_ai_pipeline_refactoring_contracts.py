from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_DB_BACKEND", "sqlite")
os.environ.setdefault("OGP_WEB_SECRET", "test-secret")

from ogp_web.schemas import LawQaPayload, PrincipalScanPayload, SuggestPayload
from ogp_web.services import ai_service
from ogp_web.services.ai_pipeline import guardrails, orchestration, transport
from ogp_web.services.ai_pipeline.telemetry_meta import build_law_qa_metrics_meta, build_suggest_metrics_meta


def test_transport_retry_policy_contract():
    policy = transport.default_retry_policy(max_attempts=0)
    assert policy.max_attempts == 1


def test_guardrails_contract_clean_and_truncate():
    cleaned = guardrails.clean_suggest_text("Готовый текст жалобы\n1. Факт")
    assert cleaned == "Факт"
    assert guardrails.truncate_suggest_value("один два три", max_chars=6).endswith("...")


def test_principal_scan_contract_validation():
    deps = orchestration.PrincipalScanDeps(
        impl=lambda image_data_url: {"principal_name": "A", "principal_rank": "B", "principal_phone": "1234567", "principal_address": ""},
        ai_exception_details=lambda exc: [str(exc)],
    )
    result = orchestration.run_principal_scan(PrincipalScanPayload(image_data_url="data:image/png;base64,AAAA"), deps)
    assert result.principal_address == "-"


def test_principal_scan_contract_rejects_bad_image_prefix():
    deps = orchestration.PrincipalScanDeps(impl=lambda image_data_url: {}, ai_exception_details=lambda exc: [str(exc)])
    with pytest.raises(HTTPException) as exc:
        orchestration.run_principal_scan(PrincipalScanPayload(image_data_url="http://bad"), deps)
    assert exc.value.status_code == 400


def test_suggest_generation_attempts_contract_compacts_and_switches_model():
    attempts = (
        orchestration.SuggestGenerationAttempt(raw_desc="a", law_context="ctx-1"),
        orchestration.SuggestGenerationAttempt(raw_desc="a", law_context="ctx-2"),
    )
    compaction_levels: list[int] = []

    def generator(attempt, model_name):
        if attempt.law_context == "ctx-1":
            raise RuntimeError("maximum context length exceeded")
        return {"model": model_name, "law_context": attempt.law_context}

    result = orchestration.run_suggest_generation_attempts(
        attempts=attempts,
        prompt_builder=lambda attempt: f"prompt:{attempt.law_context}",
        generator=generator,
        is_context_window_error=lambda exc: "context length" in str(exc),
        ai_exception_details=lambda exc: [str(exc)],
        clock=lambda: 10.0,
        selected_model="gpt-5.4-mini",
        selection_reason="suggest_default",
        low_confidence_model="gpt-5.4",
        on_context_compaction=lambda level: compaction_levels.append(level),
    )

    assert result.generation_result == {"model": "gpt-5.4", "law_context": "ctx-2"}
    assert result.prompt_text == "prompt:ctx-2"
    assert result.selected_model == "gpt-5.4"
    assert result.selection_reason == "suggest_context_compacted"
    assert result.compaction_level == 1
    assert compaction_levels == [1]


def test_suggest_validation_remediation_contract_retries_then_falls_back():
    class _Validation:
        def __init__(self, blocker_codes=(), warning_codes=(), info_codes=(), blockers=()):
            self.blocker_codes = tuple(blocker_codes)
            self.warning_codes = tuple(warning_codes)
            self.info_codes = tuple(info_codes)
            self.blockers = tuple(blockers)
            self.status = "fail" if blocker_codes else "pass"

    class _Remediation:
        def __init__(self, text, validation, retries_used, safe_fallback_used):
            self.text = text
            self.validation = validation
            self.retries_used = retries_used
            self.safe_fallback_used = safe_fallback_used

    validation_calls: list[str] = []

    def validate(text, context):
        _ = context
        validation_calls.append(text)
        if "retry" in text:
            return _Validation(blocker_codes=("new_fact_detected",), blockers=("b",))
        if "fallback" in text:
            return _Validation()
        return _Validation(blocker_codes=("new_fact_detected",), blockers=("a",))

    result = orchestration.run_suggest_validation_remediation(
        generation_result=type("Gen", (), {"text": "bad-initial"})(),
        point3_context=object(),
        clean_text=lambda text: text,
        validate_generated_paragraph=validate,
        legacy_validation_error_codes=lambda codes: tuple(codes),
        retry_generator=lambda validation_error: type("Gen", (), {"text": f"retry:{validation_error}"})(),
        ai_exception_details=lambda exc: [str(exc)],
        build_safe_fallback_paragraph=lambda context: "fallback-text",
        apply_validation_remediation=lambda text, context: _Remediation(text, _Validation(), 2, False),
        remediation_factory=lambda text, validation, retries_used, safe_fallback_used: _Remediation(
            text, validation, retries_used, safe_fallback_used
        ),
    )

    assert result.validation_retry_count == 1
    assert result.validation_errors == ("new_fact_detected",)
    assert result.generation_result.text.startswith("retry:")
    assert result.remediation.text == "fallback-text"
    assert result.remediation.safe_fallback_used is True


def test_build_suggest_result_contract_aggregates_warning_codes():
    result = orchestration.build_suggest_result(
        text="ok",
        generation_id="g1",
        contract_version="v1",
        shadow={},
        telemetry_meta={"selected_model": "gpt-5.4"},
        budget_status="ok",
        budget_warnings=["budget_warn"],
        budget_policy={"flow": "suggest"},
        retrieval_ms=1,
        openai_ms=2,
        total_suggest_ms=3,
        prompt_mode="legacy",
        retrieval_confidence="high",
        retrieval_context_mode="low_confidence_context",
        retrieval_profile="suggest",
        bundle_status="fresh",
        bundle_generated_at="",
        bundle_fingerprint="fp",
        selected_norms_count=1,
        policy_mode="factual_plus_legal",
        policy_reason="r",
        valid_triggers_count=1,
        avg_trigger_confidence=0.5,
        remediation_retries=1,
        safe_fallback_used=False,
        validation_status="pass_after_retry",
        validation_retry_count=1,
        validation_errors=("new_fact_detected",),
        input_warning_codes=("input_warn",),
        protected_terms=("term",),
        selected_model="gpt-5.4",
        selection_reason="suggest_default",
        guard_warning_codes=("guard_warn",),
        validator_warning_codes=("validator_warn",),
        point3_input_warning_codes=("input_warn",),
        context_compaction_level=1,
        factual_fallback_expanded_mode="factual_fallback_expanded",
        guard_status="warn",
    )

    assert result.guard_status == "warn"
    assert result.selected_model == "gpt-5.4"
    assert "guard_warn" in result.warnings
    assert "validator_warn" in result.warnings
    assert "budget_warn" in result.warnings
    assert "input_warn" in result.warnings
    assert "suggest_low_confidence_context" in result.warnings
    assert "suggest_context_compacted" in result.warnings
    assert "suggest_output_remediated" in result.warnings
    assert "suggest_validation_retry" in result.warnings
    assert "suggest_legal_grounded" in result.warnings


def test_finalize_suggest_result_contract_builds_metrics_and_payload():
    class _GenerationResult:
        usage = {"total_tokens": 3}
        cache_hit = False
        attempt_path = "direct"
        attempt_duration_ms = 120
        route_policy = "direct_first"

    class _Validation:
        blocker_codes = ()
        warning_codes = ("validator_warn",)
        info_codes = ("validator_info",)
        blockers = ()
        status = "warn"

    class _Remediation:
        validation = _Validation()
        retries_used = 1
        safe_fallback_used = False

    class _Audit:
        warning_codes = ("input_warn",)
        protected_terms = ("term",)

    class _PolicyDecision:
        mode = "factual_plus_legal"
        reason = "policy_reason"
        valid_triggers_count = 2
        avg_confidence = 0.75

    class _Point3Context:
        input_audit = _Audit()
        policy_decision = _PolicyDecision()

    class _SuggestContext:
        retrieval_confidence = "high"
        retrieval_context_mode = "normal_context"
        retrieval_profile = "suggest"
        bundle_status = "fresh"
        bundle_generated_at = "2026-04-16T00:00:00Z"
        bundle_fingerprint = "bundle-fp"
        selected_norms_count = 1

    class _BudgetAssessment:
        status = "ok"
        warnings = ("budget_warn",)
        policy = {"flow": "suggest"}

    class _GuardResult:
        status = "warn"
        warning_codes = ("guard_warn",)

    result = orchestration.finalize_suggest_result(
        generation_id="g-final",
        contract_version="v-final",
        shadow={"enabled": False},
        generation_result=_GenerationResult(),
        remediation=_Remediation(),
        validation_retry_count=1,
        validation_errors=(),
        selected_model="gpt-5.4",
        selection_reason="suggest_default",
        suggest_compaction_level=1,
        suggest_prompt_mode="data_driven",
        suggest_context=_SuggestContext(),
        point3_context=_Point3Context(),
        prompt_text="prompt",
        final_text="final text",
        retrieval_ms=11,
        openai_ms=22,
        total_suggest_ms=33,
        build_ai_telemetry=lambda **kwargs: {"model": kwargs["model_name"], "latency_ms": kwargs["latency_ms"]},
        evaluate_budget=lambda **kwargs: _BudgetAssessment(),
        telemetry_to_meta=lambda telemetry: dict(telemetry),
        policy_to_meta=lambda policy: {"policy": policy["flow"]},
        guard_suggest_answer=lambda text: _GuardResult(),
        legacy_validation_error_codes=lambda codes: tuple(codes),
        factual_fallback_expanded_mode="factual_fallback_expanded",
    )

    assert result.selected_model == "gpt-5.4"
    assert result.selection_reason == "suggest_default"
    assert result.guard_status == "warn"
    assert result.retrieval_ms == 11
    assert result.openai_ms == 22
    assert result.total_suggest_ms == 33
    assert result.telemetry["attempt_path"] == "direct"
    assert result.telemetry["validation_status"] == "pass_after_retry"
    assert "guard_warn" in result.warnings
    assert "validator_warn" in result.warnings
    assert "budget_warn" in result.warnings
    assert "suggest_context_compacted" in result.warnings
    assert "suggest_validation_retry" in result.warnings


def test_finalize_law_qa_result_contract_builds_metrics_and_payload():
    class _RetrievalResult:
        indexed_chunk_count = 4
        confidence = "high"
        profile = "law_qa"
        bundle_health = type(
            "BundleHealth",
            (),
            {
                "status": "fresh",
                "generated_at": "2026-04-16T00:00:00Z",
                "fingerprint": "bundle-fp",
                "warnings": ("bundle_warn",),
            },
        )()

    class _BudgetAssessment:
        status = "ok"
        warnings = ("budget_warn",)
        policy = {"flow": "law_qa"}

    class _GuardResult:
        status = "warn"
        warning_codes = ("guard_warn",)

    result = orchestration.finalize_law_qa_result(
        text="Answer with source https://laws.example",
        generation_id="g-law",
        contract_version="v-law",
        retrieval_result=_RetrievalResult(),
        shadow={"enabled": False},
        model_name="gpt-5.4",
        selection_reason="law_qa_default",
        requested_model="gpt-5.4-mini",
        compaction_level=1,
        prompt="prompt",
        usage={"total_tokens": 9},
        latency_ms=44,
        max_answer_chars=40,
        build_ai_telemetry=lambda **kwargs: {"model": kwargs["model_name"], "latency_ms": kwargs["latency_ms"]},
        evaluate_budget=lambda **kwargs: _BudgetAssessment(),
        unique_sources=lambda retrieval_result: ("https://laws.example/article-1",),
        guard_law_qa_answer=lambda **kwargs: _GuardResult(),
        telemetry_to_meta=lambda telemetry: dict(telemetry),
        policy_to_meta=lambda policy: {"policy": policy["flow"]},
        strip_law_qa_source_urls=lambda text: text.replace(" https://laws.example", ""),
        normalize_law_qa_text_formatting=lambda text: f"{text} normalized",
        build_selected_norms=lambda retrieval_result: [{"article": "1"}],
    )

    assert result.selected_model == "gpt-5.4"
    assert result.selection_reason == "law_qa_default"
    assert result.requested_model == "gpt-5.4-mini"
    assert result.guard_status == "warn"
    assert result.used_sources == ["https://laws.example/article-1"]
    assert result.telemetry["context_compaction_level"] == 1
    assert result.telemetry["selected_model"] == "gpt-5.4"
    assert result.selected_norms == [{"article": "1"}]
    assert "bundle_warn" in result.warnings
    assert "guard_warn" in result.warnings
    assert "budget_warn" in result.warnings
    assert "law_qa_context_compacted" in result.warnings


def test_run_law_qa_generation_attempts_contract_compacts_and_switches_model():
    attempts = (("ctx-1",), ("ctx-2",))
    warnings: list[tuple[str, str, int]] = []

    def request_generator(prompt, model_name):
        if prompt == "prompt:ctx-1":
            raise RuntimeError("maximum context length exceeded")
        return "answer", {"total_tokens": 12}

    result = orchestration.run_law_qa_generation_attempts(
        context_attempts=attempts,
        prompt_builder=lambda context_blocks, model_name: f"prompt:{context_blocks[0]}",
        request_generator=request_generator,
        is_context_window_error=lambda exc: "context length" in str(exc),
        ai_exception_details=lambda exc: [str(exc)],
        logger_warning=lambda message, model_name, attempt_level: warnings.append((message, model_name, attempt_level)),
        selected_model="gpt-5.4-mini",
        selection_reason="law_qa_default",
        low_confidence_model="gpt-5.4",
    )

    assert result.text == "answer"
    assert result.usage == {"total_tokens": 12}
    assert result.prompt == "prompt:ctx-2"
    assert result.model_name == "gpt-5.4"
    assert result.selection_reason == "law_qa_context_compacted"
    assert result.compaction_level == 1
    assert warnings == [("Law QA prompt exceeded context window for model %s; retrying with compact context level=%s", "gpt-5.4", 1)]


def test_resolve_law_qa_runtime_context_contract_builds_shadow_and_attempts():
    class _Payload:
        question = "When must detainee be released?"
        model = "gpt-5.4-mini"
        server_code = "blackberry"
        law_version_id = 12

    retrieval_result = type(
        "RetrievalResult",
        (),
        {
            "is_configured": True,
            "indexed_chunk_count": 2,
            "server_code": "blackberry",
            "server_name": "BlackBerry",
            "confidence": "low",
            "profile": "law_qa",
            "matches": ("primary",),
        },
    )()
    shadow_result = type("ShadowResult", (), {"matches": ("shadow",)})()
    calls: list[tuple[str, str]] = []

    def retrieve_law_context(**kwargs):
        calls.append((kwargs["profile"], kwargs["query"]))
        return shadow_result if kwargs["profile"] == "shadow_profile" else retrieval_result

    server_config = type("ServerConfig", (), {"feature_flags": frozenset({"legal_pipeline_shadow"})})()
    ai_context = type("AiContext", (), {"shadow_law_qa_profile": "shadow_profile"})()
    selection = type("Selection", (), {"model_name": "gpt-5.4", "reason": "law_qa_low_confidence"})()

    result = orchestration.resolve_law_qa_runtime_context(
        payload=_Payload(),
        default_server_code="default",
        retrieve_law_context=retrieve_law_context,
        resolve_server_config=lambda **kwargs: server_config,
        resolve_server_ai_context_settings=lambda **kwargs: ai_context,
        select_law_qa_model=lambda **kwargs: selection,
        get_flow_model=lambda flow, field, fallback: "gpt-5.4",
        build_shadow_comparison=lambda **kwargs: {"enabled": kwargs["enabled"], "profile": kwargs["profile"]},
        server_feature_enabled=lambda cfg, flag: flag in cfg.feature_flags,
        build_law_qa_context_blocks=lambda retrieval_result: ["ctx-a", "ctx-b"],
        build_law_qa_context_blocks_limited=lambda retrieval_result, **kwargs: [f"ctx-{kwargs['max_blocks']}"],
    )

    assert result.question == "When must detainee be released?"
    assert result.requested_model == "gpt-5.4-mini"
    assert result.retrieval_result is retrieval_result
    assert result.model_name == "gpt-5.4"
    assert result.selection_reason == "law_qa_low_confidence"
    assert result.low_confidence_model == "gpt-5.4"
    assert result.shadow == {"enabled": True, "profile": "shadow_profile"}
    assert result.context_attempts[0] == ["ctx-a", "ctx-b"]
    assert result.context_attempts[1] == ["ctx-8"]
    assert calls == [("law_qa", "When must detainee be released?"), ("shadow_profile", "When must detainee be released?")]


def test_resolve_suggest_runtime_context_contract_builds_shadow_and_attempts():
    payload = SuggestPayload(
        victim_name="Victim",
        org="Org",
        subject="Subject",
        event_dt="2026-04-16 10:00",
        raw_desc="Draft",
        complaint_basis="basis",
        main_focus="focus",
        law_version_id=9,
    )

    suggest_context = type(
        "SuggestContext",
        (),
        {
            "context_text": "law-context",
            "retrieval_confidence": "low",
            "retrieval_context_mode": "low_confidence_context",
            "retrieval_profile": "suggest",
            "bundle_status": "fresh",
            "bundle_generated_at": "2026-04-16T00:00:00Z",
            "bundle_fingerprint": "bundle-fp",
            "selected_norms_count": 1,
            "selected_norms": ("norm-1",),
        },
    )()
    primary_result = type("PrimaryResult", (), {"matches": ("primary",)})()
    shadow_result = type("ShadowResult", (), {"matches": ("shadow",)})()
    server_config = type("ServerConfig", (), {"feature_flags": frozenset({"legal_pipeline_shadow"})})()
    ai_context = type(
        "AiContext",
        (),
        {
            "suggest_prompt_mode": "data_driven",
            "suggest_low_confidence_policy": "controlled_fallback",
            "shadow_suggest_profile": "shadow_profile",
        },
    )()
    selection = type("Selection", (), {"model_name": "gpt-5.4-mini", "reason": "suggest_default"})()
    point3_context = type(
        "Point3Context",
        (),
        {
            "policy_decision": type("PolicyDecision", (), {"mode": "factual_plus_legal"})(),
            "prompt_context_json": staticmethod(lambda: {"ctx": "payload"}),
        },
    )()
    retrieval_calls: list[tuple[str, str]] = []

    def retrieve_law_context(**kwargs):
        retrieval_calls.append((kwargs["profile"], kwargs["query"]))
        return shadow_result if kwargs["profile"] == "shadow_profile" else primary_result

    result = orchestration.resolve_suggest_runtime_context(
        payload=payload,
        server_code="blackberry",
        default_server_code="default",
        clock=iter((10.0, 10.2)).__next__,
        new_generation_id=lambda: "gen-1",
        resolve_server_config=lambda **kwargs: server_config,
        resolve_server_ai_context_settings=lambda **kwargs: ai_context,
        build_shadow_comparison=lambda **kwargs: {"enabled": kwargs["enabled"], "profile": kwargs["profile"]},
        build_suggest_retrieval_query=lambda current_payload: "query",
        build_suggest_law_context=lambda **kwargs: suggest_context,
        suggest_context_factory=lambda **kwargs: kwargs,
        server_feature_enabled=lambda cfg, flag: flag in cfg.feature_flags,
        retrieve_law_context=retrieve_law_context,
        select_suggest_model=lambda **kwargs: selection,
        get_flow_model=lambda flow, field, fallback: "gpt-5.4",
        build_point3_pipeline_context=lambda **kwargs: point3_context,
        build_filtered_prompt_law_context=lambda **kwargs: "prompt-law-context",
        truncate_suggest_value=lambda text, max_chars: f"{text[:max_chars]}:{max_chars}",
    )

    assert result.generation_id == "gen-1"
    assert result.suggest_prompt_mode == "data_driven"
    assert result.low_confidence_policy == "controlled_fallback"
    assert result.selected_model == "gpt-5.4-mini"
    assert result.selection_reason == "suggest_default"
    assert result.low_confidence_model == "gpt-5.4"
    assert result.prompt_law_context == "prompt-law-context"
    assert result.retrieval_ms == 199
    assert result.shadow == {"enabled": True, "profile": "shadow_profile"}
    assert result.suggest_attempts[0].law_context == "prompt-law-context"
    assert result.suggest_attempts[1].law_context.endswith(":2600")
    assert retrieval_calls == [("suggest", "query"), ("shadow_profile", "query")]


def test_run_suggest_execution_flow_contract_builds_attempt_and_validation_flow():
    runtime_context = orchestration.SuggestRuntimeContext(
        generation_id="gen-1",
        server_config=object(),
        ai_context=object(),
        suggest_context=type(
            "SuggestContext",
            (),
            {
                "retrieval_context_mode": "normal_context",
                "bundle_fingerprint": "bundle-fp",
                "retrieval_profile": "suggest",
            },
        )(),
        shadow={},
        victim_name="Victim",
        org="Org",
        subject="Subject",
        event_dt="2026-04-16 10:00",
        complaint_basis="basis",
        main_focus="focus",
        raw_desc="Draft",
        suggest_prompt_mode="data_driven",
        low_confidence_policy="controlled_fallback",
        selected_model="gpt-5.4-mini",
        selection_reason="suggest_default",
        low_confidence_model="gpt-5.4",
        point3_context=object(),
        pipeline_context_payload={"ctx": "payload"},
        prompt_law_context="prompt-law-context",
        suggest_attempts=(
            orchestration.SuggestGenerationAttempt(raw_desc="Draft", law_context="law-ctx"),
        ),
        retrieval_ms=120,
    )
    compaction_levels: list[int] = []
    transport_calls: list[tuple[str, str, str]] = []

    def transport_call(*, model_name, raw_desc, law_context, validation_error=""):
        transport_calls.append((model_name, law_context, validation_error))
        return type("Gen", (), {"text": "generated", "usage": {"total_tokens": 3}, "cache_hit": False})()

    generation_attempt = orchestration.SuggestGenerationAttemptResult(
        generation_result=type("Gen", (), {"text": "generated", "usage": {"total_tokens": 3}, "cache_hit": False})(),
        prompt_text="prompt-text",
        selected_model="gpt-5.4",
        selection_reason="suggest_context_compacted",
        compaction_level=1,
        openai_ms=220,
    )
    remediation = type("Remediation", (), {"text": "final-text", "validation": object(), "retries_used": 1, "safe_fallback_used": False})()
    validation_result = orchestration.SuggestValidationRemediationResult(
        generation_result=generation_attempt.generation_result,
        cleaned_text="cleaned",
        remediation=remediation,
        validation_retry_count=1,
        validation_errors=("warn",),
    )

    result = orchestration.run_suggest_execution_flow(
        runtime_context=runtime_context,
        policy_mode="factual_plus_legal",
        transport_call=transport_call,
        build_suggest_prompt=lambda **kwargs: "prompt-text",
        run_suggest_generation_attempts=lambda **kwargs: compaction_levels.append(1) or generation_attempt,
        run_suggest_validation_remediation=lambda **kwargs: validation_result,
        is_context_window_error=lambda exc: False,
        ai_exception_details=lambda exc: [str(exc)],
        clock=lambda: 1.0,
        logger_warning=lambda message, level: None,
        clean_text=lambda text: text,
        validate_generated_paragraph=lambda text, context: object(),
        legacy_validation_error_codes=lambda codes: tuple(codes),
        build_safe_fallback_paragraph=lambda context: "fallback",
        apply_validation_remediation=lambda text, context: remediation,
        remediation_factory=lambda text, validation, retries_used, safe_fallback_used: remediation,
    )

    assert result.prompt_text == "prompt-text"
    assert result.selected_model == "gpt-5.4"
    assert result.selection_reason == "suggest_context_compacted"
    assert result.suggest_compaction_level == 1
    assert result.openai_ms == 220
    assert result.validation_retry_count == 1
    assert result.validation_errors == ("warn",)
    assert result.final_text == "final-text"
    assert compaction_levels == [1]


def test_run_law_qa_execution_flow_contract_builds_generation_attempt_and_latency():
    runtime_context = orchestration.LawQaRuntimeContext(
        question="When must detainee be released?",
        requested_model="gpt-5.4-mini",
        retrieval_result=type(
            "RetrievalResult",
            (),
            {
                "server_name": "BlackBerry",
                "server_code": "blackberry",
                "confidence": "low",
            },
        )(),
        server_config=object(),
        ai_context=object(),
        model_name="gpt-5.4-mini",
        selection_reason="law_qa_default",
        low_confidence_model="gpt-5.4",
        shadow={"enabled": False},
        context_attempts=(("ctx-1",),),
    )
    generation_attempt = orchestration.LawQaGenerationAttemptResult(
        text="answer",
        usage={"total_tokens": 9},
        prompt="prompt-text",
        model_name="gpt-5.4",
        selection_reason="law_qa_context_compacted",
        compaction_level=1,
    )

    result = orchestration.run_law_qa_execution_flow(
        runtime_context=runtime_context,
        payload=LawQaPayload(question="When must detainee be released?", model="gpt-5.4-mini", server_code="blackberry", max_answer_chars=400),
        default_server_code="default",
        clock=iter((10.0, 10.3)).__next__,
        new_generation_id=lambda: "law-gen-1",
        create_client=lambda: object(),
        request_law_qa_text=lambda **kwargs: ("answer", {"total_tokens": 9}),
        build_law_qa_prompt=lambda **kwargs: "prompt-text",
        run_law_qa_generation_attempts=lambda **kwargs: generation_attempt,
        is_context_window_error=lambda exc: False,
        ai_exception_details=lambda exc: [str(exc)],
        logger_warning=lambda message, model_name, level: None,
    )

    assert result.generation_id == "law-gen-1"
    assert result.retrieval_result is runtime_context.retrieval_result
    assert result.requested_model == "gpt-5.4-mini"
    assert result.shadow == {"enabled": False}
    assert result.text == "answer"
    assert result.usage == {"total_tokens": 9}
    assert result.prompt == "prompt-text"
    assert result.model_name == "gpt-5.4"
    assert result.selection_reason == "law_qa_context_compacted"
    assert result.compaction_level == 1
    assert result.latency_ms == 300


def test_telemetry_meta_contracts():
    law_result = ai_service.LawQaAnswerResult(
        text="ok",
        generation_id="g1",
        used_sources=["u"],
        indexed_documents=1,
        retrieval_confidence="high",
        retrieval_profile="law_qa",
        guard_status="pass",
        contract_version="v",
        bundle_status="ok",
        bundle_generated_at="",
        bundle_fingerprint="",
        warnings=[],
        shadow={},
        selected_norms=[],
        telemetry={},
        budget_status="ok",
        budget_warnings=[],
        budget_policy={},
        selected_model="gpt-5.4",
        selection_reason="law_qa_low_confidence",
        requested_model="gpt-5.4-mini",
    )
    law_meta = build_law_qa_metrics_meta(
        payload=LawQaPayload(question="q", model="m", server_code="s", max_answer_chars=1000),
        result=law_result,
        used_sources=["u"],
        short_text_hash=lambda x: "h",
        mask_text_preview=lambda x, max_chars=0: x,
    )
    assert law_meta["flow"] == "law_qa"
    assert law_meta["model"] == "gpt-5.4"
    assert law_meta["selected_model"] == "gpt-5.4"
    assert law_meta["selection_reason"] == "law_qa_low_confidence"
    assert law_meta["requested_model"] == "gpt-5.4-mini"

    suggest_result = ai_service.SuggestTextResult(
        text="ok",
        generation_id="g2",
        guard_status="pass",
        contract_version="v",
        warnings=[],
        shadow={},
        telemetry={},
        budget_status="ok",
        budget_warnings=[],
        budget_policy={},
        retrieval_ms=1,
        openai_ms=2,
        total_suggest_ms=3,
        prompt_mode="legacy",
        retrieval_confidence="high",
        retrieval_context_mode="normal_context",
        retrieval_profile="suggest",
        bundle_status="ok",
        bundle_generated_at="",
        bundle_fingerprint="",
        selected_norms_count=0,
        selected_model="gpt-5.4",
        selection_reason="suggest_low_confidence_context",
    )
    suggest_meta = build_suggest_metrics_meta(
        payload=SuggestPayload(victim_name="v", org="o", subject="s", event_dt="e", raw_desc="r"),
        result=suggest_result,
        server_code="srv",
        short_text_hash=lambda x: "h",
        mask_text_preview=lambda x, max_chars=0: x,
    )
    assert suggest_meta["flow"] == "suggest"
    assert suggest_meta["model"] == "gpt-5.4"
    assert suggest_meta["selected_model"] == "gpt-5.4"
    assert suggest_meta["selection_reason"] == "suggest_low_confidence_context"


def test_smoke_answer_law_question_details(monkeypatch):
    expected = ai_service.LawQaAnswerResult(
        text="x", generation_id="g", used_sources=[], indexed_documents=0, retrieval_confidence="low", retrieval_profile="law_qa", guard_status="pass", contract_version="v", bundle_status="ok", bundle_generated_at="", bundle_fingerprint="", warnings=[], shadow={}, selected_norms=[], telemetry={}, budget_status="ok", budget_warnings=[], budget_policy={}, selected_model="gpt-5.4", selection_reason="law_qa_low_confidence", requested_model="gpt-5.4-mini"
    )
    monkeypatch.setattr(ai_service, "_answer_law_question_details_impl", lambda payload: expected)
    result = ai_service.answer_law_question_details(LawQaPayload(question="q", model="m", server_code="s", max_answer_chars=1000))
    assert result is expected


def test_smoke_suggest_text_details(monkeypatch):
    expected = ai_service.SuggestTextResult(
        text="x", generation_id="g", guard_status="pass", contract_version="v", warnings=[], shadow={}, telemetry={}, budget_status="ok", budget_warnings=[], budget_policy={}, retrieval_ms=1, openai_ms=2, total_suggest_ms=3, prompt_mode="legacy", retrieval_confidence="high", retrieval_context_mode="normal_context", retrieval_profile="suggest", bundle_status="ok", bundle_generated_at="", bundle_fingerprint="", selected_norms_count=0, selected_model="gpt-5.4-mini", selection_reason="suggest_default"
    )
    monkeypatch.setattr(ai_service, "_suggest_text_details_impl", lambda payload, server_code="": expected)
    result = ai_service.suggest_text_details(SuggestPayload(victim_name="v", org="o", subject="s", event_dt="e", raw_desc="r"), server_code="s")
    assert result is expected


def test_smoke_extract_principal_scan(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "extract_principal_fields_with_proxy_fallback",
        lambda **kwargs: {"principal_name": "A", "principal_rank": "B", "principal_phone": "1234567", "principal_address": "X"},
    )
    result = ai_service.extract_principal_scan(PrincipalScanPayload(image_data_url="data:image/png;base64,AAAA"))
    assert result.principal_name == "A"


def test_suggest_forced_norms_uses_shared_server_context_resolver(monkeypatch):
    monkeypatch.setattr(ai_service, "_suggest_is_mask_exception_case", lambda query: True)
    monkeypatch.setattr(
        ai_service,
        "resolve_server_config",
        lambda **kwargs: type("Cfg", (), {"law_qa_bundle_path": "/tmp/bundle.json"})(),
    )
    monkeypatch.setattr(
        ai_service,
        "load_law_bundle_chunks",
        lambda server_code, bundle_path, law_version_id=None: (),
    )

    result = ai_service._build_suggest_forced_norms(server_code="blackberry", query="mask exception")
    assert result == ()
