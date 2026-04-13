from __future__ import annotations

from typing import Callable

from ogp_web.schemas import LawQaPayload, SuggestPayload
from ogp_web.services.ai_pipeline.interfaces import LawQaAnswerResult, SuggestTextResult

LAW_QA_PROMPT_VERSION = "law_qa.v5"
from shared.ogp_ai_prompts import SUGGEST_PROMPT_VERSION


def build_law_qa_metrics_meta(
    *,
    payload: LawQaPayload,
    result: LawQaAnswerResult,
    used_sources: list[str],
    short_text_hash: Callable[[str], str],
    mask_text_preview: Callable[[str], str],
) -> dict[str, object]:
    return {
        "generation_id": result.generation_id,
        "flow": "law_qa",
        "contract_version": result.contract_version,
        "prompt_version": LAW_QA_PROMPT_VERSION,
        "server_code": payload.server_code,
        "model": payload.model,
        "input_chars": len(payload.question or ""),
        "input_hash": short_text_hash(payload.question or ""),
        "input_preview": mask_text_preview(payload.question or "", max_chars=180),
        "output_chars": len(result.text or ""),
        "output_hash": short_text_hash(result.text or ""),
        "output_preview": mask_text_preview(result.text or "", max_chars=220),
        "retrieval_profile": result.retrieval_profile,
        "retrieval_confidence": result.retrieval_confidence,
        "bundle_status": result.bundle_status,
        "bundle_generated_at": result.bundle_generated_at,
        "bundle_fingerprint": result.bundle_fingerprint,
        "guard_status": result.guard_status,
        "guard_warnings": list(result.warnings),
        "budget_status": result.budget_status,
        "budget_warnings": list(result.budget_warnings),
        "budget_policy": result.budget_policy,
        "used_sources_count": len(used_sources),
        "selected_norms_count": len(result.selected_norms),
        **result.telemetry,
        "shadow": result.shadow,
    }


def build_suggest_metrics_meta(
    *,
    payload: SuggestPayload,
    result: SuggestTextResult,
    server_code: str,
    short_text_hash: Callable[[str], str],
    mask_text_preview: Callable[[str], str],
) -> dict[str, object]:
    return {
        "generation_id": result.generation_id,
        "flow": "suggest",
        "contract_version": result.contract_version,
        "prompt_version": SUGGEST_PROMPT_VERSION,
        "prompt_mode": str(getattr(result, "prompt_mode", "legacy") or "legacy").strip().lower(),
        "server_code": server_code,
        "complaint_basis": payload.complaint_basis,
        "main_focus": payload.main_focus,
        "input_chars": len(payload.raw_desc or ""),
        "input_hash": short_text_hash(payload.raw_desc or ""),
        "input_preview": mask_text_preview(payload.raw_desc or "", max_chars=180),
        "output_chars": len(result.text or ""),
        "output_hash": short_text_hash(result.text or ""),
        "output_preview": mask_text_preview(result.text or "", max_chars=220),
        "guard_status": result.guard_status,
        "guard_warnings": list(result.warnings),
        "budget_status": result.budget_status,
        "budget_warnings": list(result.budget_warnings),
        "budget_policy": result.budget_policy,
        "retrieval_confidence": str(getattr(result, "retrieval_confidence", "medium") or "medium").strip().lower(),
        "retrieval_context_mode": str(getattr(result, "retrieval_context_mode", "normal_context") or "normal_context").strip(),
        "retrieval_profile": str(getattr(result, "retrieval_profile", "suggest") or "suggest").strip(),
        "bundle_status": str(getattr(result, "bundle_status", "unknown") or "unknown").strip(),
        "bundle_generated_at": str(getattr(result, "bundle_generated_at", "") or "").strip(),
        "bundle_fingerprint": str(getattr(result, "bundle_fingerprint", "") or "").strip(),
        "selected_norms_count": int(getattr(result, "selected_norms_count", 0) or 0),
        "policy_mode": str(getattr(result, "policy_mode", "") or "").strip(),
        "policy_reason": str(getattr(result, "policy_reason", "") or "").strip(),
        "valid_triggers_count": int(getattr(result, "valid_triggers_count", 0) or 0),
        "avg_trigger_confidence": float(getattr(result, "avg_trigger_confidence", 0.0) or 0.0),
        "remediation_retries": int(getattr(result, "remediation_retries", 0) or 0),
        "safe_fallback_used": bool(getattr(result, "safe_fallback_used", False)),
        "input_warning_codes": list(getattr(result, "input_warning_codes", ()) or ()),
        "protected_terms": list(getattr(result, "protected_terms", ()) or ()),
        "retrieval_ms": int(getattr(result, "retrieval_ms", 0) or 0),
        "openai_ms": int(getattr(result, "openai_ms", 0) or 0),
        "total_suggest_ms": int(getattr(result, "total_suggest_ms", 0) or 0),
        **dict(getattr(result, "telemetry", {}) or {}),
        "shadow": getattr(result, "shadow", {}),
    }
