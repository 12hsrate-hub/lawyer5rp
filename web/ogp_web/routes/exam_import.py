from __future__ import annotations

import logging
from functools import partial
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from ogp_web.dependencies import get_admin_metrics_store, get_exam_answers_store, get_exam_import_task_registry
from ogp_web.env import is_test_user
from ogp_web.schemas import ExamAnswerScore, ExamImportDetail, ExamImportResponse, ExamImportTaskStatus
from ogp_web.services import exam_import_service
from ogp_web.services.auth_service import AuthUser, require_user
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
_SCORING_WRAPPER_LOCK = Lock()


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


def _build_entries_response(store: ExamAnswersStore):
    return exam_import_service.build_entries_response(store)


def _build_failed_fields(scores: list[dict[str, object]]) -> list[dict[str, object]]:
    return exam_import_service.build_failed_fields(scores)


def _build_bulk_scoring_result(
    *,
    user: AuthUser,
    store: ExamAnswersStore,
    metrics_store: AdminMetricsStore,
    progress_callback=None,
) -> dict[str, object]:
    with _SCORING_WRAPPER_LOCK:
        original_batch = exam_import_service.score_exam_answers_batch_with_proxy_fallback
        original_single = exam_import_service.score_exam_answer_with_proxy_fallback
        original_score = exam_import_service.score_exam_answers_if_needed
        exam_import_service.score_exam_answers_batch_with_proxy_fallback = score_exam_answers_batch_with_proxy_fallback
        exam_import_service.score_exam_answer_with_proxy_fallback = score_exam_answer_with_proxy_fallback
        exam_import_service.score_exam_answers_if_needed = lambda store_arg, entry_arg, **_: _score_exam_answers_if_needed(store_arg, entry_arg)
        try:
            return exam_import_service.build_bulk_scoring_result(
                user=user,
                store=store,
                metrics_store=metrics_store,
                exam_sheet_url=EXAM_SHEET_URL,
                build_exam_score_items=build_exam_score_items,
                progress_callback=progress_callback,
            )
        finally:
            exam_import_service.score_exam_answers_batch_with_proxy_fallback = original_batch
            exam_import_service.score_exam_answer_with_proxy_fallback = original_single
            exam_import_service.score_exam_answers_if_needed = original_score


def _build_row_scoring_result(
    *,
    source_row: int,
    user: AuthUser,
    store: ExamAnswersStore,
    metrics_store: AdminMetricsStore,
    force_rescore: bool = False,
) -> dict[str, object]:
    with _SCORING_WRAPPER_LOCK:
        original_batch = exam_import_service.score_exam_answers_batch_with_proxy_fallback
        original_single = exam_import_service.score_exam_answer_with_proxy_fallback
        original_score = exam_import_service.score_exam_answers_if_needed
        exam_import_service.score_exam_answers_batch_with_proxy_fallback = score_exam_answers_batch_with_proxy_fallback
        exam_import_service.score_exam_answer_with_proxy_fallback = score_exam_answer_with_proxy_fallback
        exam_import_service.score_exam_answers_if_needed = lambda store_arg, entry_arg, **_: _score_exam_answers_if_needed(store_arg, entry_arg)
        try:
            return exam_import_service.build_row_scoring_result(
                source_row=source_row,
                user=user,
                store=store,
                metrics_store=metrics_store,
                build_exam_score_items=build_exam_score_items,
                force_rescore=force_rescore,
            )
        finally:
            exam_import_service.score_exam_answers_batch_with_proxy_fallback = original_batch
            exam_import_service.score_exam_answer_with_proxy_fallback = original_single
            exam_import_service.score_exam_answers_if_needed = original_score


def _build_failed_rescoring_result(
    *,
    user: AuthUser,
    store: ExamAnswersStore,
    metrics_store: AdminMetricsStore,
    progress_callback=None,
) -> dict[str, object]:
    with _SCORING_WRAPPER_LOCK:
        original_batch = exam_import_service.score_exam_answers_batch_with_proxy_fallback
        original_single = exam_import_service.score_exam_answer_with_proxy_fallback
        original_score = exam_import_service.score_exam_answers_if_needed
        exam_import_service.score_exam_answers_batch_with_proxy_fallback = score_exam_answers_batch_with_proxy_fallback
        exam_import_service.score_exam_answer_with_proxy_fallback = score_exam_answer_with_proxy_fallback
        exam_import_service.score_exam_answers_if_needed = lambda store_arg, entry_arg, **_: _score_exam_answers_if_needed(store_arg, entry_arg)
        try:
            return exam_import_service.build_failed_rescoring_result(
                user=user,
                store=store,
                metrics_store=metrics_store,
                exam_sheet_url=EXAM_SHEET_URL,
                build_exam_score_items=build_exam_score_items,
                progress_callback=progress_callback,
            )
        finally:
            exam_import_service.score_exam_answers_batch_with_proxy_fallback = original_batch
            exam_import_service.score_exam_answer_with_proxy_fallback = original_single
            exam_import_service.score_exam_answers_if_needed = original_score


@router.post("/api/exam-import/sync", response_model=ExamImportResponse)
async def sync_exam_import(
    user: AuthUser = Depends(require_user),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ExamImportResponse:
    if not is_test_user(user.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Тестовая страница недоступна."])

    try:
        rows = await _run_sync_io(fetch_exam_sheet_rows, force_refresh=True)
        stats = await _run_sync_io(store.import_rows, rows)
    except Exception as exc:
        logger.exception("Exam import sync failed for user=%s", user.username)
        metrics_store.log_event(
            event_type="exam_import_sync_error",
            username=user.username,
            path="/api/exam-import/sync",
            method="POST",
            status_code=502,
            meta={"error": str(exc), "error_type": exc.__class__.__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=[
                "Не удалось обновить данные из Google Sheets.",
                f"Тип ошибки: {exc.__class__.__name__}",
                f"Полная ошибка: {exc}",
            ],
        ) from exc

    return ExamImportResponse(
        sheet_url=EXAM_SHEET_URL,
        total_rows=stats["total_rows"],
        imported_count=len(rows),
        inserted_count=stats["inserted_count"],
        updated_count=stats["updated_count"],
        skipped_count=int(stats.get("skipped_count", 0)),
        scored_count=0,
        latest_entries=await _run_sync_io(_build_entries_response, store),
    )


@router.post("/api/exam-import/score", response_model=ExamImportResponse)
async def score_exam_import(
    user: AuthUser = Depends(require_user),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ExamImportResponse:
    if not is_test_user(user.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Тестовая страница недоступна."])

    try:
        payload = await _run_sync_io(_build_bulk_scoring_result, user=user, store=store, metrics_store=metrics_store)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=[str(exc)]) from exc
    return ExamImportResponse(**payload)


@router.post("/api/exam-import/rows/{source_row}/score", response_model=ExamImportDetail)
async def score_exam_import_row(
    source_row: int,
    user: AuthUser = Depends(require_user),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ExamImportDetail:
    if not is_test_user(user.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Тестовая страница недоступна."])

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
    user: AuthUser = Depends(require_user),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    task_registry: ExamImportTaskRegistry = Depends(get_exam_import_task_registry),
) -> ExamImportTaskStatus:
    if not is_test_user(user.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Тестовая страница недоступна."])

    try:
        record = task_registry.create_task(
            task_type="bulk_score",
            runner=lambda progress_callback: _build_bulk_scoring_result(
                user=user,
                store=store,
                metrics_store=metrics_store,
                progress_callback=progress_callback,
            ),
        )
    except ExamImportTaskCapacityError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=[str(exc)]) from exc
    return ExamImportTaskStatus(**record.to_dict())


@router.post("/api/exam-import/rescore-failed/tasks", response_model=ExamImportTaskStatus)
async def create_exam_import_failed_rescore_task(
    user: AuthUser = Depends(require_user),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    task_registry: ExamImportTaskRegistry = Depends(get_exam_import_task_registry),
) -> ExamImportTaskStatus:
    if not is_test_user(user.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Тестовая страница недоступна."])

    try:
        record = task_registry.create_task(
            task_type="bulk_rescore_failed",
            runner=lambda progress_callback: _build_failed_rescoring_result(
                user=user,
                store=store,
                metrics_store=metrics_store,
                progress_callback=progress_callback,
            ),
        )
    except ExamImportTaskCapacityError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=[str(exc)]) from exc
    return ExamImportTaskStatus(**record.to_dict())


@router.post("/api/exam-import/rows/{source_row}/score/tasks", response_model=ExamImportTaskStatus)
async def create_exam_import_row_score_task(
    source_row: int,
    user: AuthUser = Depends(require_user),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    task_registry: ExamImportTaskRegistry = Depends(get_exam_import_task_registry),
) -> ExamImportTaskStatus:
    if not is_test_user(user.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Тестовая страница недоступна."])

    if await _run_sync_io(store.get_entry, source_row) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Строка не найдена в базе импорта."])

    try:
        record = task_registry.create_task(
            task_type="row_score",
            source_row=source_row,
            runner=lambda progress_callback: _build_row_scoring_result(
                source_row=source_row,
                user=user,
                store=store,
                metrics_store=metrics_store,
            ),
        )
    except ExamImportTaskCapacityError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=[str(exc)]) from exc
    return ExamImportTaskStatus(**record.to_dict())


@router.get("/api/exam-import/tasks/{task_id}", response_model=ExamImportTaskStatus)
async def get_exam_import_task(
    task_id: str,
    user: AuthUser = Depends(require_user),
    task_registry: ExamImportTaskRegistry = Depends(get_exam_import_task_registry),
) -> ExamImportTaskStatus:
    if not is_test_user(user.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Тестовая страница недоступна."])

    record = task_registry.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Задача проверки не найдена."])
    return ExamImportTaskStatus(**record.to_dict())


@router.get("/api/exam-import/rows/{source_row}", response_model=ExamImportDetail)
async def exam_import_detail(
    source_row: int,
    user: AuthUser = Depends(require_user),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
) -> ExamImportDetail:
    if not is_test_user(user.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Тестовая страница недоступна."])

    entry = await _run_sync_io(store.get_entry, source_row)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Строка не найдена в базе импорта."])
    if entry.get("exam_scores"):
        _fill_question_g_fields(entry)
    entry["exam_scores"] = [ExamAnswerScore(**item).model_dump() for item in (entry.get("exam_scores") or [])]
    return ExamImportDetail(**_normalize_entry(entry))


@router.delete("/api/exam-import/rows/{source_row}/scores", response_model=ExamImportDetail)
async def clear_exam_import_row_scores(
    source_row: int,
    user: AuthUser = Depends(require_user),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
) -> ExamImportDetail:
    if not is_test_user(user.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Тестовая страница недоступна."])

    entry = await _run_sync_io(store.get_entry, source_row)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Строка не найдена в базе импорта."])

    cleared = await _run_sync_io(store.clear_scores_for_row, source_row)
    if not cleared:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Строка не найдена в базе импорта."])

    refreshed = await _run_sync_io(store.get_entry, source_row)
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Строка не найдена в базе импорта."])
    if refreshed.get("exam_scores"):
        _fill_question_g_fields(refreshed)
    refreshed["exam_scores"] = [ExamAnswerScore(**item).model_dump() for item in (refreshed.get("exam_scores") or [])]
    return ExamImportDetail(**_normalize_entry(refreshed))
