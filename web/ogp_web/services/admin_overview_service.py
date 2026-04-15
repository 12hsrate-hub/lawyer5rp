from __future__ import annotations

import logging
from typing import Any, Callable


LOGGER = logging.getLogger(__name__)


def build_law_jobs_overview_payload(*, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    law_tasks = [dict(task) for task in tasks if str(task.get("scope") or "") == "law_sources_rebuild"]
    failed = [task for task in law_tasks if str(task.get("status") or "") == "failed"]
    running = [task for task in law_tasks if str(task.get("status") or "") in {"queued", "running"}]
    alerts = [
        {
            "kind": "failed_rebuild",
            "task_id": task.get("task_id"),
            "server_code": task.get("server_code"),
            "error": task.get("error"),
        }
        for task in failed[:20]
    ]
    return {
        "ok": True,
        "summary": {
            "total_tasks": len(law_tasks),
            "running_tasks": len(running),
            "failed_tasks": len(failed),
            "alerts_count": len(alerts),
        },
        "alerts": alerts,
        "running": running[:20],
    }


def build_async_jobs_overview_payload(*, items: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_items = [dict(item) for item in items]
    problem_statuses = {"failed", "retry_scheduled"}
    problem_items = [item for item in normalized_items if str(item.get("canonical_status") or "") in problem_statuses]
    failed_items = [item for item in normalized_items if str(item.get("canonical_status") or "") == "failed"]
    retry_items = [item for item in normalized_items if str(item.get("canonical_status") or "") == "retry_scheduled"]
    running_items = [item for item in normalized_items if str(item.get("canonical_status") or "") == "running"]

    by_type: dict[str, int] = {}
    for item in problem_items:
        job_type = str(item.get("job_type") or "unknown")
        by_type[job_type] = by_type.get(job_type, 0) + 1

    return {
        "ok": True,
        "summary": {
            "total_jobs": len(normalized_items),
            "problem_jobs": len(problem_items),
            "failed_jobs": len(failed_items),
            "retry_scheduled_jobs": len(retry_items),
            "running_jobs": len(running_items),
        },
        "problem_jobs": problem_items[:20],
        "by_job_type": [
            {"job_type": key, "count": value}
            for key, value in sorted(by_type.items(), key=lambda pair: (-pair[1], pair[0]))
        ],
    }


def build_exam_import_overview_payload(
    *,
    exam_store,
    metrics_store,
    include_recent_entries: bool = False,
    on_error: Callable[[str, Exception], None] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "pending_scores": 0,
        "last_sync": None,
        "last_score": None,
        "recent_failures": [],
        "recent_row_failures": [],
        "failed_entries": [],
    }
    if include_recent_entries:
        payload["recent_entries"] = []

    pending_scores = 0
    try:
        pending_scores = int(exam_store.count_entries_needing_scores() or 0)
    except Exception as exc:  # noqa: BLE001
        _report_error("exam_pending_scores", exc, on_error=on_error)

    try:
        payload = dict(metrics_store.get_exam_import_summary(pending_scores=pending_scores) or {})
    except Exception as exc:  # noqa: BLE001
        _report_error("exam_summary", exc, on_error=on_error)
        payload["pending_scores"] = pending_scores

    try:
        payload["failed_entries"] = list(exam_store.list_entries_with_failed_scores(limit=5))
    except Exception as exc:  # noqa: BLE001
        _report_error("exam_failed_entries", exc, on_error=on_error)
        payload["failed_entries"] = []

    if include_recent_entries:
        try:
            payload["recent_entries"] = list(exam_store.list_entries(limit=8))
        except Exception as exc:  # noqa: BLE001
            _report_error("exam_recent_entries", exc, on_error=on_error)
            payload["recent_entries"] = []

    recent_failures = list(payload.get("recent_failures") or [])
    recent_row_failures = list(payload.get("recent_row_failures") or [])
    failed_entries = list(payload.get("failed_entries") or [])
    payload["recent_failures"] = recent_failures
    payload["recent_row_failures"] = recent_row_failures
    payload["failed_entries"] = failed_entries[:5]
    payload["pending_scores"] = int(payload.get("pending_scores") or pending_scores or 0)
    payload["summary"] = {
        "pending_scores": int(payload.get("pending_scores") or 0),
        "failed_entries": len(failed_entries),
        "recent_failures": len(recent_failures),
        "recent_row_failures": len(recent_row_failures),
        "problem_signals": len(failed_entries) + len(recent_failures) + len(recent_row_failures),
    }
    if include_recent_entries:
        payload["recent_entries"] = list(payload.get("recent_entries") or [])[:8]
    return payload


def _report_error(source: str, exc: Exception, *, on_error: Callable[[str, Exception], None] | None) -> None:
    if on_error is not None:
        on_error(source, exc)
        return
    LOGGER.warning("admin_exam_import_overview_failed source=%s error=%s", source, exc)
