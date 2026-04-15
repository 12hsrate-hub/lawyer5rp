from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from threading import BoundedSemaphore, Lock
from time import monotonic

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
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.services.complaint_service import generate_bbcode_text, generate_rehab_bbcode_text
from ogp_web.services.complaint_draft_schema import normalize_complaint_draft
from ogp_web.services.complaint_service import build_generation_context_snapshot
from ogp_web.services.citation_service import save_answer_citations
from ogp_web.services.feature_flags import FeatureFlagService, RolloutContext
from ogp_web.services.generation_orchestrator import GenerationOrchestrator
from ogp_web.services.generated_document_trace_service import (
    build_store_provenance_service,
    list_user_generated_document_history,
    resolve_generated_document_provenance_payload,
    resolve_user_generated_document_trace_bundle,
)
from ogp_web.services.pilot_runtime_adapter import (
    resolve_pilot_complaint_runtime_context,
    supports_pilot_runtime_adapter,
)
from ogp_web.services.regression_metrics import (
    build_rollout_labels,
    record_async_queue_lag,
    record_generation_latency,
    record_validation_fail_rate,
    start_timer,
)
from ogp_web.services.server_context_service import (
    resolve_user_server_complaint_settings,
    resolve_user_server_identity,
    resolve_user_server_config,
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


def _normalize_history_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for item in items:
        row = dict(item)
        created_at = row.get("created_at")
        if isinstance(created_at, datetime):
            row["created_at"] = created_at.isoformat()
        elif created_at is not None and not isinstance(created_at, str):
            row["created_at"] = str(created_at)
        normalized.append(row)
    return normalized


def _env_positive_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


class SuggestConcurrencyLimiter:
    def __init__(self, *, max_concurrency: int, retry_after_seconds: int = 3) -> None:
        self.max_concurrency = max(1, int(max_concurrency or 1))
        self.retry_after_seconds = max(1, int(retry_after_seconds or 1))
        self._semaphore = BoundedSemaphore(self.max_concurrency)
        self._lock = Lock()
        self._inflight = 0

    def try_acquire(self) -> bool:
        if not self._semaphore.acquire(blocking=False):
            return False
        with self._lock:
            self._inflight += 1
        return True

    def release(self) -> None:
        with self._lock:
            if self._inflight <= 0:
                return
            self._inflight -= 1
        self._semaphore.release()

    @property
    def inflight(self) -> int:
        with self._lock:
            return self._inflight


SUGGEST_CONCURRENCY_LIMITER = SuggestConcurrencyLimiter(
    max_concurrency=_env_positive_int("OGP_SUGGEST_MAX_CONCURRENCY", 4),
    retry_after_seconds=_env_positive_int("OGP_SUGGEST_RETRY_AFTER_SECONDS", 3),
)


def _build_heavy_ai_executor() -> ThreadPoolExecutor | None:
    max_workers = _env_positive_int("OGP_AI_HEAVY_MAX_WORKERS", 0)
    if max_workers <= 0:
        return None
    return ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ogp-ai-heavy")


HEAVY_AI_EXECUTOR = _build_heavy_ai_executor()


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
    enqueued_at = monotonic()
    executor = HEAVY_AI_EXECUTOR if use_heavy_executor else None
    queue_size = -1
    if executor is not None:
        queue = getattr(executor, "_work_queue", None)
        if queue is not None and hasattr(queue, "qsize"):
            try:
                queue_size = int(queue.qsize())
            except Exception:  # noqa: BLE001
                queue_size = -1

    def _invoke() -> tuple[object, float, float]:
        started_at = monotonic()
        wait_ms = (started_at - enqueued_at) * 1000.0
        result = func(**kwargs)
        finished_at = monotonic()
        run_ms = (finished_at - started_at) * 1000.0
        return result, wait_ms, run_ms

    loop = asyncio.get_running_loop()
    if executor is None:
        started_at = monotonic()
        result = await run_in_threadpool(func, **kwargs)
        finished_at = monotonic()
        wait_ms = 0.0
        run_ms = (finished_at - started_at) * 1000.0
    else:
        result, wait_ms, run_ms = await loop.run_in_executor(executor, _invoke)

    metrics_store.log_event(
        event_type="threadpool_wait",
        username=user.username,
        server_code=user.server_code,
        path=path,
        method="POST",
        status_code=200,
        meta={
            "server_code": user.server_code,
            "operation": operation,
            "executor": "ai_heavy" if executor is not None else "default",
            "queue_size": queue_size,
            "wait_ms": round(wait_ms, 2),
            "run_ms": round(run_ms, 2),
        },
    )
    record_async_queue_lag(
        metrics_store,
        username=user.username,
        path=path,
        method="POST",
        labels=build_rollout_labels(
            flag="async_jobs_v1",
            rollout_mode="all" if executor is not None else "off",
            cohort="default",
            server_id=user.server_code,
            flow_type=operation,
            status="success",
        ),
        lag_ms=int(wait_ms),
    )
    return result


def _validation_service(store: UserStore) -> ValidationService:
    return ValidationService(ValidationRepository(store.backend))


def _with_shadow_citations_policy(context_snapshot: dict[str, object]) -> dict[str, object]:
    snapshot = dict(context_snapshot)
    snapshot["citations_policy_gate"] = {"mode": "shadow", "status": "flagged_no_citations"}
    return snapshot


def _build_complaint_generation_context_snapshot(
    *,
    store: UserStore,
    user: AuthUser,
    adapter_flag,
) -> dict[str, object]:
    if supports_pilot_runtime_adapter(server_code=user.server_code, document_kind="complaint") and adapter_flag.use_new_flow:
        return resolve_pilot_complaint_runtime_context(store, user).to_generation_context_snapshot()
    return dict(build_generation_context_snapshot(store, user, document_kind="complaint"))


def _validate_server_payload(store: UserStore, user: AuthUser, *, org: str = "", complaint_basis: str = "") -> None:
    complaint_settings = resolve_user_server_complaint_settings(store, user.username, server_code=user.server_code)
    server_identity = resolve_user_server_identity(store, user.username, server_code=user.server_code)
    normalized_org = str(org or "").strip()
    normalized_basis = str(complaint_basis or "").strip()
    if normalized_org and complaint_settings.organizations and normalized_org not in complaint_settings.organizations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[f"Организация {normalized_org!r} не относится к серверу {server_identity.name}."],
        )
    allowed_bases = set(complaint_settings.complaint_basis_codes)
    if normalized_basis and allowed_bases and normalized_basis not in allowed_bases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[f"Основание жалобы {normalized_basis!r} не поддерживается для сервера {server_identity.name}."],
        )


@router.get("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def get_complaint_draft(
    document_type: str = "complaint",
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ComplaintDraftResponse:
    server_config = resolve_user_server_config(store, user.username, server_code=user.server_code)
    draft = store.get_complaint_draft(user.username, server_code=user.server_code, document_type=document_type)
    metadata = draft.get("_meta", {}) if isinstance(draft.get("_meta"), dict) else {}
    normalized = normalize_complaint_draft(_flatten_complaint_draft(draft.get("draft", {})), config=server_config)
    return ComplaintDraftResponse(
        draft=normalized.draft,
        updated_at=str(draft.get("updated_at", "") or ""),
        bundle_version=str(metadata.get("bundle_version", "") or ""),
        schema_hash=str(metadata.get("schema_hash", "") or ""),
        status=str(metadata.get("status", "draft") or "draft"),
        allowed_actions=list(metadata.get("allowed_actions", []) or []),
        document_type=str(draft.get("document_type", document_type) or "complaint"),
        server_id=str(draft.get("server_id", user.server_code) or ""),
        message="Черновик жалобы загружен.",
    )


@router.put("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def save_complaint_draft(
    payload: ComplaintDraftPayload,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ComplaintDraftResponse:
    server_config = resolve_user_server_config(store, user.username, server_code=user.server_code)
    normalized = normalize_complaint_draft(_flatten_complaint_draft(payload.draft), config=server_config)
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
        user.username,
        draft_with_meta,
        server_code=user.server_code,
        document_type=payload.document_type,
    )
    metadata = draft.get("_meta", {}) if isinstance(draft.get("_meta"), dict) else {}
    metrics_store.log_event(
        event_type="complaint_draft_saved",
        username=user.username,
        path="/api/complaint-draft",
        method="PUT",
        status_code=200,
        resource_units=len(str(normalized.draft or {})),
        meta={"keys_count": len(normalized.draft or {}), "server_code": user.server_code, "draft_actions": normalized.actions or {}},
    )
    return ComplaintDraftResponse(
        draft=_flatten_complaint_draft(draft.get("draft", {})),
        updated_at=str(draft.get("updated_at", "") or ""),
        bundle_version=str(metadata.get("bundle_version", "") or ""),
        schema_hash=str(metadata.get("schema_hash", "") or ""),
        status=str(metadata.get("status", "draft") or "draft"),
        allowed_actions=list(metadata.get("allowed_actions", []) or []),
        document_type=str(draft.get("document_type", payload.document_type) or "complaint"),
        server_id=str(draft.get("server_id", user.server_code) or ""),
        message="Черновик жалобы сохранён.",
    )


@router.delete("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def clear_complaint_draft(
    document_type: str = "complaint",
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ComplaintDraftResponse:
    store.clear_complaint_draft(user.username, server_code=user.server_code, document_type=document_type)
    metrics_store.log_event(
        event_type="complaint_draft_cleared",
        username=user.username,
        path="/api/complaint-draft",
        method="DELETE",
        status_code=200,
        meta={"server_code": user.server_code},
    )
    return ComplaintDraftResponse(
        draft={},
        updated_at="",
        status="draft",
        document_type=document_type,
        server_id=user.server_code,
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
    started_at = start_timer()
    docs_flag = flag_service.evaluate(flag="documents_v2", context=RolloutContext(username=user.username, server_id=user.server_code))
    validation_flag = flag_service.evaluate(
        flag="validation_gate_v1",
        context=RolloutContext(username=user.username, server_id=user.server_code),
    )
    adapter_flag = flag_service.evaluate(
        flag="pilot_runtime_adapter_v1",
        context=RolloutContext(username=user.username, server_id=user.server_code),
    )
    _validate_server_payload(store, user, org=payload.org)
    context_snapshot = _with_shadow_citations_policy(
        _build_complaint_generation_context_snapshot(store=store, user=user, adapter_flag=adapter_flag)
    )
    bbcode = generate_bbcode_text(store, payload, user)
    orchestrator = GenerationOrchestrator(store)
    bridge_result = orchestrator.write_generation_bridge(
        username=user.username,
        server_code=user.server_code,
        document_kind="complaint",
        payload=payload.model_dump(),
        result_text=bbcode,
        context_snapshot=context_snapshot,
        legacy_generated_document_id=None,
    )
    document_id = int(bridge_result.generated_document_id)
    if bridge_result is not None:
        try:
            if validation_flag.use_new_flow:
                result = _validation_service(store).run_validation(
                    target_type="document_version",
                    target_id=int(bridge_result.document_version_id),
                )
                record_validation_fail_rate(
                    metrics_store,
                    username=user.username,
                    path="/api/generate",
                    method="POST",
                    labels=build_rollout_labels(
                        flag="validation_gate_v1",
                        rollout_mode=validation_flag.mode.value,
                        cohort=validation_flag.cohort.value,
                        server_id=user.server_code,
                        flow_type="generate",
                        status="fail" if result.run.get("status") == "fail" else "success",
                    ),
                    failed=result.run.get("status") == "fail",
                )
        except Exception:
            if str(os.getenv("OGP_VALIDATION_GENERATION_STRICT", "0") or "").strip() in {"1", "true", "yes", "on"}:
                raise
    metrics_store.log_event(
        event_type="complaint_generated",
        username=user.username,
        path="/api/generate",
        method="POST",
        status_code=200,
        resource_units=len(bbcode),
        meta={
            "server_code": user.server_code,
            "event_dt": payload.event_dt,
            "org": payload.org,
            "subject_names": payload.subject_names,
            "result_chars": len(bbcode),
            "description_chars": len(payload.situation_description or ""),
        },
    )
    record_generation_latency(
        metrics_store,
        username=user.username,
        path="/api/generate",
        method="POST",
        labels=build_rollout_labels(
            flag="documents_v2",
            rollout_mode=docs_flag.mode.value,
            cohort=docs_flag.cohort.value,
            server_id=user.server_code,
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
    bridge_result = GenerationOrchestrator(store).write_generation_bridge(
        username=user.username,
        server_code=user.server_code,
        document_kind="rehab",
        payload=payload.model_dump(),
        result_text=bbcode,
        context_snapshot=context_snapshot,
        legacy_generated_document_id=None,
    )
    document_id = int(bridge_result.generated_document_id)
    if bridge_result is not None:
        try:
            if validation_flag.use_new_flow:
                result = _validation_service(store).run_validation(
                    target_type="document_version",
                    target_id=int(bridge_result.document_version_id),
                )
                record_validation_fail_rate(
                    metrics_store,
                    username=user.username,
                    path="/api/generate-rehab",
                    method="POST",
                    labels=build_rollout_labels(
                        flag="validation_gate_v1",
                        rollout_mode=validation_flag.mode.value,
                        cohort=validation_flag.cohort.value,
                        server_id=user.server_code,
                        flow_type="generate",
                        status="fail" if result.run.get("status") == "fail" else "success",
                    ),
                    failed=result.run.get("status") == "fail",
                )
        except Exception:
            if str(os.getenv("OGP_VALIDATION_GENERATION_STRICT", "0") or "").strip() in {"1", "true", "yes", "on"}:
                raise
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
    items = _normalize_history_items(
        list_user_generated_document_history(store=store, username=user.username, limit=limit)
    )
    return GeneratedDocumentHistoryResponse(items=items)


@router.get("/api/generated-documents/{document_id}/snapshot", response_model=GeneratedDocumentSnapshotResponse)
async def generated_document_snapshot(
    document_id: int,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
) -> GeneratedDocumentSnapshotResponse:
    bundle = resolve_user_generated_document_trace_bundle(
        store=store,
        username=user.username,
        legacy_generated_document_id=document_id,
    )
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Документ не найден."])
    provenance = resolve_generated_document_provenance_payload(
        store=store,
        generation_snapshot_id=bundle.generation_snapshot_id,
    )
    return GeneratedDocumentSnapshotResponse(**bundle.snapshot, provenance=provenance)


@router.post("/api/ai/suggest", response_model=SuggestResponse)
async def suggest(
    payload: SuggestPayload,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> SuggestResponse:
    _validate_server_payload(store, user, org=payload.org, complaint_basis=payload.complaint_basis)
    acquired = SUGGEST_CONCURRENCY_LIMITER.try_acquire()
    if not acquired:
        retry_after = str(SUGGEST_CONCURRENCY_LIMITER.retry_after_seconds)
        metrics_store.log_event(
            event_type="ai_suggest_overload",
            username=user.username,
            server_code=user.server_code,
            path="/api/ai/suggest",
            method="POST",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            meta={
                "server_code": user.server_code,
                "complaint_basis": payload.complaint_basis,
                "main_focus": payload.main_focus,
                "retry_after_seconds": SUGGEST_CONCURRENCY_LIMITER.retry_after_seconds,
                "inflight": SUGGEST_CONCURRENCY_LIMITER.inflight,
                "max_concurrency": SUGGEST_CONCURRENCY_LIMITER.max_concurrency,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=["Сервис AI suggest временно перегружен. Повторите попытку через несколько секунд."],
            headers={"Retry-After": retry_after},
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
        meta=ai_service.build_suggest_metrics_meta(payload=payload, result=result, server_code=user.server_code),
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


def _law_qa_selected_norms_to_citations(*, store: UserStore, server_id: str, law_version_id: int | None, selected_norms: list[dict[str, object]]) -> list[dict[str, object]]:
    if law_version_id is None:
        return []
    citations: list[dict[str, object]] = []
    for norm in selected_norms:
        source_url = str(norm.get("source_url") or "").strip()
        document_title = str(norm.get("document_title") or "").strip()
        article_label = str(norm.get("article_label") or "").strip()
        excerpt = str(norm.get("excerpt") or norm.get("excerpt_preview") or "").strip()
        if not source_url or not document_title or not article_label:
            continue
        source = store.resolve_law_article_source(
            server_id=server_id,
            law_version_id=law_version_id,
            article_label=article_label,
            document_title=document_title,
            source_url=source_url,
        )
        if source is None:
            continue
        citations.append(
            {
                "citation_type": "norm",
                "source_type": "law_article",
                "source_id": int(source["source_id"]),
                "source_version_id": int(source["source_version_id"]),
                "canonical_ref": f"{document_title} {article_label}",
                "quoted_text": excerpt,
                "usage_type": "supporting",
            }
        )
    return citations


@router.post("/api/ai/law-qa-test", response_model=LawQaResponse)
async def law_qa_test(
    payload: LawQaPayload,
    user: AuthUser = Depends(requires_permission("court_claims")),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    flag_service: FeatureFlagService = Depends(get_feature_flag_service),
) -> LawQaResponse:
    try:
        started_at = start_timer()
        effective_server_code = payload.server_code or user.server_code
        if not str(effective_server_code or "").strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["server_code is required."])
        payload = payload.model_copy(update={"server_code": effective_server_code})
        result = await _run_ai_task(
            metrics_store=metrics_store,
            user=user,
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
        raw_citations = _law_qa_selected_norms_to_citations(
            store=store,
            server_id=effective_server_code,
            law_version_id=payload.law_version_id,
            selected_norms=selected_norms,
        )
        citations_flag = flag_service.evaluate(
            flag="citations_required",
            context=RolloutContext(username=user.username, server_id=effective_server_code),
        )
        response_warnings = list(getattr(result, "warnings", []) or [])
        if citations_flag.use_new_flow and not raw_citations:
            if citations_flag.enforcement.value == "hard":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=["citations_required policy blocked the response due to missing citations."],
                )
            response_warnings.append("citations_required_warn:missing_citations")
        retrieval = run_retrieval(
            store=store,
            actor_username=user.username,
            server_id=effective_server_code,
            run_type="law_qa",
            query_text=payload.question,
            effective_versions={"law_version_id": payload.law_version_id},
            retrieved_sources=[{"url": item} for item in (getattr(result, "used_sources", []) or [])],
            candidates=raw_citations,
            policy_status="pass" if raw_citations else "blocked_missing_citations",
        )
        actor_id = store.get_user_id(user.username)
        if actor_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Пользователь не найден."])
        law_qa_run_id = store.create_law_qa_run(
            server_id=effective_server_code,
            user_id=int(actor_id),
            question=payload.question,
            answer_text=result.text,
            retrieval_run_id=retrieval.retrieval_run_id,
            snapshot_id=str(payload.law_version_id or ""),
        )
        citations = (
            save_answer_citations(
                store=store,
                server_id=effective_server_code,
                law_qa_run_id=law_qa_run_id,
                retrieval_run_id=retrieval.retrieval_run_id,
                citations=raw_citations,
            )
            if raw_citations
            else []
        )
        metrics_store.log_event(
            event_type="ai_law_qa_test",
            username=user.username,
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
            },
        )
        metrics_store.log_ai_generation(
            username=user.username,
            server_code=effective_server_code,
            flow="law_qa",
            generation_id=result.generation_id,
            path="/api/ai/law-qa-test",
            meta=ai_service.build_law_qa_metrics_meta(payload=payload, result=result, used_sources=result.used_sources),
        )
        try:
            validation_flag = flag_service.evaluate(
                flag="validation_gate_v1",
                context=RolloutContext(username=user.username, server_id=effective_server_code),
            )
            validation_repo = ValidationRepository(store.backend)
            conn = store.backend.connect()
            user_row = conn.execute("SELECT id FROM users WHERE username = %s", (user.username,)).fetchone()
            conn.close()
            if user_row is not None:
                qa_run = validation_repo.create_law_qa_run(
                    server_id=effective_server_code,
                    user_id=int(user_row["id"]),
                    question=payload.question,
                    answer_text=result.text,
                    used_sources=list(result.used_sources),
                    selected_norms=list(result.selected_norms),
                    metadata={"generation_id": result.generation_id, "legacy_endpoint": "/api/ai/law-qa-test"},
                )
                if validation_flag.use_new_flow:
                    validation_result = ValidationService(validation_repo).run_validation(
                        target_type="law_qa_run",
                        target_id=int(qa_run["id"]),
                    )
                    record_validation_fail_rate(
                        metrics_store,
                        username=user.username,
                        path="/api/ai/law-qa-test",
                        method="POST",
                        labels=build_rollout_labels(
                            flag="validation_gate_v1",
                            rollout_mode=validation_flag.mode.value,
                            cohort=validation_flag.cohort.value,
                            server_id=effective_server_code,
                            flow_type="law_qa",
                            status="fail" if validation_result.run.get("status") == "fail" else "success",
                        ),
                        failed=validation_result.run.get("status") == "fail",
                    )
        except Exception:
            if str(os.getenv("OGP_VALIDATION_LAW_QA_STRICT", "0") or "").strip() in {"1", "true", "yes", "on"}:
                raise
        record_generation_latency(
            metrics_store,
            username=user.username,
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
    validation_repository = ValidationRepository(store.backend)
    target = validation_repository.get_document_version_target(version_id=version_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Document version not found."])
    if str(target.get("server_id") or "") != user.server_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для документа."])

    payload = build_store_provenance_service(store=store).get_document_version_trace(document_version_id=version_id)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Provenance trace not found."])
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
