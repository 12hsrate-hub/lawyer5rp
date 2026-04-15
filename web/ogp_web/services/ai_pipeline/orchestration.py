from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from fastapi import HTTPException, status

from ogp_web.schemas import LawQaPayload, PrincipalScanPayload, PrincipalScanResult, SuggestPayload
from ogp_web.services.ai_pipeline.interfaces import LawQaAnswerResult, SuggestTextResult


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
class LawQaGenerationAttemptResult:
    text: str
    usage: Any
    prompt: str
    model_name: str
    selection_reason: str
    compaction_level: int


@dataclass(frozen=True)
class LawQaRuntimeContext:
    question: str
    requested_model: str
    retrieval_result: Any
    server_config: Any
    ai_context: Any
    model_name: str
    selection_reason: str
    low_confidence_model: str
    shadow: dict[str, object]
    context_attempts: tuple[Sequence[str], ...]


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


def resolve_law_qa_runtime_context(
    *,
    payload: LawQaPayload,
    default_server_code: str,
    retrieve_law_context: Callable[..., Any],
    resolve_server_config: Callable[..., Any],
    resolve_server_ai_context_settings: Callable[..., Any],
    select_law_qa_model: Callable[..., Any],
    get_flow_model: Callable[[str, str, str], str],
    build_shadow_comparison: Callable[..., Any],
    server_feature_enabled: Callable[[Any, str], bool],
    build_law_qa_context_blocks: Callable[[Any], list[str]],
    build_law_qa_context_blocks_limited: Callable[..., list[str]],
) -> LawQaRuntimeContext:
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Введите вопрос для анализа."],
        )

    requested_model = str(payload.model or "").strip()
    retrieval_result = retrieve_law_context(
        server_code=payload.server_code or default_server_code,
        query=question,
        excerpt_chars=1800,
        profile="law_qa",
        law_version_id=payload.law_version_id,
    )
    if not retrieval_result.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[
                "Для выбранного сервера не настроены источники законов.",
            ],
        )
    if not retrieval_result.indexed_chunk_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[
                "Не удалось загрузить законы для выбранного сервера. Проверьте настройку law base.",
            ],
        )

    server_config = resolve_server_config(server_code=retrieval_result.server_code)
    selection = select_law_qa_model(
        question=question,
        retrieval_confidence=retrieval_result.confidence,
        server_config=server_config,
    )
    ai_context = resolve_server_ai_context_settings(server_code=retrieval_result.server_code)
    model_name = selection.model_name
    selection_reason = selection.reason
    low_confidence_model = get_flow_model("law_qa", "low_confidence_model", "gpt-5.4")
    shadow = build_shadow_comparison(
        enabled=False,
        profile="",
        primary_matches=retrieval_result.matches,
        shadow_matches=(),
    )
    if server_feature_enabled(server_config, "legal_pipeline_shadow"):
        shadow_profile = ai_context.shadow_law_qa_profile
        if shadow_profile and shadow_profile != retrieval_result.profile:
            shadow_result = retrieve_law_context(
                server_code=retrieval_result.server_code,
                query=question,
                excerpt_chars=1800,
                profile=shadow_profile,
                law_version_id=payload.law_version_id,
            )
            shadow = build_shadow_comparison(
                enabled=True,
                profile=shadow_profile,
                primary_matches=retrieval_result.matches,
                shadow_matches=shadow_result.matches,
            )

    context_attempts = (
        build_law_qa_context_blocks(retrieval_result),
        build_law_qa_context_blocks_limited(retrieval_result, max_blocks=8, max_excerpt_chars=900),
        build_law_qa_context_blocks_limited(retrieval_result, max_blocks=5, max_excerpt_chars=650),
        build_law_qa_context_blocks_limited(retrieval_result, max_blocks=3, max_excerpt_chars=420),
        build_law_qa_context_blocks_limited(retrieval_result, max_blocks=2, max_excerpt_chars=280),
    )
    return LawQaRuntimeContext(
        question=question,
        requested_model=requested_model,
        retrieval_result=retrieval_result,
        server_config=server_config,
        ai_context=ai_context,
        model_name=model_name,
        selection_reason=selection_reason,
        low_confidence_model=low_confidence_model,
        shadow=shadow,
        context_attempts=context_attempts,
    )


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


def run_law_qa_generation_attempts(
    *,
    context_attempts: Sequence[Sequence[str]],
    prompt_builder: Callable[[Sequence[str], str], str],
    request_generator: Callable[[str, str], tuple[str, Any]],
    is_context_window_error: Callable[[Exception], bool],
    ai_exception_details: Callable[[Exception], list[str]],
    logger_warning: Callable[[str, str, int], None] | None,
    selected_model: str,
    selection_reason: str,
    low_confidence_model: str,
) -> LawQaGenerationAttemptResult:
    current_model = selected_model
    current_selection_reason = selection_reason
    prompt = ""
    text = ""
    usage: Any = None
    compaction_level = 0
    try:
        for attempt_index, context_blocks in enumerate(context_attempts):
            if not context_blocks:
                continue
            prompt = prompt_builder(context_blocks, current_model)
            try:
                text, usage = request_generator(prompt, current_model)
                compaction_level = attempt_index
                break
            except HTTPException:
                raise
            except Exception as exc:
                if is_context_window_error(exc) and attempt_index < len(context_attempts) - 1:
                    if low_confidence_model and current_model != low_confidence_model:
                        current_model = low_confidence_model
                        current_selection_reason = "law_qa_context_compacted"
                    if logger_warning is not None:
                        logger_warning(
                            "Law QA prompt exceeded context window for model %s; retrying with compact context level=%s",
                            current_model,
                            attempt_index + 1,
                        )
                    continue
                raise
        if not text:
            raise RuntimeError("Law QA generation failed without response text after context retries.")
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ai_exception_details(exc)) from exc

    return LawQaGenerationAttemptResult(
        text=text,
        usage=usage,
        prompt=prompt,
        model_name=current_model,
        selection_reason=current_selection_reason,
        compaction_level=compaction_level,
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


def finalize_suggest_result(
    *,
    generation_id: str,
    contract_version: str,
    shadow: dict[str, object],
    generation_result: Any,
    remediation: Any,
    validation_retry_count: int,
    validation_errors: tuple[str, ...],
    selected_model: str,
    selection_reason: str,
    suggest_compaction_level: int,
    suggest_prompt_mode: str,
    suggest_context: Any,
    point3_context: Any,
    prompt_text: str,
    final_text: str,
    retrieval_ms: int,
    openai_ms: int,
    total_suggest_ms: int,
    build_ai_telemetry: Callable[..., Any],
    evaluate_budget: Callable[..., Any],
    telemetry_to_meta: Callable[[Any], dict[str, object]],
    policy_to_meta: Callable[[Any], dict[str, object]],
    guard_suggest_answer: Callable[[str], Any],
    legacy_validation_error_codes: Callable[[tuple[str, ...]], tuple[str, ...]],
    factual_fallback_expanded_mode: str,
) -> SuggestTextResult:
    telemetry = build_ai_telemetry(
        model_name=selected_model,
        prompt_text=prompt_text,
        output_text=final_text,
        usage=generation_result.usage,
        latency_ms=openai_ms,
        cache_hit=generation_result.cache_hit,
    )
    budget_assessment = evaluate_budget(flow="suggest", telemetry=telemetry)
    validation_result = remediation.validation
    guard_result = guard_suggest_answer(text=final_text)
    combined_guard_status = "fail" if validation_result.blockers else "warn" if (
        guard_result.status == "warn" or validation_result.status == "warn"
    ) else "pass"
    current_validation_errors = validation_errors
    if not current_validation_errors:
        current_validation_errors = legacy_validation_error_codes(tuple(validation_result.blocker_codes))
    validation_status = validation_result.status
    if remediation.safe_fallback_used:
        validation_status = "fallback"
    elif validation_retry_count > 0:
        validation_status = "pass_after_retry"
    telemetry_meta = telemetry_to_meta(telemetry)
    telemetry_meta.update(
        {
            "attempt_path": generation_result.attempt_path,
            "attempt_duration_ms": generation_result.attempt_duration_ms,
            "route_policy": generation_result.route_policy,
            "selected_model": selected_model,
            "selection_reason": selection_reason,
            "context_compaction_level": suggest_compaction_level,
            "context_compacted": bool(suggest_compaction_level > 0),
            "retrieval_context_mode": suggest_context.retrieval_context_mode,
            "policy_mode": point3_context.policy_decision.mode,
            "policy_reason": point3_context.policy_decision.reason,
            "valid_triggers_count": point3_context.policy_decision.valid_triggers_count,
            "avg_trigger_confidence": point3_context.policy_decision.avg_confidence,
            "validator_warning_codes": list(validation_result.warning_codes),
            "validator_info_codes": list(validation_result.info_codes),
            "validation_errors": list(current_validation_errors),
            "validation_retry_count": validation_retry_count,
            "validation_status": validation_status,
            "input_warning_codes": list(point3_context.input_audit.warning_codes),
            "protected_terms": list(point3_context.input_audit.protected_terms),
            "remediation_retries": remediation.retries_used,
            "safe_fallback_used": remediation.safe_fallback_used,
        }
    )
    return build_suggest_result(
        text=final_text,
        generation_id=generation_id,
        contract_version=contract_version,
        shadow=shadow,
        telemetry_meta=telemetry_meta,
        budget_status=budget_assessment.status,
        budget_warnings=list(budget_assessment.warnings),
        budget_policy=policy_to_meta(budget_assessment.policy),
        retrieval_ms=retrieval_ms,
        openai_ms=openai_ms,
        total_suggest_ms=total_suggest_ms,
        prompt_mode=suggest_prompt_mode,
        retrieval_confidence=suggest_context.retrieval_confidence,
        retrieval_context_mode=suggest_context.retrieval_context_mode,
        retrieval_profile=suggest_context.retrieval_profile,
        bundle_status=suggest_context.bundle_status,
        bundle_generated_at=suggest_context.bundle_generated_at,
        bundle_fingerprint=suggest_context.bundle_fingerprint,
        selected_norms_count=suggest_context.selected_norms_count,
        policy_mode=point3_context.policy_decision.mode,
        policy_reason=point3_context.policy_decision.reason,
        valid_triggers_count=point3_context.policy_decision.valid_triggers_count,
        avg_trigger_confidence=point3_context.policy_decision.avg_confidence,
        remediation_retries=remediation.retries_used,
        safe_fallback_used=remediation.safe_fallback_used,
        validation_status=validation_status,
        validation_retry_count=validation_retry_count,
        validation_errors=current_validation_errors,
        input_warning_codes=point3_context.input_audit.warning_codes,
        protected_terms=point3_context.input_audit.protected_terms,
        selected_model=selected_model,
        selection_reason=selection_reason,
        guard_warning_codes=guard_result.warning_codes,
        validator_warning_codes=validation_result.warning_codes,
        point3_input_warning_codes=point3_context.input_audit.warning_codes,
        context_compaction_level=suggest_compaction_level,
        factual_fallback_expanded_mode=factual_fallback_expanded_mode,
        guard_status=combined_guard_status,
    )


def finalize_law_qa_result(
    *,
    text: str,
    generation_id: str,
    contract_version: str,
    retrieval_result: Any,
    shadow: dict[str, object],
    model_name: str,
    selection_reason: str,
    requested_model: str,
    compaction_level: int,
    prompt: str,
    usage: Any,
    latency_ms: int,
    max_answer_chars: int,
    build_ai_telemetry: Callable[..., Any],
    evaluate_budget: Callable[..., Any],
    unique_sources: Callable[[Any], Sequence[str]],
    guard_law_qa_answer: Callable[..., Any],
    telemetry_to_meta: Callable[[Any], dict[str, object]],
    policy_to_meta: Callable[[Any], dict[str, object]],
    strip_law_qa_source_urls: Callable[[str], str],
    normalize_law_qa_text_formatting: Callable[[str], str],
    build_selected_norms: Callable[[Any], list[dict[str, object]]],
) -> LawQaAnswerResult:
    sanitized_text = strip_law_qa_source_urls(text)
    sanitized_text = normalize_law_qa_text_formatting(sanitized_text)
    limited = sanitized_text[:max_answer_chars].strip()
    telemetry = build_ai_telemetry(
        model_name=model_name,
        prompt_text=prompt,
        output_text=limited,
        usage=usage,
        latency_ms=latency_ms,
        cache_hit=False,
    )
    budget_assessment = evaluate_budget(flow="law_qa", telemetry=telemetry)
    used_sources = list(unique_sources(retrieval_result))
    guard_result = guard_law_qa_answer(
        text=limited,
        allowed_source_urls=used_sources,
        bundle_health=retrieval_result.bundle_health,
    )
    telemetry_meta = telemetry_to_meta(telemetry)
    telemetry_meta.update(
        {
            "selected_model": model_name,
            "selection_reason": selection_reason,
            "requested_model": requested_model,
            "context_compaction_level": compaction_level,
            "context_compacted": bool(compaction_level > 0),
        }
    )
    warnings = list(
        dict.fromkeys(
            list(retrieval_result.bundle_health.warnings)
            + list(guard_result.warning_codes)
            + list(budget_assessment.warnings)
            + (["law_qa_context_compacted"] if compaction_level > 0 else [])
        )
    )
    return LawQaAnswerResult(
        text=limited,
        generation_id=generation_id,
        used_sources=used_sources,
        indexed_documents=retrieval_result.indexed_chunk_count,
        retrieval_confidence=retrieval_result.confidence,
        retrieval_profile=retrieval_result.profile,
        guard_status=guard_result.status,
        contract_version=contract_version,
        bundle_status=retrieval_result.bundle_health.status,
        bundle_generated_at=retrieval_result.bundle_health.generated_at,
        bundle_fingerprint=retrieval_result.bundle_health.fingerprint,
        warnings=warnings,
        shadow=shadow,
        selected_norms=build_selected_norms(retrieval_result),
        telemetry=telemetry_meta,
        budget_status=budget_assessment.status,
        budget_warnings=list(budget_assessment.warnings),
        budget_policy=policy_to_meta(budget_assessment.policy),
        selected_model=model_name,
        selection_reason=selection_reason,
        requested_model=requested_model,
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
