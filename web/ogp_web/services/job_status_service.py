from __future__ import annotations

from typing import Any


_CANONICAL_STATE_MAP: dict[str, dict[str, str]] = {
    "async_job": {
        "pending": "queued",
        "queued": "queued",
        "processing": "running",
        "succeeded": "succeeded",
        "dead_lettered": "failed",
        "cancelled": "cancelled",
        "failed": "failed",
        "retry_scheduled": "retry_scheduled",
        "running": "running",
    },
    "exam_import": {
        "queued": "queued",
        "running": "running",
        "completed": "succeeded",
        "succeeded": "succeeded",
        "failed": "failed",
        "cancelled": "cancelled",
        "retry_scheduled": "retry_scheduled",
    },
    "admin_task": {
        "queued": "queued",
        "running": "running",
        "finished": "succeeded",
        "completed": "succeeded",
        "succeeded": "succeeded",
        "failed": "failed",
        "cancelled": "cancelled",
        "retry_scheduled": "retry_scheduled",
    },
}


def normalize_job_status(raw_status: Any, *, subsystem: str) -> str:
    normalized_subsystem = str(subsystem or "").strip().lower()
    normalized_status = str(raw_status or "").strip().lower()
    if not normalized_status:
        return "failed"
    mapping = _CANONICAL_STATE_MAP.get(normalized_subsystem, {})
    return mapping.get(normalized_status, normalized_status)


def enrich_job_status(payload: dict[str, Any], *, subsystem: str) -> dict[str, Any]:
    item = dict(payload or {})
    raw_status = str(item.get("raw_status") or item.get("status") or "").strip().lower()
    item["raw_status"] = raw_status
    item["canonical_status"] = normalize_job_status(raw_status, subsystem=subsystem)
    return item
