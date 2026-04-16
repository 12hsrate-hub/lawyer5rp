from __future__ import annotations

from threading import Lock
from typing import Any, Callable

from fastapi import HTTPException, status

from ogp_web.services import exam_import_service
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.exam_import_tasks import ExamImportTaskCapacityError, ExamImportTaskRegistry
from ogp_web.services.job_status_service import enrich_job_status
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore


class ExamImportRuntimeService:
    def __init__(self) -> None:
        self._scoring_wrapper_lock = Lock()

    def _run_with_scoring_injection(
        self,
        *,
        score_if_needed_func: Callable[[ExamAnswersStore, dict[str, object]], tuple[bool, dict[str, int]]],
        batch_score_func: Callable[..., Any],
        single_score_func: Callable[..., Any],
        runner: Callable[[], dict[str, object]],
    ) -> dict[str, object]:
        with self._scoring_wrapper_lock:
            original_batch = exam_import_service.score_exam_answers_batch_with_proxy_fallback
            original_single = exam_import_service.score_exam_answer_with_proxy_fallback
            original_score = exam_import_service.score_exam_answers_if_needed
            exam_import_service.score_exam_answers_batch_with_proxy_fallback = batch_score_func
            exam_import_service.score_exam_answer_with_proxy_fallback = single_score_func
            exam_import_service.score_exam_answers_if_needed = lambda store_arg, entry_arg, **_: score_if_needed_func(
                store_arg,
                entry_arg,
            )
            try:
                return runner()
            finally:
                exam_import_service.score_exam_answers_batch_with_proxy_fallback = original_batch
                exam_import_service.score_exam_answer_with_proxy_fallback = original_single
                exam_import_service.score_exam_answers_if_needed = original_score

    def build_bulk_scoring_result(
        self,
        *,
        user: AuthUser,
        store: ExamAnswersStore,
        metrics_store: AdminMetricsStore,
        exam_sheet_url: str,
        build_exam_score_items: Callable[..., Any],
        score_if_needed_func: Callable[[ExamAnswersStore, dict[str, object]], tuple[bool, dict[str, int]]],
        batch_score_func: Callable[..., Any],
        single_score_func: Callable[..., Any],
        progress_callback=None,
    ) -> dict[str, object]:
        return self._run_with_scoring_injection(
            score_if_needed_func=score_if_needed_func,
            batch_score_func=batch_score_func,
            single_score_func=single_score_func,
            runner=lambda: exam_import_service.build_bulk_scoring_result(
                user=user,
                store=store,
                metrics_store=metrics_store,
                exam_sheet_url=exam_sheet_url,
                build_exam_score_items=build_exam_score_items,
                progress_callback=progress_callback,
            ),
        )

    def build_row_scoring_result(
        self,
        *,
        source_row: int,
        user: AuthUser,
        store: ExamAnswersStore,
        metrics_store: AdminMetricsStore,
        build_exam_score_items: Callable[..., Any],
        score_if_needed_func: Callable[[ExamAnswersStore, dict[str, object]], tuple[bool, dict[str, int]]],
        batch_score_func: Callable[..., Any],
        single_score_func: Callable[..., Any],
        force_rescore: bool = False,
    ) -> dict[str, object]:
        return self._run_with_scoring_injection(
            score_if_needed_func=score_if_needed_func,
            batch_score_func=batch_score_func,
            single_score_func=single_score_func,
            runner=lambda: exam_import_service.build_row_scoring_result(
                source_row=source_row,
                user=user,
                store=store,
                metrics_store=metrics_store,
                build_exam_score_items=build_exam_score_items,
                force_rescore=force_rescore,
            ),
        )

    def build_failed_rescoring_result(
        self,
        *,
        user: AuthUser,
        store: ExamAnswersStore,
        metrics_store: AdminMetricsStore,
        exam_sheet_url: str,
        build_exam_score_items: Callable[..., Any],
        score_if_needed_func: Callable[[ExamAnswersStore, dict[str, object]], tuple[bool, dict[str, int]]],
        batch_score_func: Callable[..., Any],
        single_score_func: Callable[..., Any],
        progress_callback=None,
    ) -> dict[str, object]:
        return self._run_with_scoring_injection(
            score_if_needed_func=score_if_needed_func,
            batch_score_func=batch_score_func,
            single_score_func=single_score_func,
            runner=lambda: exam_import_service.build_failed_rescoring_result(
                user=user,
                store=store,
                metrics_store=metrics_store,
                exam_sheet_url=exam_sheet_url,
                build_exam_score_items=build_exam_score_items,
                progress_callback=progress_callback,
            ),
        )

    def build_sync_import_response(
        self,
        *,
        user: AuthUser,
        store: ExamAnswersStore,
        metrics_store: AdminMetricsStore,
        exam_sheet_url: str,
        fetch_rows: Callable[..., list[dict[str, object]]],
        build_entries_response: Callable[..., list[object]],
    ) -> dict[str, object]:
        try:
            rows = fetch_rows(force_refresh=True)
            stats = store.import_rows(rows)
        except Exception as exc:
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

        return {
            "sheet_url": exam_sheet_url,
            "total_rows": stats["total_rows"],
            "imported_count": len(rows),
            "inserted_count": stats["inserted_count"],
            "updated_count": stats["updated_count"],
            "skipped_count": int(stats.get("skipped_count", 0)),
            "scored_count": 0,
            "latest_entries": build_entries_response(store),
        }

    def create_task_status(
        self,
        *,
        task_registry: ExamImportTaskRegistry,
        task_type: str,
        runner: Callable[..., dict[str, object]],
        source_row: int | None = None,
    ) -> dict[str, object]:
        try:
            record = task_registry.create_task(
                task_type=task_type,
                source_row=source_row,
                runner=runner,
            )
        except ExamImportTaskCapacityError as exc:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=[str(exc)]) from exc
        return enrich_job_status(record.to_dict(), subsystem="exam_import")

    def get_task_status(
        self,
        *,
        task_registry: ExamImportTaskRegistry,
        task_id: str,
    ) -> dict[str, object]:
        record = task_registry.get_task(task_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Задача проверки не найдена."])
        return enrich_job_status(record.to_dict(), subsystem="exam_import")

    def require_entry(
        self,
        *,
        store: ExamAnswersStore,
        source_row: int,
    ) -> dict[str, object]:
        entry = store.get_entry(source_row)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Строка не найдена в базе импорта."])
        return entry

    def build_entry_detail(
        self,
        *,
        entry: dict[str, object],
        fill_question_g_fields: Callable[[dict[str, object]], None],
        normalize_entry: Callable[[dict[str, object]], dict[str, object]],
        score_serializer: Callable[[dict[str, object]], dict[str, object]],
    ) -> dict[str, object]:
        if entry.get("exam_scores"):
            fill_question_g_fields(entry)
        entry["exam_scores"] = [score_serializer(item) for item in (entry.get("exam_scores") or [])]
        return normalize_entry(entry)

    def clear_row_scores_and_build_detail(
        self,
        *,
        store: ExamAnswersStore,
        source_row: int,
        fill_question_g_fields: Callable[[dict[str, object]], None],
        normalize_entry: Callable[[dict[str, object]], dict[str, object]],
        score_serializer: Callable[[dict[str, object]], dict[str, object]],
    ) -> dict[str, object]:
        self.require_entry(store=store, source_row=source_row)
        cleared = store.clear_scores_for_row(source_row)
        if not cleared:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Строка не найдена в базе импорта."])
        refreshed = self.require_entry(store=store, source_row=source_row)
        return self.build_entry_detail(
            entry=refreshed,
            fill_question_g_fields=fill_question_g_fields,
            normalize_entry=normalize_entry,
            score_serializer=score_serializer,
        )
