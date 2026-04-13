from __future__ import annotations

import pytest
from fastapi import HTTPException

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
        impl=lambda image_data_url: {"principal_name": "A", "principal_rank": "B", "principal_phone": "C", "principal_address": ""},
        ai_exception_details=lambda exc: [str(exc)],
    )
    result = orchestration.run_principal_scan(PrincipalScanPayload(image_data_url="data:image/png;base64,AAAA"), deps)
    assert result.principal_address == "-"


def test_principal_scan_contract_rejects_bad_image_prefix():
    deps = orchestration.PrincipalScanDeps(impl=lambda image_data_url: {}, ai_exception_details=lambda exc: [str(exc)])
    with pytest.raises(HTTPException) as exc:
        orchestration.run_principal_scan(PrincipalScanPayload(image_data_url="http://bad"), deps)
    assert exc.value.status_code == 400


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
    )
    law_meta = build_law_qa_metrics_meta(
        payload=LawQaPayload(question="q", model="m", server_code="s", max_answer_chars=1000),
        result=law_result,
        used_sources=["u"],
        short_text_hash=lambda x: "h",
        mask_text_preview=lambda x, max_chars=0: x,
    )
    assert law_meta["flow"] == "law_qa"

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
    )
    suggest_meta = build_suggest_metrics_meta(
        payload=SuggestPayload(victim_name="v", org="o", subject="s", event_dt="e", raw_desc="r"),
        result=suggest_result,
        server_code="srv",
        short_text_hash=lambda x: "h",
        mask_text_preview=lambda x, max_chars=0: x,
    )
    assert suggest_meta["flow"] == "suggest"


def test_smoke_answer_law_question_details(monkeypatch):
    expected = ai_service.LawQaAnswerResult(
        text="x", generation_id="g", used_sources=[], indexed_documents=0, retrieval_confidence="low", retrieval_profile="law_qa", guard_status="pass", contract_version="v", bundle_status="ok", bundle_generated_at="", bundle_fingerprint="", warnings=[], shadow={}, selected_norms=[], telemetry={}, budget_status="ok", budget_warnings=[], budget_policy={}
    )
    monkeypatch.setattr(ai_service, "_answer_law_question_details_impl", lambda payload: expected)
    result = ai_service.answer_law_question_details(LawQaPayload(question="q", model="m", server_code="s", max_answer_chars=1000))
    assert result is expected


def test_smoke_suggest_text_details(monkeypatch):
    expected = ai_service.SuggestTextResult(
        text="x", generation_id="g", guard_status="pass", contract_version="v", warnings=[], shadow={}, telemetry={}, budget_status="ok", budget_warnings=[], budget_policy={}, retrieval_ms=1, openai_ms=2, total_suggest_ms=3, prompt_mode="legacy", retrieval_confidence="high", retrieval_context_mode="normal_context", retrieval_profile="suggest", bundle_status="ok", bundle_generated_at="", bundle_fingerprint="", selected_norms_count=0
    )
    monkeypatch.setattr(ai_service, "_suggest_text_details_impl", lambda payload, server_code="": expected)
    result = ai_service.suggest_text_details(SuggestPayload(victim_name="v", org="o", subject="s", event_dt="e", raw_desc="r"), server_code="s")
    assert result is expected


def test_smoke_extract_principal_scan(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "extract_principal_fields_with_proxy_fallback",
        lambda **kwargs: {"principal_name": "A", "principal_rank": "B", "principal_phone": "C", "principal_address": "X"},
    )
    result = ai_service.extract_principal_scan(PrincipalScanPayload(image_data_url="data:image/png;base64,AAAA"))
    assert result.principal_name == "A"
