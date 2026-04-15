from __future__ import annotations

from threading import Lock
from typing import Any, Callable

from ogp_web.services import exam_import_service
from ogp_web.services.auth_service import AuthUser
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
