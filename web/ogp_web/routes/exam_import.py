from __future__ import annotations

import logging
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool

from ogp_web.dependencies import get_admin_metrics_store, get_exam_answers_store, get_exam_import_task_registry, requires_permission
from ogp_web.schemas import ExamAnswerScore, ExamImportDetail, ExamImportResponse, ExamImportTaskStatus
from ogp_web.services.job_status_service import enrich_job_status
from ogp_web.services import exam_import_service
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.exam_import_runtime_service import ExamImportRuntimeService
from ogp_web.services.exam_import_tasks import (
    ExamImportTaskCapacityError,
    ExamImportTaskRegistry,
)
from ogp_web.services.exam_sheet_service import EXAM_SHEET_URL, build_exam_score_items, fetch_exam_sheet_rows
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from shared.ogp_ai import score_exam_answer_with_proxy_fallback, score_exam_answers_batch_with_proxy_fallback


router = APIRouter(tags=["exam-import"])
logger = logging.getLogger(__name__)
_SERVICE_SCORE_EXAM_ANSWERS_IF_NEEDED = exam_import_service.score_exam_answers_if_needed
EXAM_IMPORT_RUNTIME_SERVICE = ExamImportRuntimeService()


async def _run_sync_io(func, /, *args, **kwargs):
    return await run_in_threadpool(partial(func, *args, **kwargs))


def _fill_question_g_fields(entry: dict[str, object]) -> None:
    exam_import_service.fill_question_g_fields(entry)


def _normalize_entry(entry: dict[str, object]) -> dict[str, object]:
    return exam_import_service.normalize_entry(entry)


def _retry_invalid_batch_scores(
    *,
    api_key: str,
    proxy_url: str,
    score_items: list[dict[str, str]],
    results: dict[str, dict[str, object]],
    stats: dict[str, int],
) -> dict[str, dict[str, object]]:
    return exam_import_service.retry_invalid_batch_scores(
        api_key=api_key,
        proxy_url=proxy_url,
        score_items=score_items,
        results=results,
        stats=stats,
    )


def _score_exam_answers_if_needed(store: ExamAnswersStore, entry: dict[str, object]) -> tuple[bool, dict[str, int]]:
    return _SERVICE_SCORE_EXAM_ANSWERS_IF_NEEDED(
        store,
        entry,
        build_exam_score_items=build_exam_score_items,
    )


def _humanize_scoring_exception(exc: Exception) -> str:
    return exam_import_service.humanize_scoring_exception(exc)


def _build_scoring_error_details(exc: Exception, source_row: int) -> list[str]:
    return exam_import_service.build_scoring_error_details(exc, source_row)


def _serialize_http_exception(exc: HTTPException) -> str:
    return exam_import_service.serialize_http_exception(exc)


def _score_pending_rows(store: ExamAnswersStore) -> tuple[int, dict[str, int], list[dict[str, object]]]:
    return exam_import_service.score_pending_rows(store, build_exam_score_items=build_exam_score_items)


def _build_entries_response(store: ExamAnswersStore, *, limit: int = 20, offset: int = 0):
    return exam_import_service.build_entries_response(store, limit=limit, offset=offset)


def _build_failed_fields(scores: list[dict[str, object]]) -> list[dict[str, object]]:
    return exam_import_service.build_failed_fields(scores)


def _build_bulk_scoring_result(
    *,
    user: AuthUser,
    store: ExamAnswersStore,
    metrics_store: AdminMetricsStore,
    progress_callback=None,
) -> dict[str, object]:
    return EXAM_IMPORT_RUNTIME_SERVICE.build_bulk_scoring_result(
        user=user,
        store=store,
        metrics_store=metrics_store,
        exam_sheet_url=EXAM_SHEET_URL,
        build_exam_score_items=build_exam_score_items,
        score_if_needed_func=_score_exam_answers_if_needed,
        batch_score_func=score_exam_answers_batch_with_proxy_fallback,
        single_score_func=score_exam_answer_with_proxy_fallback,
        progress_callback=progress_callback,
    )


def _build_row_scoring_result(
    *,
    source_row: int,
    user: AuthUser,
    store: ExamAnswersStore,
    metrics_store: AdminMetricsStore,
    force_rescore: bool = False,
) -> dict[str, object]:
    return EXAM_IMPORT_RUNTIME_SERVICE.build_row_scoring_result(
        source_row=source_row,
        user=user,
        store=store,
        metrics_store=metrics_store,
        build_exam_score_items=build_exam_score_items,
        score_if_needed_func=_score_exam_answers_if_needed,
        batch_score_func=score_exam_answers_batch_with_proxy_fallback,
        single_score_func=score_exam_answer_with_proxy_fallback,
        force_rescore=force_rescore,
    )


def _build_failed_rescoring_result(
    *,
    user: AuthUser,
    store: ExamAnswersStore,
    metrics_store: AdminMetricsStore,
    progress_callback=None,
) -> dict[str, object]:
    return EXAM_IMPORT_RUNTIME_SERVICE.build_failed_rescoring_result(
        user=user,
        store=store,
        metrics_store=metrics_store,
        exam_sheet_url=EXAM_SHEET_URL,
        build_exam_score_items=build_exam_score_items,
        score_if_needed_func=_score_exam_answers_if_needed,
        batch_score_func=score_exam_answers_batch_with_proxy_fallback,
        single_score_func=score_exam_answer_with_proxy_fallback,
        progress_callback=progress_callback,
    )


@router.post("/api/exam-import/sync", response_model=ExamImportResponse)
async def sync_exam_import(
    user: AuthUser = Depends(requires_permission("exam_import")),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ExamImportResponse:
    payload = await _run_sync_io(
        EXAM_IMPORT_RUNTIME_SERVICE.build_sync_import_response,
        user=user,
        store=store,
        metrics_store=metrics_store,
        exam_sheet_url=EXAM_SHEET_URL,
        fetch_rows=fetch_exam_sheet_rows,
        build_entries_response=_build_entries_response,
    )
    return ExamImportResponse(**payload)


@router.get("/api/exam-import/entries")
async def list_exam_import_entries(
    user: AuthUser = Depends(requires_permission("exam_import")),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    _ = user
    items = await _run_sync_io(_build_entries_response, store, limit=limit, offset=offset)
    total = await _run_sync_io(store.count)
    return {
        "items": items,
        "total": int(total),
        "limit": int(limit),
        "offset": int(offset),
        "has_next": int(offset) + len(items) < int(total),
    }


@router.post("/api/exam-import/score", response_model=ExamImportResponse)
async def score_exam_import(
    user: AuthUser = Depends(requires_permission("exam_import")),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ExamImportResponse:

    try:
        payload = await _run_sync_io(_build_bulk_scoring_result, user=user, store=store, metrics_store=metrics_store)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=[str(exc)]) from exc
    return ExamImportResponse(**payload)


@router.post("/api/exam-import/rows/{source_row}/score", response_model=ExamImportDetail)
async def score_exam_import_row(
    source_row: int,
    user: AuthUser = Depends(requires_permission("exam_import")),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ExamImportDetail:

    try:
        payload = await _run_sync_io(
            _build_row_scoring_result,
            source_row=source_row,
            user=user,
            store=store,
            metrics_store=metrics_store,
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=[str(exc)]) from exc
    return ExamImportDetail(**payload)


@router.post("/api/exam-import/score/tasks", response_model=ExamImportTaskStatus)
async def create_exam_import_score_task(
    user: AuthUser = Depends(requires_permission("exam_import")),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    task_registry: ExamImportTaskRegistry = Depends(get_exam_import_task_registry),
) -> ExamImportTaskStatus:
    payload = EXAM_IMPORT_RUNTIME_SERVICE.create_task_status(
        task_registry=task_registry,
        task_type="bulk_score",
        runner=lambda progress_callback: _build_bulk_scoring_result(
            user=user,
            store=store,
            metrics_store=metrics_store,
            progress_callback=progress_callback,
        ),
    )
    return ExamImportTaskStatus(**payload)


@router.post("/api/exam-import/rescore-failed/tasks", response_model=ExamImportTaskStatus)
async def create_exam_import_failed_rescore_task(
    user: AuthUser = Depends(requires_permission("exam_import")),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    task_registry: ExamImportTaskRegistry = Depends(get_exam_import_task_registry),
) -> ExamImportTaskStatus:
    payload = EXAM_IMPORT_RUNTIME_SERVICE.create_task_status(
        task_registry=task_registry,
        task_type="bulk_rescore_failed",
        runner=lambda progress_callback: _build_failed_rescoring_result(
            user=user,
            store=store,
            metrics_store=metrics_store,
            progress_callback=progress_callback,
        ),
    )
    return ExamImportTaskStatus(**payload)


@router.post("/api/exam-import/rows/{source_row}/score/tasks", response_model=ExamImportTaskStatus)
async def create_exam_import_row_score_task(
    source_row: int,
    user: AuthUser = Depends(requires_permission("exam_import")),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    task_registry: ExamImportTaskRegistry = Depends(get_exam_import_task_registry),
) -> ExamImportTaskStatus:
    await _run_sync_io(EXAM_IMPORT_RUNTIME_SERVICE.require_entry, store=store, source_row=source_row)
    payload = EXAM_IMPORT_RUNTIME_SERVICE.create_task_status(
        task_registry=task_registry,
        task_type="row_score",
        source_row=source_row,
        runner=lambda progress_callback: _build_row_scoring_result(
            source_row=source_row,
            user=user,
            store=store,
            metrics_store=metrics_store,
        ),
    )
    return ExamImportTaskStatus(**payload)


@router.get("/api/exam-import/tasks/{task_id}", response_model=ExamImportTaskStatus)
async def get_exam_import_task(
    task_id: str,
    user: AuthUser = Depends(requires_permission("exam_import")),
    task_registry: ExamImportTaskRegistry = Depends(get_exam_import_task_registry),
) -> ExamImportTaskStatus:
    payload = EXAM_IMPORT_RUNTIME_SERVICE.get_task_status(task_registry=task_registry, task_id=task_id)
    return ExamImportTaskStatus(**payload)


@router.get("/api/exam-import/rows/{source_row}", response_model=ExamImportDetail)
async def exam_import_detail(
    source_row: int,
    user: AuthUser = Depends(requires_permission("exam_import")),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
) -> ExamImportDetail:
    entry = await _run_sync_io(EXAM_IMPORT_RUNTIME_SERVICE.require_entry, store=store, source_row=source_row)
    payload = EXAM_IMPORT_RUNTIME_SERVICE.build_entry_detail(
        entry=entry,
        fill_question_g_fields=_fill_question_g_fields,
        normalize_entry=_normalize_entry,
        score_serializer=lambda item: ExamAnswerScore(**item).model_dump(),
    )
    return ExamImportDetail(**payload)


@router.delete("/api/exam-import/rows/{source_row}/scores", response_model=ExamImportDetail)
async def clear_exam_import_row_scores(
    source_row: int,
    user: AuthUser = Depends(requires_permission("exam_import")),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
) -> ExamImportDetail:
    payload = await _run_sync_io(
        EXAM_IMPORT_RUNTIME_SERVICE.clear_row_scores_and_build_detail,
        store=store,
        source_row=source_row,
        fill_question_g_fields=_fill_question_g_fields,
        normalize_entry=_normalize_entry,
        score_serializer=lambda item: ExamAnswerScore(**item).model_dump(),
    )
    return ExamImportDetail(**payload)
