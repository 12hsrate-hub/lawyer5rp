from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import BoundedSemaphore, Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from ogp_web.dependencies import get_admin_metrics_store, get_user_store
from ogp_web.schemas import (
    AiFeedbackPayload,
    AiFeedbackResponse,
    ComplaintDraftPayload,
    ComplaintDraftResponse,
    ComplaintPayload,
    GenerateResponse,
    LawQaPayload,
    LawQaResponse,
    PrincipalScanPayload,
    PrincipalScanResult,
    RehabPayload,
    SuggestPayload,
    SuggestResponse,
)
from ogp_web.server_config import build_permission_set, get_server_config
from ogp_web.services import ai_service
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.services.complaint_service import generate_bbcode_text, generate_rehab_bbcode_text
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["complaint"])


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
        result, wait_ms, run_ms = await run_in_threadpool(_invoke)
    else:
        result, wait_ms, run_ms = await loop.run_in_executor(executor, _invoke)

    await _run_sync_io(
        metrics_store.log_event,
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
    return result


def _server_config_for_user(store: UserStore, user: AuthUser):
    return get_server_config(user.server_code or store.get_server_code(user.username))


def _ensure_law_qa_permission(store: UserStore, user: AuthUser) -> None:
    server_config = _server_config_for_user(store, user)
    permissions = build_permission_set(store, user.username, server_config)
    if not permissions.can_access_court_claims:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=["Недостаточно прав для доступа к тестовому Q&A по законам."],
        )


def _validate_server_payload(store: UserStore, user: AuthUser, *, org: str = "", complaint_basis: str = "") -> None:
    server_config = _server_config_for_user(store, user)
    normalized_org = str(org or "").strip()
    normalized_basis = str(complaint_basis or "").strip()
    if normalized_org and server_config.organizations and normalized_org not in server_config.organizations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[f"Организация {normalized_org!r} не относится к серверу {server_config.name}."],
        )
    allowed_bases = set(server_config.complaint_basis_codes())
    if normalized_basis and allowed_bases and normalized_basis not in allowed_bases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[f"Основание жалобы {normalized_basis!r} не поддерживается для сервера {server_config.name}."],
        )


@router.get("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def get_complaint_draft(
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
) -> ComplaintDraftResponse:
    draft = store.get_complaint_draft(user.username)
    return ComplaintDraftResponse(
        draft=draft.get("draft", {}),
        updated_at=str(draft.get("updated_at", "") or ""),
        message="Черновик жалобы загружен.",
    )


@router.put("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def save_complaint_draft(
    payload: ComplaintDraftPayload,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ComplaintDraftResponse:
    draft = store.save_complaint_draft(user.username, payload.draft)
    metrics_store.log_event(
        event_type="complaint_draft_saved",
        username=user.username,
        path="/api/complaint-draft",
        method="PUT",
        status_code=200,
        resource_units=len(str(payload.draft or {})),
        meta={"keys_count": len(payload.draft or {}), "server_code": user.server_code},
    )
    return ComplaintDraftResponse(
        draft=draft.get("draft", {}),
        updated_at=str(draft.get("updated_at", "") or ""),
        message="Черновик жалобы сохранён.",
    )


@router.delete("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def clear_complaint_draft(
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ComplaintDraftResponse:
    store.clear_complaint_draft(user.username)
    metrics_store.log_event(
        event_type="complaint_draft_cleared",
        username=user.username,
        path="/api/complaint-draft",
        method="DELETE",
        status_code=200,
        meta={"server_code": user.server_code},
    )
    return ComplaintDraftResponse(draft={}, updated_at="", message="Черновик жалобы очищен.")


@router.post("/api/generate", response_model=GenerateResponse)
async def generate(
    payload: ComplaintPayload,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> GenerateResponse:
    _validate_server_payload(store, user, org=payload.org)
    bbcode = generate_bbcode_text(store, payload, user)
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
    return GenerateResponse(bbcode=bbcode)


@router.post("/api/generate-rehab", response_model=GenerateResponse)
async def generate_rehab(
    payload: RehabPayload,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> GenerateResponse:
    bbcode = generate_rehab_bbcode_text(store, payload, user)
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
    return GenerateResponse(bbcode=bbcode)


@router.post("/api/ai/suggest", response_model=SuggestResponse)
async def suggest(
    payload: SuggestPayload,
    user: AuthUser = Depends(require_user),
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
    user: AuthUser = Depends(require_user),
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
) -> LawQaResponse:
    _ensure_law_qa_permission(store, user)
    effective_server_code = payload.server_code or user.server_code or store.get_server_code(user.username)
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
        warnings=result.warnings,
        shadow=result.shadow,
        selected_norms=result.selected_norms,
    )


@router.post("/api/ai/feedback", response_model=AiFeedbackResponse)
async def ai_feedback(
    payload: AiFeedbackPayload,
    user: AuthUser = Depends(require_user),
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
