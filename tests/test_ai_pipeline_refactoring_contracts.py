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
