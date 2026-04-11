from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from fastapi import HTTPException, status

from ogp_web.schemas import ExamAnswerScore, ExamImportDetail, ExamImportEntry, ExamImportResponse
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from shared.ogp_ai import DEFAULT_INVALID_BATCH_RATIONALE, score_exam_answer_with_proxy_fallback
from shared.ogp_ai import score_exam_answers_batch_with_proxy_fallback


logger = logging.getLogger(__name__)
RETRY_BATCH_CHUNK_SIZE = 4
_SCORING_STAT_KEYS = (
    "answer_count",
    "heuristic_count",
    "cache_hit_count",
    "llm_count",
    "llm_calls",
    "invalid_batch_item_count",
    "retry_batch_items",
    "retry_batch_calls",
    "retry_single_items",
    "retry_single_calls",
    "scoring_ms",
)
_SCORING_META_KEYS = ("prompt_mode", "prompt_version", "single_prompt_version")


def _empty_scoring_stats() -> dict[str, object]:
    stats: dict[str, object] = {key: 0 for key in _SCORING_STAT_KEYS}
    stats.update({key: "" for key in _SCORING_META_KEYS})
    return stats


def _merge_scoring_stats(target: dict[str, object], extra: dict[str, object], *, include_answer_count: bool = True) -> None:
    for key in _SCORING_STAT_KEYS:
        if key == "answer_count" and not include_answer_count:
            continue
        target[key] = int(target.get(key) or 0) + int(extra.get(key) or 0)
    for key in _SCORING_META_KEYS:
        current = str(target.get(key) or "").strip()
        incoming = str(extra.get(key) or "").strip()
        if not current and incoming:
            target[key] = incoming


def _is_invalid_batch_result(result: dict[str, object] | None) -> bool:
    rationale = str((result or {}).get("rationale") or "").strip()
    return rationale == DEFAULT_INVALID_BATCH_RATIONALE


def _append_stage(stage_trace: dict[str, list[str]], column: str, stage: str) -> None:
    stage_trace.setdefault(str(column), []).append(stage)


def _normalize_exam_column_key(column: object) -> str:
    normalized = str(column or "").strip().upper()
    return re.sub(r"\s+", "", normalized)


def _log_stage_trace(
    *,
    source_row: int,
    column: str,
    stages: list[str],
    result: dict[str, object] | None,
) -> None:
    logger.warning(
        "Exam scoring stage trace source_row=%s column=%s stages=%s final_score=%s final_rationale=%s",
        source_row,
        column,
        " > ".join(stages),
        (result or {}).get("score"),
        str((result or {}).get("rationale") or "").strip(),
    )


def fill_question_g_fields(entry: dict[str, object]) -> None:
    question_g = next((item for item in (entry.get("exam_scores") or []) if item["column"] == "G"), None)
    if question_g:
        entry["question_g_header"] = question_g["header"]
        entry["question_g_answer"] = question_g["user_answer"]
        entry["question_g_score"] = question_g["score"]
        entry["question_g_rationale"] = question_g["rationale"]
    else:
        entry["question_g_header"] = ""
        entry["question_g_answer"] = ""
        entry["question_g_score"] = None
        entry["question_g_rationale"] = ""


def normalize_entry(entry: dict[str, object]) -> dict[str, object]:
    normalized = dict(entry)
    normalized["average_score_answer_count"] = int(normalized.get("average_score_answer_count") or 0)
    normalized["average_score_scored_at"] = str(normalized.get("average_score_scored_at") or "")
    normalized["question_g_header"] = str(normalized.get("question_g_header") or "")
    normalized["question_g_answer"] = str(normalized.get("question_g_answer") or "")
    normalized["question_g_rationale"] = str(normalized.get("question_g_rationale") or "")
    normalized["updated_at"] = str(normalized.get("updated_at") or "")
    normalized["imported_at"] = str(normalized.get("imported_at") or "")
    normalized["submitted_at"] = str(normalized.get("submitted_at") or "")
    normalized["full_name"] = str(normalized.get("full_name") or "")
    normalized["discord_tag"] = str(normalized.get("discord_tag") or "")
    normalized["passport"] = str(normalized.get("passport") or "")
    normalized["exam_format"] = str(normalized.get("exam_format") or "")
    normalized["payload"] = normalized.get("payload") or {}
    normalized["exam_scores"] = normalized.get("exam_scores") or []
    return normalized


def retry_invalid_batch_scores(
    *,
    api_key: str,
    proxy_url: str,
    source_row: int,
    score_items: list[dict[str, str]],
    results: dict[str, dict[str, object]],
    stats: dict[str, object],
) -> dict[str, dict[str, object]]:
    item_by_column = {_normalize_exam_column_key(item["column"]): item for item in score_items}
    retried_results = dict(results)
    normalized_results = {_normalize_exam_column_key(column): result for column, result in results.items()}
    invalid_columns = [column for column, result in normalized_results.items() if _is_invalid_batch_result(result)]
    invalid_items = [item_by_column[column] for column in invalid_columns if column in item_by_column]
    for column, result in normalized_results.items():
        retried_results[column] = result
    stage_trace: dict[str, list[str]] = {}
    for column in invalid_columns:
        _append_stage(stage_trace, column, "batch_initial")
        _append_stage(stage_trace, column, "invalid_batch")
    stats["invalid_batch_item_count"] += len(invalid_items)

    if len(invalid_items) > 1:
        for item in invalid_items:
            _append_stage(stage_trace, str(item["column"]), "retry_batch")
        try:
            retry_results, retry_stats = score_exam_answers_batch_with_proxy_fallback(
                api_key=api_key,
                proxy_url=proxy_url,
                items=invalid_items,
                return_stats=True,
                chunk_size=RETRY_BATCH_CHUNK_SIZE,
            )
            stats["retry_batch_items"] += len(invalid_items)
            stats["retry_batch_calls"] += int(retry_stats.get("llm_calls") or 0)
            _merge_scoring_stats(stats, retry_stats, include_answer_count=False)
            for column, result in retry_results.items():
                normalized_column = _normalize_exam_column_key(column)
                retried_results[normalized_column] = result
                if _is_invalid_batch_result(result):
                    _append_stage(stage_trace, normalized_column, "retry_batch_invalid")
                else:
                    _append_stage(stage_trace, normalized_column, "retry_batch_resolved")
        except Exception:
            logger.exception(
                "Mini-batch retry failed for source_row=%s invalid exam scoring items=%s",
                source_row,
                len(invalid_items),
            )
            for item in invalid_items:
                _append_stage(stage_trace, str(item["column"]), "retry_batch_failed")

    remaining_invalid_columns = [
        column for column in invalid_columns if _is_invalid_batch_result(retried_results.get(column))
    ]
    for column in remaining_invalid_columns:
        item = item_by_column.get(column)
        if not item:
            continue
        _append_stage(stage_trace, column, "retry_single")
        try:
            retried_results[str(column)] = score_exam_answer_with_proxy_fallback(
                api_key=api_key,
                proxy_url=proxy_url,
                user_answer=str(item["user_answer"] or ""),
                correct_answer=str(item["correct_answer"] or ""),
                column=str(item.get("column") or ""),
                question=str(item.get("question") or item.get("header") or ""),
                exam_type=str(item.get("exam_type") or ""),
                key_points=[str(point).strip() for point in (item.get("key_points") or []) if str(point).strip()],
            )
            stats["retry_single_items"] += 1
            stats["retry_single_calls"] += 1
            stats["llm_calls"] += 1
            stats["llm_count"] += 1
            _append_stage(stage_trace, column, "retry_single_resolved")
        except Exception:
            _append_stage(stage_trace, column, "retry_single_failed")
            logger.exception(
                "Single-score retry failed for source_row=%s column=%s after invalid batch result",
                source_row,
                column,
            )

    for column, stages in stage_trace.items():
        _log_stage_trace(
            source_row=source_row,
            column=column,
            stages=stages,
            result=retried_results.get(column),
        )
    return retried_results


def score_exam_answers_if_needed(
    store: ExamAnswersStore,
    entry: dict[str, object],
    *,
    build_exam_score_items,
    force_rescore: bool = False,
) -> tuple[bool, dict[str, object]]:
    payload = entry.get("payload") or {}
    empty_stats = _empty_scoring_stats()
    if not isinstance(payload, dict):
        entry["exam_scores"] = []
        fill_question_g_fields(entry)
        return False, empty_stats

    cached_scores = entry.get("exam_scores") or []
    needs_rescore = bool(entry.get("needs_rescore"))
    average_score = entry.get("average_score")
    should_use_cached_scores = bool(cached_scores) and not needs_rescore and not force_rescore and average_score is not None
    if should_use_cached_scores:
        entry["exam_scores"] = cached_scores
        fill_question_g_fields(entry)
        return False, empty_stats

    score_items = build_exam_score_items(payload)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    proxy_url = os.getenv("OPENAI_PROXY_URL", "").strip()
    start_ts = time.perf_counter()
    results, stats = score_exam_answers_batch_with_proxy_fallback(
        api_key=api_key,
        proxy_url=proxy_url,
        items=score_items,
        return_stats=True,
    )
    stats["scoring_ms"] = int((time.perf_counter() - start_ts) * 1000)
    results = retry_invalid_batch_scores(
        api_key=api_key,
        proxy_url=proxy_url,
        source_row=int(entry["source_row"]),
        score_items=score_items,
        results=results,
        stats=stats,
    )
    entry["exam_scores"] = [
        {
            **item,
            "score": int(
                results.get(_normalize_exam_column_key(item["column"]), {}).get("score", 1),
            ),
            "rationale": str(
                results.get(_normalize_exam_column_key(item["column"]), {}).get("rationale", "") or "",
            ),
        }
        for item in score_items
    ]
    store.save_exam_scores(source_row=int(entry["source_row"]), scores=entry["exam_scores"])
    refreshed = store.get_entry(int(entry["source_row"]))
    if refreshed is not None:
        entry.update(
            average_score=refreshed.get("average_score"),
            average_score_answer_count=refreshed.get("average_score_answer_count", 0),
            needs_rescore=refreshed.get("needs_rescore", 0),
        )
    fill_question_g_fields(entry)
    return True, stats


def entry_has_failed_fields(entry: dict[str, object]) -> bool:
    if bool(entry.get("needs_rescore")):
        return True
    for item in list(entry.get("exam_scores") or []):
        score = item.get("score")
        if score is None:
            continue
        if int(score) < 100:
            return True
    return False


def humanize_scoring_exception(exc: Exception) -> str:
    raw = str(exc).strip() or exc.__class__.__name__
    lower = raw.lower()
    if "capacity" in lower or "overloaded" in lower:
        return "Модель оценки сейчас перегружена. Попробуйте повторить проверку чуть позже."
    if "timeout" in lower:
        return "Проверка ответов превысила время ожидания. Попробуйте еще раз."
    if "api key" in lower or "invalid_api_key" in lower or "incorrect api key" in lower:
        return "На сервере возникла проблема с OPENAI_API_KEY."
    if "connection" in lower or "network" in lower or "proxy" in lower:
        return "Не удалось подключиться к OpenAI или прокси."
    return f"Не удалось завершить AI-проверку: {raw}"


def build_scoring_error_details(exc: Exception, source_row: int) -> list[str]:
    raw = str(exc).strip() or repr(exc)
    details = [
        humanize_scoring_exception(exc),
        f"Строка импорта: {source_row}",
        f"Тип ошибки: {exc.__class__.__name__}",
    ]
    if raw and raw != details[0]:
        details.append(f"Полная ошибка: {raw}")
    return details


def serialize_http_exception(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, list):
        return " ".join(str(item).strip() for item in detail if str(item).strip())
    return str(detail).strip() or "Не удалось завершить задачу."


def score_pending_rows(store: ExamAnswersStore, *, build_exam_score_items) -> tuple[int, dict[str, object], list[dict[str, object]]]:
    scored_count = 0
    aggregate_stats = _empty_scoring_stats()
    failures: list[dict[str, object]] = []
    pending_entries = store.list_entries_needing_scores(limit=500)
    for pending in pending_entries:
        detailed_entry = store.get_entry(int(pending["source_row"]))
        if detailed_entry is None:
            continue
        try:
            did_score, stats = score_exam_answers_if_needed(store, detailed_entry, build_exam_score_items=build_exam_score_items)
            if did_score:
                scored_count += 1
                _merge_scoring_stats(aggregate_stats, stats)
        except Exception as exc:
            source_row = int(pending["source_row"])
            logger.exception("Exam batch scoring failed for source_row=%s", source_row)
            failures.append({"source_row": source_row, "error": exc})
    return scored_count, aggregate_stats, failures


def score_pending_rows_with_progress(
    store: ExamAnswersStore,
    *,
    build_exam_score_items,
    progress_callback=None,
    mode: str = "missing_only",
) -> tuple[int, dict[str, object], list[dict[str, object]], int]:
    scored_count = 0
    processed_count = 0
    aggregate_stats = _empty_scoring_stats()
    failures: list[dict[str, object]] = []
    pending_entries = store.list_entries_needing_scores(limit=500)
    total_count = len(pending_entries)

    if progress_callback:
        progress_callback(
            {
                "mode": mode,
                "processed_count": 0,
                "total_count": total_count,
                "remaining_count": total_count,
                "scored_count": 0,
                "failed_count": 0,
                "current_source_row": None,
            }
        )

    for pending in pending_entries:
        detailed_entry = store.get_entry(int(pending["source_row"]))
        if detailed_entry is None:
            continue
        source_row = int(pending["source_row"])
        try:
            did_score, stats = score_exam_answers_if_needed(store, detailed_entry, build_exam_score_items=build_exam_score_items)
            if did_score:
                scored_count += 1
                _merge_scoring_stats(aggregate_stats, stats)
        except Exception as exc:
            logger.exception("Exam batch scoring failed for source_row=%s", source_row)
            failures.append({"source_row": source_row, "error": exc})
        finally:
            processed_count += 1
            if progress_callback:
                progress_callback(
                    {
                        "mode": mode,
                        "processed_count": processed_count,
                        "total_count": total_count,
                        "remaining_count": max(total_count - processed_count, 0),
                        "scored_count": scored_count,
                        "failed_count": len(failures),
                        "current_source_row": source_row,
                    }
                )

    return scored_count, aggregate_stats, failures, total_count


def build_entries_response(store: ExamAnswersStore) -> list[ExamImportEntry]:
    latest_entries_raw = store.list_entries()
    return [ExamImportEntry(**normalize_entry(entry)) for entry in latest_entries_raw]


def build_failed_fields(scores: list[dict[str, object]]) -> list[dict[str, object]]:
    failed_fields: list[dict[str, object]] = []
    for item in scores:
        score = item.get("score")
        if score is None:
            continue
        numeric_score = int(score)
        if numeric_score >= 100:
            continue
        failed_fields.append(
            {
                "column": str(item.get("column") or ""),
                "header": str(item.get("header") or ""),
                "score": numeric_score,
                "rationale": str(item.get("rationale") or ""),
            }
        )
    return failed_fields


def build_bulk_scoring_result(
    *,
    user,
    store: ExamAnswersStore,
    metrics_store: AdminMetricsStore,
    exam_sheet_url: str,
    build_exam_score_items,
    progress_callback=None,
) -> dict[str, object]:
    scored_count, scoring_stats, failures, _ = score_pending_rows_with_progress(
        store,
        build_exam_score_items=build_exam_score_items,
        progress_callback=progress_callback,
        mode="missing_only",
    )
    if scored_count:
        metrics_store.log_event(
            event_type="ai_exam_scoring",
            username=user.username,
            path="/api/exam-import/score",
            method="POST",
            status_code=200,
            resource_units=int(scoring_stats.get("llm_count") or 0),
            meta={**scoring_stats, "rows_scored": scored_count},
        )
    if failures:
        metrics_store.log_event(
            event_type="exam_import_score_failures",
            username=user.username,
            path="/api/exam-import/score",
            method="POST",
            status_code=502 if scored_count == 0 else 200,
            meta={
                "scored_count": scored_count,
                "failed_count": len(failures),
                "failed_rows": [int(item["source_row"]) for item in failures[:20]],
                **scoring_stats,
            },
        )
    if failures and scored_count == 0:
        first_failure = failures[0]
        raise RuntimeError(" ".join(build_scoring_error_details(first_failure["error"], int(first_failure["source_row"]))))

    latest_entries = build_entries_response(store)
    failed_rows: list[dict[str, object]] = []
    for entry_summary in latest_entries:
        detailed_entry = store.get_entry(int(entry_summary.source_row))
        if detailed_entry is None:
            continue
        failed_fields = build_failed_fields(list(detailed_entry.get("exam_scores") or []))
        if not failed_fields:
            continue
        failed_rows.append(
            {
                "source_row": int(entry_summary.source_row),
                "full_name": str(entry_summary.full_name or ""),
                "average_score": entry_summary.average_score,
                "failed_fields": failed_fields,
            }
        )

    result = ExamImportResponse(
        sheet_url=exam_sheet_url,
        total_rows=store.count(),
        imported_count=0,
        inserted_count=0,
        updated_count=0,
        skipped_count=0,
        scored_count=scored_count,
        latest_entries=latest_entries,
    ).model_dump()
    result["failed_rows"] = failed_rows
    result["failed_field_count"] = sum(len(item["failed_fields"]) for item in failed_rows)
    return result


def build_failed_rescoring_result(
    *,
    user,
    store: ExamAnswersStore,
    metrics_store: AdminMetricsStore,
    exam_sheet_url: str,
    build_exam_score_items,
    progress_callback=None,
) -> dict[str, object]:
    rescored_count = 0
    scoring_stats = _empty_scoring_stats()
    failures: list[dict[str, object]] = []
    candidates = store.list_entries_with_failed_scores(limit=500)

    for candidate in candidates:
        source_row = int(candidate["source_row"])
        detailed_entry = store.get_entry(source_row)
        if detailed_entry is None or not entry_has_failed_fields(detailed_entry):
            continue
        try:
            did_score, stats = score_exam_answers_if_needed(
                store,
                detailed_entry,
                build_exam_score_items=build_exam_score_items,
                force_rescore=True,
            )
            if did_score:
                rescored_count += 1
                _merge_scoring_stats(scoring_stats, stats)
        except Exception as exc:
            logger.exception("Exam failed-row rescoring failed for source_row=%s", source_row)
            failures.append({"source_row": source_row, "error": exc})
        finally:
            processed_total = rescored_count + len(failures)
            if progress_callback:
                progress_callback(
                    {
                        "mode": "failed_only",
                        "processed_count": processed_total,
                        "total_count": len(candidates),
                        "remaining_count": max(len(candidates) - processed_total, 0),
                        "scored_count": rescored_count,
                        "failed_count": len(failures),
                        "current_source_row": source_row,
                    }
                )

    if rescored_count:
        metrics_store.log_event(
            event_type="ai_exam_scoring",
            username=user.username,
            path="/api/exam-import/rescore-failed",
            method="POST",
            status_code=200,
            resource_units=int(scoring_stats.get("llm_count") or 0),
            meta={**scoring_stats, "rows_scored": rescored_count, "mode": "failed_only"},
        )
    if failures:
        metrics_store.log_event(
            event_type="exam_import_score_failures",
            username=user.username,
            path="/api/exam-import/rescore-failed",
            method="POST",
            status_code=502 if rescored_count == 0 else 200,
            meta={
                "scored_count": rescored_count,
                "failed_count": len(failures),
                "failed_rows": [int(item["source_row"]) for item in failures[:20]],
                "mode": "failed_only",
                **scoring_stats,
            },
        )
    if failures and rescored_count == 0:
        first_failure = failures[0]
        raise RuntimeError(" ".join(build_scoring_error_details(first_failure["error"], int(first_failure["source_row"]))))

    latest_entries = build_entries_response(store)
    failed_rows: list[dict[str, object]] = []
    for entry_summary in latest_entries:
        detailed_entry = store.get_entry(int(entry_summary.source_row))
        if detailed_entry is None:
            continue
        failed_fields = build_failed_fields(list(detailed_entry.get("exam_scores") or []))
        if not failed_fields:
            continue
        failed_rows.append(
            {
                "source_row": int(entry_summary.source_row),
                "full_name": str(entry_summary.full_name or ""),
                "average_score": entry_summary.average_score,
                "failed_fields": failed_fields,
            }
        )

    result = ExamImportResponse(
        sheet_url=exam_sheet_url,
        total_rows=store.count(),
        imported_count=0,
        inserted_count=0,
        updated_count=0,
        skipped_count=0,
        scored_count=rescored_count,
        latest_entries=latest_entries,
    ).model_dump()
    result["failed_rows"] = failed_rows
    result["failed_field_count"] = sum(len(item["failed_fields"]) for item in failed_rows)
    result["rescored_failed_count"] = rescored_count
    return result


def build_row_scoring_result(
    *,
    source_row: int,
    user,
    store: ExamAnswersStore,
    metrics_store: AdminMetricsStore,
    build_exam_score_items,
    force_rescore: bool = False,
) -> dict[str, object]:
    entry = store.get_entry(source_row)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Строка не найдена в базе импорта."])

    try:
        did_score, scoring_stats = score_exam_answers_if_needed(
            store,
            entry,
            build_exam_score_items=build_exam_score_items,
            force_rescore=force_rescore,
        )
    except Exception as exc:
        logger.exception("Exam row scoring failed for source_row=%s", source_row)
        metrics_store.log_event(
            event_type="exam_import_row_score_error",
            username=user.username,
            path=f"/api/exam-import/rows/{source_row}/score",
            method="POST",
            status_code=502,
            meta={"source_row": source_row, "error": str(exc), "error_type": exc.__class__.__name__},
        )
        raise RuntimeError(" ".join(build_scoring_error_details(exc, source_row))) from exc

    if did_score:
        metrics_store.log_event(
            event_type="ai_exam_scoring",
            username=user.username,
            path=f"/api/exam-import/rows/{source_row}/score",
            method="POST",
            status_code=200,
            resource_units=int(scoring_stats.get("llm_count") or 0),
            meta={**scoring_stats, "rows_scored": 1, "source_row": source_row},
        )

    refreshed = store.get_entry(source_row) or entry
    if refreshed.get("exam_scores"):
        fill_question_g_fields(refreshed)
    refreshed["exam_scores"] = [ExamAnswerScore(**item).model_dump() for item in (refreshed.get("exam_scores") or [])]
    result = ExamImportDetail(**normalize_entry(refreshed)).model_dump()
    result["failed_fields"] = build_failed_fields(list(refreshed.get("exam_scores") or []))
    return result
