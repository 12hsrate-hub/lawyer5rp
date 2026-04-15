from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from fastapi import HTTPException, status

from ogp_web.schemas import LawQaPayload, PrincipalScanPayload, PrincipalScanResult, SuggestPayload
from ogp_web.services.ai_pipeline.interfaces import SuggestTextResult


@dataclass(frozen=True)
class LawQaOrchestrationDeps:
    impl: Callable[[LawQaPayload], object]


@dataclass(frozen=True)
class SuggestOrchestrationDeps:
    impl: Callable[[SuggestPayload, str], object]


@dataclass(frozen=True)
class PrincipalScanDeps:
    impl: Callable[[str], dict[str, object]]
    ai_exception_details: Callable[[Exception], list[str]]


@dataclass(frozen=True)
class SuggestGenerationAttempt:
    raw_desc: str
    law_context: str


@dataclass(frozen=True)
class SuggestGenerationAttemptResult:
    generation_result: Any
    prompt_text: str
    selected_model: str
    selection_reason: str
    compaction_level: int
    openai_ms: int


@dataclass(frozen=True)
class SuggestValidationRemediationResult:
    generation_result: Any
    cleaned_text: str
    remediation: Any
    validation_retry_count: int
    validation_errors: tuple[str, ...]


def run_law_qa(payload: LawQaPayload, deps: LawQaOrchestrationDeps):
    return deps.impl(payload)


def run_suggest(payload: SuggestPayload, *, server_code: str, deps: SuggestOrchestrationDeps):
    return deps.impl(payload, server_code)


def run_suggest_generation_attempts(
    *,
    attempts: Sequence[SuggestGenerationAttempt],
    prompt_builder: Callable[[SuggestGenerationAttempt], str],
    generator: Callable[[SuggestGenerationAttempt, str], Any],
    is_context_window_error: Callable[[Exception], bool],
    ai_exception_details: Callable[[Exception], list[str]],
    clock: Callable[[], float],
    selected_model: str,
    selection_reason: str,
    low_confidence_model: str,
    on_context_compaction: Callable[[int], None] | None = None,
) -> SuggestGenerationAttemptResult:
    prompt_text = ""
    generation_result: Any | None = None
    suggest_compaction_level = 0
    request_started_at = clock()
    current_model = selected_model
    current_selection_reason = selection_reason
    try:
        for attempt_index, attempt in enumerate(attempts):
            prompt_text = prompt_builder(attempt)
            try:
                generation_result = generator(attempt, current_model)
                suggest_compaction_level = attempt_index
                break
            except Exception as exc:
                if is_context_window_error(exc) and attempt_index < len(attempts) - 1:
                    if low_confidence_model and current_model != low_confidence_model:
                        current_model = low_confidence_model
                        current_selection_reason = "suggest_context_compacted"
                    if on_context_compaction is not None:
                        on_context_compaction(attempt_index + 1)
                    continue
                raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ai_exception_details(exc)) from exc

    openai_ms = int((clock() - request_started_at) * 1000)
    if generation_result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=["Не удалось получить ответ модели после повторных попыток."],
        )
    return SuggestGenerationAttemptResult(
        generation_result=generation_result,
        prompt_text=prompt_text,
        selected_model=current_model,
        selection_reason=current_selection_reason,
        compaction_level=suggest_compaction_level,
        openai_ms=openai_ms,
    )


def run_suggest_validation_remediation(
    *,
    generation_result: Any,
    point3_context: Any,
    clean_text: Callable[[str], str],
    validate_generated_paragraph: Callable[[str, Any], Any],
    legacy_validation_error_codes: Callable[[tuple[str, ...]], tuple[str, ...]],
    retry_generator: Callable[[str], Any],
    ai_exception_details: Callable[[Exception], list[str]],
    build_safe_fallback_paragraph: Callable[[Any], str],
    apply_validation_remediation: Callable[[str, Any], Any],
    remediation_factory: Callable[[str, Any, int, bool], Any],
) -> SuggestValidationRemediationResult:
    text = str(getattr(generation_result, "text", "") or "")
    if not text:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=["Модель вернула пустой ответ. Попробуйте еще раз."],
        )
    cleaned = clean_text(text)
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=["Модель вернула некорректный формат ответа. Попробуйте еще раз."],
        )

    current_generation_result = generation_result
    validation_retry_count = 0
    validation_errors: tuple[str, ...] = ()
    initial_validation = validate_generated_paragraph(cleaned, point3_context)
    if initial_validation.blocker_codes:
        validation_errors = legacy_validation_error_codes(tuple(initial_validation.blocker_codes))
        try:
            retry_generation = retry_generator(", ".join(validation_errors))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ai_exception_details(exc)) from exc
        retry_text = clean_text(str(getattr(retry_generation, "text", "") or ""))
        if retry_text:
            current_generation_result = retry_generation
            cleaned = retry_text
            validation_retry_count = 1

    post_retry_validation = validate_generated_paragraph(cleaned, point3_context)
    if validation_retry_count > 0 and post_retry_validation.blocker_codes:
        fallback_text = build_safe_fallback_paragraph(point3_context)
        fallback_validation = validate_generated_paragraph(fallback_text, point3_context)
        remediation = remediation_factory(fallback_text, fallback_validation, 0, True)
    else:
        remediation = apply_validation_remediation(cleaned, point3_context)

    final_text = str(getattr(remediation, "text", "") or "")
    if not final_text:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=["Модель вернула пустой или некорректный текст после валидации."],
        )
    return SuggestValidationRemediationResult(
        generation_result=current_generation_result,
        cleaned_text=cleaned,
        remediation=remediation,
        validation_retry_count=validation_retry_count,
        validation_errors=validation_errors,
    )


def build_suggest_result(
    *,
    text: str,
    generation_id: str,
    contract_version: str,
    shadow: dict[str, object],
    telemetry_meta: dict[str, object],
    budget_status: str,
    budget_warnings: list[str],
    budget_policy: dict[str, object],
    retrieval_ms: int,
    openai_ms: int,
    total_suggest_ms: int,
    prompt_mode: str,
    retrieval_confidence: str,
    retrieval_context_mode: str,
    retrieval_profile: str,
    bundle_status: str,
    bundle_generated_at: str,
    bundle_fingerprint: str,
    selected_norms_count: int,
    policy_mode: str,
    policy_reason: str,
    valid_triggers_count: int,
    avg_trigger_confidence: float,
    remediation_retries: int,
    safe_fallback_used: bool,
    validation_status: str,
    validation_retry_count: int,
    validation_errors: tuple[str, ...],
    input_warning_codes: tuple[str, ...],
    protected_terms: tuple[str, ...],
    selected_model: str,
    selection_reason: str,
    guard_warning_codes: Sequence[str],
    validator_warning_codes: Sequence[str],
    point3_input_warning_codes: Sequence[str],
    context_compaction_level: int,
    factual_fallback_expanded_mode: str,
    guard_status: str,
) -> SuggestTextResult:
    warnings = list(
        dict.fromkeys(
            list(guard_warning_codes)
            + list(validator_warning_codes)
            + list(budget_warnings)
            + list(point3_input_warning_codes)
            + (["suggest_low_confidence_context"] if retrieval_context_mode == "low_confidence_context" else [])
            + (["suggest_no_context"] if retrieval_context_mode == "no_context" else [])
            + (["suggest_context_compacted"] if context_compaction_level > 0 else [])
            + (["suggest_output_remediated"] if remediation_retries > 0 else [])
            + (["suggest_safe_fallback_template"] if safe_fallback_used else [])
            + (["suggest_safe_factual_fallback"] if safe_fallback_used else [])
            + (["suggest_validation_retry"] if validation_retry_count > 0 else [])
            + (
                ["suggest_factual_fallback_expanded"]
                if policy_mode == factual_fallback_expanded_mode
                else ["suggest_legal_grounded"]
            )
        )
    )
    return SuggestTextResult(
        text=text,
        generation_id=generation_id,
        guard_status=guard_status,
        contract_version=contract_version,
        warnings=warnings,
        shadow=shadow,
        telemetry=telemetry_meta,
        budget_status=budget_status,
        budget_warnings=list(budget_warnings),
        budget_policy=budget_policy,
        retrieval_ms=retrieval_ms,
        openai_ms=openai_ms,
        total_suggest_ms=total_suggest_ms,
        prompt_mode=prompt_mode,
        retrieval_confidence=retrieval_confidence,
        retrieval_context_mode=retrieval_context_mode,
        retrieval_profile=retrieval_profile,
        bundle_status=bundle_status,
        bundle_generated_at=bundle_generated_at,
        bundle_fingerprint=bundle_fingerprint,
        selected_norms_count=selected_norms_count,
        policy_mode=policy_mode,
        policy_reason=policy_reason,
        valid_triggers_count=valid_triggers_count,
        avg_trigger_confidence=avg_trigger_confidence,
        remediation_retries=remediation_retries,
        safe_fallback_used=safe_fallback_used,
        validation_status=validation_status,
        validation_retry_count=validation_retry_count,
        validation_errors=validation_errors,
        input_warning_codes=input_warning_codes,
        protected_terms=protected_terms,
        selected_model=selected_model,
        selection_reason=selection_reason,
    )


def run_principal_scan(payload: PrincipalScanPayload, deps: PrincipalScanDeps) -> PrincipalScanResult:
    image_data_url = payload.image_data_url.strip()
    if not image_data_url.startswith("data:image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Загрузите изображение в формате PNG, JPG, WEBP или GIF."])
    try:
        data = deps.impl(image_data_url)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=deps.ai_exception_details(exc)) from exc
    try:
        result = PrincipalScanResult.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=[f"Модель вернула ответ в неожиданном формате: {exc}"]) from exc
    if not result.principal_address.strip():
        result.principal_address = "-"
    return result
