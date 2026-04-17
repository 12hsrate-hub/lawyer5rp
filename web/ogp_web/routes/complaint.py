from __future__ import annotations

from dataclasses import replace
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from ogp_web.dependencies import get_admin_metrics_store, get_feature_flag_service, get_user_store, requires_permission
from ogp_web.schemas import (
    AiFeedbackPayload,
    AiFeedbackResponse,
    ComplaintDraftPayload,
    ComplaintDraftResponse,
    ComplaintPayload,
    GenerateResponse,
    GeneratedDocumentHistoryResponse,
    GeneratedDocumentSnapshotResponse,
    LawQaPayload,
    DocumentVersionCitationsResponse,
    DocumentVersionProvenanceResponse,
    LawQaResponse,
    LawQaRunCitationsResponse,
    PrincipalScanPayload,
    PrincipalScanResult,
    RehabPayload,
    SuggestPayload,
    SuggestResponse,
)
from ogp_web.services import ai_service
from ogp_web.services.ai_pipeline.telemetry_meta import build_law_qa_metrics_meta, build_suggest_metrics_meta
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.services.complaint_runtime_service import (
    ComplaintRuntimeService,
    SuggestConcurrencyLimiter,
    build_heavy_ai_executor,
    env_positive_int,
)
from ogp_web.services.complaint_service import generate_bbcode_text, generate_rehab_bbcode_text
from ogp_web.services.complaint_draft_schema import normalize_complaint_draft
from ogp_web.services.complaint_service import build_generation_context_snapshot
from ogp_web.services.citation_service import save_answer_citations
from ogp_web.services.feature_flags import FeatureFlagService, RolloutContext
from ogp_web.services.generated_document_trace_service import (
    list_user_generated_document_history,
    require_user_generated_document_trace_bundle,
    resolve_generated_document_snapshot_payload_from_bundle,
)
from ogp_web.services.law_context_readiness_service import build_law_context_readiness_service
from ogp_web.services.pilot_runtime_adapter import (
    resolve_pilot_complaint_runtime_context,
    supports_pilot_runtime_adapter,
)
from ogp_web.services.provenance_service import resolve_document_version_trace_for_server
from ogp_web.services.regression_metrics import (
    build_rollout_labels,
    record_generation_latency,
    start_timer,
)
from ogp_web.services.section_capability_context_service import (
    ensure_section_permission,
    ensure_section_runtime_requirement,
    resolve_section_capability_context,
)
from ogp_web.services.validation_service import ValidationService
from ogp_web.services.retrieval_service import run_retrieval
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.document_repository import DocumentRepository
from ogp_web.storage.user_store import UserStore
from ogp_web.storage.validation_repository import ValidationRepository


router = APIRouter(tags=["complaint"])
LOGGER = logging.getLogger(__name__)


def _flatten_complaint_draft(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("document"), dict):
        document = payload.get("document") or {}
        draft = document.get("draft") if isinstance(document.get("draft"), dict) else {}
        result = str(document.get("result") or "")
        return {**draft, "result": result}
    return dict(payload)


def _env_positive_int(name: str, default: int) -> int:
    return env_positive_int(name, default)


SUGGEST_CONCURRENCY_LIMITER = SuggestConcurrencyLimiter(
    max_concurrency=_env_positive_int("OGP_SUGGEST_MAX_CONCURRENCY", 4),
    retry_after_seconds=_env_positive_int("OGP_SUGGEST_RETRY_AFTER_SECONDS", 3),
)


def _build_heavy_ai_executor() -> ThreadPoolExecutor | None:
    return build_heavy_ai_executor()


HEAVY_AI_EXECUTOR = _build_heavy_ai_executor()
COMPLAINT_RUNTIME_SERVICE = ComplaintRuntimeService(
    suggest_concurrency_limiter=SUGGEST_CONCURRENCY_LIMITER,
    heavy_ai_executor=HEAVY_AI_EXECUTOR,
)


def _runtime_service() -> ComplaintRuntimeService:
    COMPLAINT_RUNTIME_SERVICE.suggest_concurrency_limiter = SUGGEST_CONCURRENCY_LIMITER
    COMPLAINT_RUNTIME_SERVICE.heavy_ai_executor = HEAVY_AI_EXECUTOR
    return COMPLAINT_RUNTIME_SERVICE


async def _run_sync_io(func, /, *args, **kwargs):
    return await run_in_threadpool(partial(func, *args, **kwargs))


async def _run_ai_task(
    *,
    metrics_store: AdminMetricsStore,
    user: AuthUser,
    path: str,
    operation: str,
    func,
    use_heavy_executor: bool = False,
    **kwargs,
):
    return await _runtime_service().run_ai_task(
        metrics_store=metrics_store,
        user=user,
        path=path,
        operation=operation,
        func=func,
        use_heavy_executor=use_heavy_executor,
        threadpool_runner=run_in_threadpool,
        **kwargs,
    )
def _with_shadow_citations_policy(context_snapshot: dict[str, object]) -> dict[str, object]:
    return _runtime_service().with_shadow_citations_policy(context_snapshot)


def _build_complaint_generation_context_snapshot(
    *,
    store: UserStore,
    user: AuthUser,
    adapter_flag,
) -> dict[str, object]:
    return _runtime_service().build_complaint_generation_context_snapshot(
        store=store,
        user=user,
        adapter_flag=adapter_flag,
        legacy_snapshot_builder=lambda: dict(build_generation_context_snapshot(store, user, document_kind="complaint")),
        adapter_supported=lambda server_code, document_kind: supports_pilot_runtime_adapter(
            server_code=server_code,
            document_kind=document_kind,
        ),
        adapter_snapshot_resolver=resolve_pilot_complaint_runtime_context,
    )


def _validate_server_payload(store: UserStore, user: AuthUser, *, org: str = "", complaint_basis: str = "") -> None:
    _runtime_service().validate_server_payload(
        store,
        user,
        org=org,
        complaint_basis=complaint_basis,
    )


def _with_selected_server(user: AuthUser, server_code: str) -> AuthUser:
    return replace(user, server_code=str(server_code or "").strip().lower())


def _resolve_complaint_user(
    store: UserStore,
    user: AuthUser,
    *,
    require_runtime_pack: bool = False,
    route_path: str = "",
) -> tuple[AuthUser, object]:
    context = ensure_section_permission(
        resolve_section_capability_context(store, user.username, section_code="complaint")
    )
    if require_runtime_pack:
        context = ensure_section_runtime_requirement(context, route_path=route_path)
    return _with_selected_server(user, context.selected_server_code), context


def _resolve_law_qa_user(
    store: UserStore,
    user: AuthUser,
    *,
    server_code: str = "",
    require_runtime_pack: bool = False,
    route_path: str = "",
) -> tuple[AuthUser, object]:
    context = ensure_section_permission(
        resolve_section_capability_context(
            store,
            user.username,
            section_code="law_qa",
            explicit_server_code=server_code,
        )
    )
    if require_runtime_pack:
        context = ensure_section_runtime_requirement(context, route_path=route_path)
    return _with_selected_server(user, context.selected_server_code), context


def _require_law_context_readiness(
    store: UserStore,
    *,
    server_code: str,
    requested_law_version_id: int | None = None,
) -> dict[str, object]:
    readiness = build_law_context_readiness_service(backend=getattr(store, "backend", None)).get_readiness(
        server_code=server_code,
        requested_law_version_id=requested_law_version_id,
    )
    payload = readiness.to_payload()
    if not readiness.is_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=[
                f"Law context is not ready for server '{server_code}': {readiness.reason_code}.",
                readiness.reason_detail,
            ],
        )
    return payload


@router.get("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def get_complaint_draft(
    document_type: str = "complaint",
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ComplaintDraftResponse:
    effective_user, context = _resolve_complaint_user(store, user)
    draft = store.get_complaint_draft(
        effective_user.username,
        server_code=effective_user.server_code,
        document_type=document_type,
    )
    metadata = draft.get("_meta", {}) if isinstance(draft.get("_meta"), dict) else {}
    normalized = normalize_complaint_draft(
        _flatten_complaint_draft(draft.get("draft", {})),
        config=context.server_config,
    )
    return ComplaintDraftResponse(
        draft=normalized.draft,
        updated_at=str(draft.get("updated_at", "") or ""),
        bundle_version=str(metadata.get("bundle_version", "") or ""),
        schema_hash=str(metadata.get("schema_hash", "") or ""),
        status=str(metadata.get("status", "draft") or "draft"),
        allowed_actions=list(metadata.get("allowed_actions", []) or []),
        document_type=str(draft.get("document_type", document_type) or "complaint"),
        server_id=str(draft.get("server_id", effective_user.server_code) or ""),
        message="Черновик жалобы загружен.",
    )


@router.put("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def save_complaint_draft(
    payload: ComplaintDraftPayload,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ComplaintDraftResponse:
    effective_user, context = _resolve_complaint_user(store, user)
    normalized = normalize_complaint_draft(
        _flatten_complaint_draft(payload.draft),
        config=context.server_config,
    )
    if normalized.unknown_keys:
        unknown = ", ".join(normalized.unknown_keys)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[f"Unknown complaint draft keys: {unknown}. Supported semantic keys are configured per server."],
        )
    draft_with_meta = {
        "draft": normalized.draft,
        "_meta": {
            "bundle_version": payload.bundle_version,
            "schema_hash": payload.schema_hash,
            "status": payload.status,
            "allowed_actions": payload.allowed_actions,
        },
    }
    draft = store.save_complaint_draft(
        effective_user.username,
        draft_with_meta,
        server_code=effective_user.server_code,
        document_type=payload.document_type,
    )
    metadata = draft.get("_meta", {}) if isinstance(draft.get("_meta"), dict) else {}
    metrics_store.log_event(
        event_type="complaint_draft_saved",
        username=effective_user.username,
        path="/api/complaint-draft",
        method="PUT",
        status_code=200,
        resource_units=len(str(normalized.draft or {})),
        meta={
            "keys_count": len(normalized.draft or {}),
            "server_code": effective_user.server_code,
            "draft_actions": normalized.actions or {},
        },
    )
    return ComplaintDraftResponse(
        draft=_flatten_complaint_draft(draft.get("draft", {})),
        updated_at=str(draft.get("updated_at", "") or ""),
        bundle_version=str(metadata.get("bundle_version", "") or ""),
        schema_hash=str(metadata.get("schema_hash", "") or ""),
        status=str(metadata.get("status", "draft") or "draft"),
        allowed_actions=list(metadata.get("allowed_actions", []) or []),
        document_type=str(draft.get("document_type", payload.document_type) or "complaint"),
        server_id=str(draft.get("server_id", effective_user.server_code) or ""),
        message="Черновик жалобы сохранён.",
    )


@router.delete("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def clear_complaint_draft(
    document_type: str = "complaint",
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ComplaintDraftResponse:
    effective_user, _ = _resolve_complaint_user(store, user)
    store.clear_complaint_draft(
        effective_user.username,
        server_code=effective_user.server_code,
        document_type=document_type,
    )
    metrics_store.log_event(
        event_type="complaint_draft_cleared",
        username=effective_user.username,
        path="/api/complaint-draft",
        method="DELETE",
        status_code=200,
        meta={"server_code": effective_user.server_code},
    )
    return ComplaintDraftResponse(
        draft={},
        updated_at="",
        status="draft",
        document_type=document_type,
        server_id=effective_user.server_code,
        message="Черновик жалобы очищен.",
    )


@router.post("/api/generate", response_model=GenerateResponse)
async def generate(
    payload: ComplaintPayload,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    flag_service: FeatureFlagService = Depends(get_feature_flag_service),
) -> GenerateResponse:
    effective_user, _ = _resolve_complaint_user(
        store,
        user,
        require_runtime_pack=True,
        route_path="/api/generate",
    )
    started_at = start_timer()
    docs_flag = flag_service.evaluate(
        flag="documents_v2",
        context=RolloutContext(username=effective_user.username, server_id=effective_user.server_code),
    )
    validation_flag = flag_service.evaluate(
        flag="validation_gate_v1",
        context=RolloutContext(username=effective_user.username, server_id=effective_user.server_code),
    )
    adapter_flag = flag_service.evaluate(
        flag="pilot_runtime_adapter_v1",
        context=RolloutContext(username=effective_user.username, server_id=effective_user.server_code),
    )
    _validate_server_payload(store, effective_user, org=payload.org)
    context_snapshot = _with_shadow_citations_policy(
        _build_complaint_generation_context_snapshot(store=store, user=effective_user, adapter_flag=adapter_flag)
    )
    bbcode = generate_bbcode_text(store, payload, effective_user)
    bridge_result = _runtime_service().persist_generation_result(
        store=store,
        user=effective_user,
        document_kind="complaint",
        payload=payload.model_dump(),
        result_text=bbcode,
        context_snapshot=context_snapshot,
    )
    document_id = int(bridge_result.generated_document_id)
    _runtime_service().maybe_validate_generated_document(
        store=store,
        metrics_store=metrics_store,
        user=effective_user,
        path="/api/generate",
        validation_flag=validation_flag,
        bridge_result=bridge_result,
    )
    metrics_store.log_event(
        event_type="complaint_generated",
        username=effective_user.username,
        path="/api/generate",
        method="POST",
        status_code=200,
        resource_units=len(bbcode),
        meta={
            "server_code": effective_user.server_code,
            "event_dt": payload.event_dt,
            "org": payload.org,
            "subject_names": payload.subject_names,
            "result_chars": len(bbcode),
            "description_chars": len(payload.situation_description or ""),
        },
    )
    record_generation_latency(
        metrics_store,
        username=effective_user.username,
        path="/api/generate",
        method="POST",
        labels=build_rollout_labels(
            flag="documents_v2",
            rollout_mode=docs_flag.mode.value,
            cohort=docs_flag.cohort.value,
            server_id=effective_user.server_code,
            flow_type="generate",
            status="success",
        ),
        started_at=started_at,
    )
    return GenerateResponse(bbcode=bbcode, generated_document_id=document_id)


@router.post("/api/generate-rehab", response_model=GenerateResponse)
async def generate_rehab(
    payload: RehabPayload,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    feature_flag_service: FeatureFlagService = Depends(get_feature_flag_service),
) -> GenerateResponse:
    validation_flag = feature_flag_service.evaluate(
        flag="validation_gate_v1",
        context=RolloutContext(username=user.username, server_id=user.server_code),
    )
    context_snapshot = _with_shadow_citations_policy(build_generation_context_snapshot(store, user, document_kind="rehab"))
    bbcode = generate_rehab_bbcode_text(store, payload, user)
    bridge_result = _runtime_service().persist_generation_result(
        store=store,
        user=user,
        document_kind="rehab",
        payload=payload.model_dump(),
        result_text=bbcode,
        context_snapshot=context_snapshot,
    )
    document_id = int(bridge_result.generated_document_id)
    _runtime_service().maybe_validate_generated_document(
        store=store,
        metrics_store=metrics_store,
        user=user,
        path="/api/generate-rehab",
        validation_flag=validation_flag,
        bridge_result=bridge_result,
    )
    metrics_store.log_event(
        event_type="rehab_generated",
        username=user.username,
        path="/api/generate-rehab",
        method="POST",
        status_code=200,
        resource_units=len(bbcode),
        meta={
            "server_code": user.server_code,
            "principal_name": payload.principal_name,
            "served_seven_days": payload.served_seven_days,
            "result_chars": len(bbcode),
        },
    )
    return GenerateResponse(bbcode=bbcode, generated_document_id=document_id)


@router.get("/api/generated-documents/history", response_model=GeneratedDocumentHistoryResponse)
async def generated_documents_history(
    limit: int = 30,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
) -> GeneratedDocumentHistoryResponse:
    items = list_user_generated_document_history(store=store, username=user.username, limit=limit)
    return GeneratedDocumentHistoryResponse(items=items)


@router.get("/api/generated-documents/{document_id}/snapshot", response_model=GeneratedDocumentSnapshotResponse)
async def generated_document_snapshot(
    document_id: int,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
) -> GeneratedDocumentSnapshotResponse:
    bundle = require_user_generated_document_trace_bundle(
        store=store,
        username=user.username,
        legacy_generated_document_id=document_id,
    )
    return GeneratedDocumentSnapshotResponse(
        **resolve_generated_document_snapshot_payload_from_bundle(store=store, bundle=bundle)
    )


@router.post("/api/ai/suggest", response_model=SuggestResponse)
async def suggest(
    payload: SuggestPayload,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> SuggestResponse:
    _validate_server_payload(store, user, org=payload.org, complaint_basis=payload.complaint_basis)
    _runtime_service().ensure_suggest_capacity(
        metrics_store=metrics_store,
        user=user,
        complaint_basis=payload.complaint_basis,
        main_focus=payload.main_focus,
    )
    try:
        result = await _run_ai_task(
            metrics_store=metrics_store,
            user=user,
            path="/api/ai/suggest",
            operation="suggest_text_details",
            func=ai_service.suggest_text_details,
            use_heavy_executor=True,
            payload=payload,
            server_code=user.server_code,
        )
    finally:
        SUGGEST_CONCURRENCY_LIMITER.release()
    result_selected_model = str(getattr(result, "selected_model", "") or getattr(result, "telemetry", {}).get("model") or "").strip()
    result_selection_reason = str(getattr(result, "selection_reason", "") or "").strip()
    metrics_store.log_event(
        event_type="ai_suggest",
        username=user.username,
        path="/api/ai/suggest",
        method="POST",
        status_code=200,
        resource_units=len(payload.raw_desc or "") + len(result.text),
        meta={
            "server_code": user.server_code,
            "model": result_selected_model,
            "selected_model": result_selected_model,
            "selection_reason": result_selection_reason,
            "complaint_basis": payload.complaint_basis,
            "main_focus": payload.main_focus,
            "law_version_id": payload.law_version_id,
            "template_version_id": payload.template_version_id,
            "input_chars": len(payload.raw_desc or ""),
            "output_chars": len(result.text),
        },
    )
    metrics_store.log_ai_generation(
        username=user.username,
        server_code=user.server_code,
        flow="suggest",
        generation_id=result.generation_id,
        path="/api/ai/suggest",
        meta=build_suggest_metrics_meta(
            payload=payload,
            result=result,
            server_code=user.server_code,
            short_text_hash=ai_service.short_text_hash,
            mask_text_preview=ai_service.mask_text_preview,
        ),
    )
    return SuggestResponse(
        text=result.text,
        generation_id=result.generation_id,
        guard_status=result.guard_status,
        contract_version=result.contract_version,
        warnings=result.warnings,
    )


@router.post("/api/ai/extract-principal", response_model=PrincipalScanResult)
async def extract_principal(
    payload: PrincipalScanPayload,
    user: AuthUser = Depends(requires_permission()),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> PrincipalScanResult:
    result = await _run_ai_task(
        metrics_store=metrics_store,
        user=user,
        path="/api/ai/extract-principal",
        operation="extract_principal_scan",
        func=ai_service.extract_principal_scan,
        use_heavy_executor=True,
        payload=payload,
    )
    metrics_store.log_event(
        event_type="ai_extract_principal",
        username=user.username,
        path="/api/ai/extract-principal",
        method="POST",
        status_code=200,
        resource_units=len(payload.image_data_url or ""),
        meta={
            "server_code": user.server_code,
            "image_data_chars": len(payload.image_data_url or ""),
            "confidence": result.confidence,
            "missing_fields_count": len(result.missing_fields),
        },
    )
    return result
@router.post("/api/ai/law-qa-test", response_model=LawQaResponse)
async def law_qa_test(
    payload: LawQaPayload,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    flag_service: FeatureFlagService = Depends(get_feature_flag_service),
) -> LawQaResponse:
    try:
        started_at = start_timer()
        requested_server_code = str(payload.server_code or "").strip()
        if not requested_server_code and not str(user.server_code or "").strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["server_code is required."])
        effective_user, _ = _resolve_law_qa_user(
            store,
            user,
            server_code=requested_server_code,
            require_runtime_pack=True,
            route_path="/api/ai/law-qa-test",
        )
        effective_server_code = effective_user.server_code
        law_context_readiness = _require_law_context_readiness(
            store,
            server_code=effective_server_code,
            requested_law_version_id=payload.law_version_id,
        )
        payload = payload.model_copy(
            update={
                "server_code": effective_server_code,
                "law_version_id": law_context_readiness.get("active_law_version_id") or payload.law_version_id,
            }
        )
        result = await _run_ai_task(
            metrics_store=metrics_store,
            user=effective_user,
            path="/api/ai/law-qa-test",
            operation="answer_law_question_details",
            func=ai_service.answer_law_question_details,
            use_heavy_executor=True,
            payload=payload,
        )
        result_selected_model = str(getattr(result, "selected_model", "") or getattr(result, "telemetry", {}).get("model") or "").strip()
        result_selection_reason = str(getattr(result, "selection_reason", "") or "").strip()
        result_requested_model = str(getattr(result, "requested_model", "") or payload.model or "").strip()
        selected_norms = list(getattr(result, "selected_norms", []) or [])
        raw_citations = _runtime_service().law_qa_selected_norms_to_citations(
            store=store,
            server_id=effective_server_code,
            law_version_id=payload.law_version_id,
            selected_norms=selected_norms,
        )
        citations_flag = flag_service.evaluate(
            flag="citations_required",
            context=RolloutContext(username=effective_user.username, server_id=effective_server_code),
        )
        response_warnings = _runtime_service().resolve_law_qa_response_warnings(
            warnings=list(getattr(result, "warnings", []) or []),
            citations_flag=citations_flag,
            raw_citations=raw_citations,
        )
        retrieval, law_qa_run_id, citations = _runtime_service().persist_law_qa_artifacts(
            store=store,
            user=effective_user,
            effective_server_code=effective_server_code,
            question=payload.question,
            law_version_id=payload.law_version_id,
            answer_text=result.text,
            used_sources=list(getattr(result, "used_sources", []) or []),
            raw_citations=raw_citations,
            retrieval_runner=run_retrieval,
            citation_saver=save_answer_citations,
        )
        metrics_store.log_event(
            event_type="ai_law_qa_test",
            username=effective_user.username,
            path="/api/ai/law-qa-test",
            method="POST",
            status_code=200,
            resource_units=len(payload.question or "") + len(result.text),
            meta={
                "server_code": effective_server_code,
                "model": result_selected_model or ai_service.get_default_law_qa_model(),
                "selected_model": result_selected_model,
                "selection_reason": result_selection_reason,
                "requested_model": result_requested_model,
                "indexed_documents": result.indexed_documents,
                "used_sources_count": len(result.used_sources),
                "retrieval_confidence": result.retrieval_confidence,
                "selected_norms_count": len(result.selected_norms),
                "max_answer_chars": payload.max_answer_chars,
                "law_version_id": payload.law_version_id,
                "law_context_mode": law_context_readiness.get("mode"),
                "projection_run_id": law_context_readiness.get("projection", {}).get("run_id"),
            },
        )
        metrics_store.log_ai_generation(
            username=effective_user.username,
            server_code=effective_server_code,
            flow="law_qa",
            generation_id=result.generation_id,
            path="/api/ai/law-qa-test",
            meta=build_law_qa_metrics_meta(
                payload=payload,
                result=result,
                used_sources=result.used_sources,
                short_text_hash=ai_service.short_text_hash,
                mask_text_preview=ai_service.mask_text_preview,
            ),
        )
        try:
            validation_flag = flag_service.evaluate(
                flag="validation_gate_v1",
                context=RolloutContext(username=effective_user.username, server_id=effective_server_code),
            )
            _runtime_service().maybe_validate_law_qa_result(
                store=store,
                metrics_store=metrics_store,
                user=effective_user,
                effective_server_code=effective_server_code,
                question=payload.question,
                result=result,
                validation_flag=validation_flag,
            )
        except Exception:
            if str(os.getenv("OGP_VALIDATION_LAW_QA_STRICT", "0") or "").strip() in {"1", "true", "yes", "on"}:
                raise
        record_generation_latency(
            metrics_store,
            username=effective_user.username,
            path="/api/ai/law-qa-test",
            method="POST",
            labels=build_rollout_labels(
                flag="citations_required",
                rollout_mode=citations_flag.mode.value,
                cohort=citations_flag.cohort.value,
                server_id=effective_server_code,
                flow_type="law_qa",
                status="success",
            ),
            started_at=started_at,
        )

        return LawQaResponse(
            text=result.text,
            generation_id=result.generation_id,
            used_sources=result.used_sources,
            indexed_documents=result.indexed_documents,
            retrieval_confidence=result.retrieval_confidence,
            retrieval_profile=result.retrieval_profile,
            guard_status=result.guard_status,
            contract_version=result.contract_version,
            bundle_status=result.bundle_status,
            bundle_generated_at=result.bundle_generated_at,
            bundle_fingerprint=result.bundle_fingerprint,
            law_version_id=payload.law_version_id,
            warnings=response_warnings,
            shadow=result.shadow,
            selected_norms=result.selected_norms,
            retrieval_run_id=retrieval.retrieval_run_id,
            law_qa_run_id=law_qa_run_id,
            citations=citations,
        )
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("law_qa_test_failed user=%s server=%s", user.username, user.server_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=[f"Law QA request failed: {type(exc).__name__}."],
        ) from exc


@router.get("/api/document-versions/{version_id}/citations", response_model=DocumentVersionCitationsResponse)
async def document_version_citations(
    version_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> DocumentVersionCitationsResponse:
    _ = user
    items = store.get_document_version_citations(document_version_id=version_id, server_id=user.server_code)
    return DocumentVersionCitationsResponse(items=items)


@router.get("/api/document-versions/{version_id}/provenance", response_model=DocumentVersionProvenanceResponse)
async def document_version_provenance(
    version_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> DocumentVersionProvenanceResponse:
    try:
        payload = resolve_document_version_trace_for_server(
            store=store,
            version_id=version_id,
            server_id=user.server_code,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для документа."])
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Document version not found."])
    return DocumentVersionProvenanceResponse(**payload)


@router.get("/api/law-qa-runs/{run_id}/citations", response_model=LawQaRunCitationsResponse)
async def law_qa_run_citations(
    run_id: int,
    user: AuthUser = Depends(requires_permission("court_claims")),
    store: UserStore = Depends(get_user_store),
) -> LawQaRunCitationsResponse:
    _ = user
    items = store.get_law_qa_run_citations(law_qa_run_id=run_id, server_id=user.server_code)
    return LawQaRunCitationsResponse(items=items)


@router.post("/api/ai/feedback", response_model=AiFeedbackResponse)
async def ai_feedback(
    payload: AiFeedbackPayload,
    user: AuthUser = Depends(requires_permission()),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> AiFeedbackResponse:
    generation_id = str(payload.generation_id or "").strip()
    flow = str(payload.flow or "").strip().lower()
    if not generation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["generation_id is required."],
        )
    if flow not in {"law_qa", "suggest"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["flow must be law_qa or suggest."],
        )

    normalized_issues = list(ai_service.normalize_ai_feedback_issues(payload.issues))
    if not normalized_issues and not str(payload.note or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Provide at least one issue or a short note."],
        )

    feedback_id = f"fb_{generation_id[:8]}"
    await _run_sync_io(
        metrics_store.log_ai_feedback,
        username=user.username,
        server_code=user.server_code,
        generation_id=generation_id,
        flow=flow,
        normalized_issues=normalized_issues,
        note=payload.note,
        expected_reference=payload.expected_reference,
        helpful=payload.helpful,
    )
    return AiFeedbackResponse(
        feedback_id=feedback_id,
        generation_id=generation_id,
        flow=flow,
        normalized_issues=normalized_issues,
        message="Feedback recorded.",
    )
