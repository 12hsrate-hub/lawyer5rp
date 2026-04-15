from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any
from time import monotonic
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response
from datetime import datetime, timezone

from ogp_web.dependencies import get_content_workflow_service
from ogp_web.dependencies import get_admin_dashboard_service, get_admin_metrics_store, get_exam_answers_store, get_user_store, requires_permission
from ogp_web.dependencies import get_runtime_law_sets_store, get_runtime_servers_store
from ogp_web.server_config import get_server_config
from ogp_web.schemas import (
    AdminBlockPayload,
    AdminBulkActionPayload,
    AdminCatalogItemPayload,
    AdminCatalogRollbackPayload,
    AdminCatalogWorkflowPayload,
    AdminDeactivatePayload,
    AdminEmailUpdatePayload,
    AdminExamScoreResetPayload,
    AdminLawSourcesPayload,
    AdminLawSetPayload,
    AdminLawSetRebuildPayload,
    AdminLawSetRollbackPayload,
    AdminLawSourceRegistryPayload,
    AdminServerLawBindingPayload,
    AdminPasswordResetPayload,
    AdminQuotaPayload,
    AdminRuntimeServerPayload,
    DocumentVersionProvenanceResponse,
)
from ogp_web.services.law_admin_service import LawAdminService
from ogp_web.services.law_bundle_service import load_law_bundle_meta
from ogp_web.services.law_rebuild_tasks import find_active_law_rebuild_task
from ogp_web.services.law_version_service import resolve_active_law_version
from ogp_web.services.admin_overview_service import (
    build_async_jobs_overview_payload,
    build_exam_import_overview_payload,
    build_law_jobs_overview_payload,
)
from ogp_web.services.auth_service import AuthError, AuthUser, require_admin_user
from ogp_web.services.generated_document_trace_service import (
    list_admin_recent_generated_documents,
    require_admin_generated_document_trace_bundle,
    resolve_generated_document_provenance_payload_from_bundle,
    resolve_generated_document_review_context_payload_from_bundle,
)
from ogp_web.services.point3_policy_service import load_point3_eval_thresholds
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.content_contracts import normalize_content_type
from ogp_web.services.server_context_service import (
    extract_server_shell_context,
    resolve_user_server_context,
    resolve_user_server_permissions,
)
from ogp_web.services.async_job_service import AsyncJobService
from ogp_web.services.job_status_service import enrich_job_status
from ogp_web.services.admin_dashboard_service import AdminDashboardService
from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_server_health_payload,
    create_runtime_server_payload,
    list_runtime_servers_payload,
    set_runtime_server_active_payload,
    update_runtime_server_payload,
)
from ogp_web.services.admin_law_sets_service import (
    add_runtime_server_law_binding_payload,
    create_law_source_registry_payload,
    create_runtime_server_law_set_payload,
    list_law_source_registry_payload,
    list_runtime_server_law_bindings_payload,
    list_runtime_server_law_sets_payload,
    publish_law_set_payload,
    resolve_law_set_rebuild_context,
    resolve_law_set_rollback_context,
    update_law_set_payload,
    update_law_source_registry_payload,
)
from ogp_web.services.synthetic_runner_service import SyntheticRunnerService
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_store import UserStore
from ogp_web.storage.runtime_servers_store import RuntimeServerRecord, RuntimeServersStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.web import page_context, templates


router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)
_PERFORMANCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PERFORMANCE_CACHE_TTL_SECONDS = 10
_PERFORMANCE_CACHE_LOCK = threading.Lock()
_ADMIN_TASKS: dict[str, dict[str, Any]] = {}
_ADMIN_TASKS_LOCK = threading.Lock()
_ADMIN_TASKS_PATH = Path(__file__).resolve().parents[3] / "web" / "data" / "admin_tasks.json"
_MODEL_POLICY_PATH = Path(__file__).resolve().parents[3] / "config" / "model_policy.yaml"

_BLUEPRINT_STAGE_LABELS: dict[str, str] = {
    "phase_a_foundation": "Phase A — Stabilize foundation",
    "phase_b_visual_workflows": "Phase B — Visual workflows",
    "phase_c_quality_center": "Phase C — Quality command center",
    "phase_d_scale_out": "Phase D — Multi-server scale-out",
}


def _resolve_admin_platform_stage() -> dict[str, str]:
    raw_stage = str(os.getenv("OGP_ADMIN_PLATFORM_STAGE", "phase_a_foundation") or "").strip().lower()
    stage_code = raw_stage if raw_stage in _BLUEPRINT_STAGE_LABELS else "phase_a_foundation"
    return {
        "stage_code": stage_code,
        "stage_label": _BLUEPRINT_STAGE_LABELS[stage_code],
    }


def _point3_monitoring_threshold(level: str, metric: str, fallback: float) -> float:
    payload = load_point3_eval_thresholds()
    monitoring = payload.get("monitoring") if isinstance(payload, dict) else {}
    level_payload = monitoring.get(level) if isinstance(monitoring, dict) else {}
    try:
        value = float((level_payload or {}).get(metric))
    except (TypeError, ValueError, AttributeError):
        value = fallback
    return value * 100.0


def _cache_key(*, window_minutes: int, top_endpoints: int) -> str:
    return f"{window_minutes}:{top_endpoints}"


def _load_cached_performance_payload(cache_key: str) -> dict[str, Any] | None:
    with _PERFORMANCE_CACHE_LOCK:
        now = monotonic()
        cached = _PERFORMANCE_CACHE.get(cache_key)
        if not cached:
            return None
        cached_at, payload = cached
        if now - cached_at > _PERFORMANCE_CACHE_TTL_SECONDS:
            _PERFORMANCE_CACHE.pop(cache_key, None)
            return None
        payload["cached"] = True
        return deepcopy(payload)


def _store_performance_payload(cache_key: str, payload: dict[str, Any]) -> None:
    with _PERFORMANCE_CACHE_LOCK:
        _PERFORMANCE_CACHE[cache_key] = (monotonic(), deepcopy(payload))


def _raise_admin_http_error(*, status_code: int, code: str, message: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail=[message],
        headers={"X-Error-Code": code},
    )


def _normalize_api_error(exc: Exception, *, source: str) -> dict[str, str]:
    return {
        "source": source,
        "message": str(exc) or f"{source}_error",
    }


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().lower()


def _detail_lines(*items: Any) -> list[str]:
    lines = [str(item or "").strip() for item in items]
    return [line for line in lines if line]


def _raise_http_error(status_code: int, *detail: Any) -> None:
    raise HTTPException(status_code=status_code, detail=_detail_lines(*detail))


def _raise_bad_request(*detail: Any) -> None:
    _raise_http_error(status.HTTP_400_BAD_REQUEST, *detail)


def _raise_not_found(*detail: Any) -> None:
    _raise_http_error(status.HTTP_404_NOT_FOUND, *detail)


def _admin_ok(**payload: Any) -> dict[str, Any]:
    return {"ok": True, **payload}


def _normalize_admin_catalog_entity_type(entity_type: str) -> str:
    return normalize_content_type(entity_type, allow_legacy_import_alias=True)


def _get_async_job_service(request: Request, user_store: UserStore) -> AsyncJobService:
    queue_provider = getattr(request.app.state, "queue_provider", None)
    return AsyncJobService(user_store.backend, queue_provider=queue_provider)


def _load_model_policy() -> dict[str, Any]:
    if not _MODEL_POLICY_PATH.exists():
        return {}
    try:
        payload = yaml.safe_load(_MODEL_POLICY_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"failed_to_load_model_policy: {exc}") from exc
    return payload if isinstance(payload, dict) else {}


def _parse_metric_event_timestamp(value: Any) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _filter_recent_metric_items(items: list[dict[str, Any]], *, since_hours: int = 24) -> list[dict[str, Any]]:
    safe_hours = max(0, int(since_hours or 0))
    if safe_hours <= 0:
        return list(items)
    threshold = datetime.now(timezone.utc).timestamp() - safe_hours * 3600
    filtered: list[dict[str, Any]] = []
    for item in items:
        parsed = _parse_metric_event_timestamp(item.get("created_at"))
        if parsed is None or parsed.timestamp() >= threshold:
            filtered.append(item)
    return filtered


def _round_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100.0, 2)


def _safe_float(value: Any, default: float = 0.0, *, generation_id: str = "", field: str = "value") -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(
            "admin_ai_pipeline_invalid_float generation_id=%s field=%s raw_value=%r",
            generation_id or "unknown",
            field,
            value,
        )
        return default


def _band_from_thresholds(value: float | None, *, green_max: float, yellow_max: float) -> str:
    if value is None:
        return "unknown"
    if value < green_max:
        return "green"
    if value <= yellow_max:
        return "yellow"
    return "red"


AI_PIPELINE_RECENT_WINDOW_HOURS = 24
AI_PIPELINE_RECENT_HISTORY_LIMIT = 5000


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_synthetic_summary(recent_events: list[dict[str, Any]]) -> dict[str, Any]:
    run_events: list[dict[str, Any]] = []
    for event in recent_events:
        if str(event.get("event_type") or "") != "synthetic_run":
            continue
        raw_meta = event.get("meta_json") or event.get("meta") or {}
        if isinstance(raw_meta, str):
            try:
                raw_meta = json.loads(raw_meta)
            except Exception:  # noqa: BLE001
                raw_meta = {}
        if not isinstance(raw_meta, dict):
            raw_meta = {}
        run_events.append(
            {
                "run_id": str(raw_meta.get("run_id") or ""),
                "suite": str(raw_meta.get("suite") or ""),
                "status": str(raw_meta.get("run_status") or ""),
                "trigger": str(raw_meta.get("trigger") or ""),
                "created_at": event.get("created_at"),
                "steps_total": int(raw_meta.get("steps_total") or 0),
                "steps_failed": int(raw_meta.get("steps_failed") or 0),
            }
        )
    runs_by_suite: dict[str, dict[str, Any]] = {}
    for run in run_events:
        suite = run.get("suite") or "unknown"
        runs_by_suite.setdefault(suite, {"latest_status": "unknown", "last_run_at": None, "runs_total": 0, "failed_total": 0})
        bucket = runs_by_suite[suite]
        bucket["runs_total"] += 1
        if run.get("status") != "pass":
            bucket["failed_total"] += 1
        if bucket["last_run_at"] is None:
            bucket["last_run_at"] = run.get("created_at")
            bucket["latest_status"] = run.get("status") or "unknown"
    return {
        "runs": run_events[:20],
        "by_suite": runs_by_suite,
        "total_runs": len(run_events),
        "failed_runs": sum(1 for item in run_events if item.get("status") != "pass"),
    }


def _is_generation_fallback(meta: dict[str, Any]) -> bool:
    attempt_path = str(meta.get("attempt_path") or "").strip().lower()
    if meta.get("context_compacted"):
        return True
    return bool(attempt_path) and attempt_path not in {"direct", "proxy", "cache"}


def _summarize_generation_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    input_tokens: list[int] = []
    output_tokens: list[int] = []
    total_tokens: list[int] = []
    latency_values: list[int] = []
    retrieval_values: list[int] = []
    openai_values: list[int] = []
    total_suggest_values: list[int] = []
    estimated_cost_total = 0.0
    estimated_cost_count = 0
    budget_warning_count = 0
    models: dict[str, int] = {}
    retrieval_context_mode_counts: dict[str, int] = {}

    for row in rows:
        meta = row.get("meta") or {}
        model = str(meta.get("model") or "").strip()
        if model:
            models[model] = models.get(model, 0) + 1
        context_mode = str(meta.get("retrieval_context_mode") or "").strip().lower()
        if context_mode:
            retrieval_context_mode_counts[context_mode] = retrieval_context_mode_counts.get(context_mode, 0) + 1

        input_value = _safe_int(meta.get("input_tokens"))
        output_value = _safe_int(meta.get("output_tokens"))
        total_value = _safe_int(meta.get("total_tokens"))
        latency_value = _safe_int(meta.get("latency_ms"), default=-1)
        retrieval_value = _safe_int(meta.get("retrieval_ms"), default=-1)
        openai_value = _safe_int(meta.get("openai_ms"), default=-1)
        total_suggest_value = _safe_int(meta.get("total_suggest_ms"), default=-1)

        if input_value > 0:
            input_tokens.append(input_value)
        if output_value > 0:
            output_tokens.append(output_value)
        if total_value > 0:
            total_tokens.append(total_value)
        if latency_value >= 0:
            latency_values.append(latency_value)
        if retrieval_value >= 0:
            retrieval_values.append(retrieval_value)
        if openai_value >= 0:
            openai_values.append(openai_value)
        if total_suggest_value >= 0:
            total_suggest_values.append(total_suggest_value)

        if meta.get("estimated_cost_usd") not in (None, ""):
            cost_value = _safe_float(meta.get("estimated_cost_usd"), default=0.0)
            estimated_cost_total += cost_value
            estimated_cost_count += 1

        warnings = meta.get("budget_warnings") or ()
        if isinstance(warnings, list) and warnings:
            budget_warning_count += 1

    return {
        "total_generations": len(rows),
        "models": models,
        "retrieval_context_mode_counts": retrieval_context_mode_counts,
        "input_tokens_total": sum(input_tokens),
        "output_tokens_total": sum(output_tokens),
        "total_tokens_total": sum(total_tokens),
        "input_tokens_p50": AdminMetricsStore._percentile(input_tokens, 0.5),
        "total_tokens_p95": AdminMetricsStore._percentile(total_tokens, 0.95),
        "latency_ms_p50": AdminMetricsStore._percentile(latency_values, 0.5),
        "latency_ms_p95": AdminMetricsStore._percentile(latency_values, 0.95),
        "retrieval_ms_p50": AdminMetricsStore._percentile(retrieval_values, 0.5),
        "retrieval_ms_p95": AdminMetricsStore._percentile(retrieval_values, 0.95),
        "openai_ms_p50": AdminMetricsStore._percentile(openai_values, 0.5),
        "openai_ms_p95": AdminMetricsStore._percentile(openai_values, 0.95),
        "total_suggest_ms_p50": AdminMetricsStore._percentile(total_suggest_values, 0.5),
        "total_suggest_ms_p95": AdminMetricsStore._percentile(total_suggest_values, 0.95),
        "estimated_cost_total_usd": round(estimated_cost_total, 6),
        "estimated_cost_samples": estimated_cost_count,
        "budget_warning_count": budget_warning_count,
    }


def _build_ai_pipeline_quality_summary(
    *,
    generations: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
) -> dict[str, Any]:
    total_generations = len(generations)
    total_feedback = len(feedback)
    guard_fail_count = 0
    guard_warn_count = 0
    fallback_count = 0
    validation_retry_count = 0
    safe_fallback_count = 0
    issue_counts = {
        "wrong_law": 0,
        "wrong_fact": 0,
        "hallucination": 0,
        "unclear_answer": 0,
        "unsupported_article_reference": 0,
        "new_fact_detected": 0,
        "format_violation": 0,
    }

    for row in generations:
        meta = row.get("meta") or {}
        guard_status = str(meta.get("guard_status") or "").strip().lower()
        if guard_status == "fail":
            guard_fail_count += 1
        elif guard_status == "warn":
            guard_warn_count += 1
        if _is_generation_fallback(meta):
            fallback_count += 1
        validation_errors = {str(value or "").strip().lower() for value in meta.get("validation_errors") or []}
        for issue_key in ("unsupported_article_reference", "new_fact_detected", "format_violation"):
            if issue_key in validation_errors:
                issue_counts[issue_key] += 1
        if int(meta.get("validation_retry_count") or 0) > 0:
            validation_retry_count += 1
        if bool(meta.get("safe_fallback_used")):
            safe_fallback_count += 1

    for row in feedback:
        issues = {str(value or "").strip().lower() for value in (row.get("meta") or {}).get("issues") or []}
        for issue_key in issue_counts:
            if issue_key in issues:
                issue_counts[issue_key] += 1

    guard_fail_rate = _round_rate(guard_fail_count, total_generations)
    guard_warn_rate = _round_rate(guard_warn_count, total_generations)
    wrong_law_rate = _round_rate(issue_counts["wrong_law"], total_feedback)
    hallucination_rate = _round_rate(issue_counts["hallucination"], total_feedback)
    unclear_answer_rate = _round_rate(issue_counts["unclear_answer"], total_feedback)
    wrong_fact_rate = _round_rate(issue_counts["wrong_fact"], total_feedback)
    fallback_rate = _round_rate(fallback_count, total_generations)
    unsupported_article_rate = _round_rate(issue_counts["unsupported_article_reference"], total_generations)
    new_fact_validation_rate = _round_rate(issue_counts["new_fact_detected"], total_generations)
    format_violation_rate = _round_rate(issue_counts["format_violation"], total_generations)
    validation_retry_rate = _round_rate(validation_retry_count, total_generations)
    safe_fallback_rate = _round_rate(safe_fallback_count, total_generations)
    warning_new_fact_rate = _point3_monitoring_threshold("warning", "new_fact_rate", 0.01)
    critical_new_fact_rate = _point3_monitoring_threshold("critical", "new_fact_rate", 0.02)
    warning_unsupported_rate = _point3_monitoring_threshold("warning", "unsupported_article_rate", 0.01)
    critical_unsupported_rate = _point3_monitoring_threshold("critical", "unsupported_article_rate", 0.03)
    warning_format_rate = _point3_monitoring_threshold("warning", "format_violation_rate", 0.03)
    critical_format_rate = _point3_monitoring_threshold("critical", "format_violation_rate", 0.05)
    warning_retry_rate = _point3_monitoring_threshold("warning", "validation_retry_rate", 0.08)
    critical_retry_rate = _point3_monitoring_threshold("critical", "validation_retry_rate", 0.12)
    warning_fallback_rate = _point3_monitoring_threshold("warning", "safe_fallback_rate", 0.08)
    critical_fallback_rate = _point3_monitoring_threshold("critical", "safe_fallback_rate", 0.12)

    return {
        "sample_window_hours": 24,
        "generation_samples": total_generations,
        "feedback_samples": total_feedback,
        "guard_fail_rate": guard_fail_rate,
        "guard_warn_rate": guard_warn_rate,
        "wrong_law_rate": wrong_law_rate,
        "wrong_fact_rate": wrong_fact_rate,
        "hallucination_rate": hallucination_rate,
        "unclear_answer_rate": unclear_answer_rate,
        "fallback_rate": fallback_rate,
        "unsupported_article_rate": unsupported_article_rate,
        "new_fact_validation_rate": new_fact_validation_rate,
        "format_violation_rate": format_violation_rate,
        "validation_retry_rate": validation_retry_rate,
        "safe_fallback_rate": safe_fallback_rate,
        "issue_counts": issue_counts,
        "bands": {
            "guard_fail_rate": _band_from_thresholds(guard_fail_rate, green_max=1.5, yellow_max=3.0),
            "guard_warn_rate": _band_from_thresholds(guard_warn_rate, green_max=8.0, yellow_max=15.0),
            "wrong_law_rate": _band_from_thresholds(wrong_law_rate, green_max=2.0, yellow_max=4.0),
            "wrong_fact_rate": _band_from_thresholds(wrong_fact_rate, green_max=2.0, yellow_max=4.0),
            "hallucination_rate": _band_from_thresholds(hallucination_rate, green_max=0.8, yellow_max=1.5),
            "unclear_answer_rate": _band_from_thresholds(unclear_answer_rate, green_max=5.0, yellow_max=9.0),
            "unsupported_article_rate": _band_from_thresholds(
                unsupported_article_rate,
                green_max=warning_unsupported_rate,
                yellow_max=critical_unsupported_rate,
            ),
            "new_fact_validation_rate": _band_from_thresholds(
                new_fact_validation_rate,
                green_max=warning_new_fact_rate,
                yellow_max=critical_new_fact_rate,
            ),
            "format_violation_rate": _band_from_thresholds(
                format_violation_rate,
                green_max=warning_format_rate,
                yellow_max=critical_format_rate,
            ),
            "validation_retry_rate": _band_from_thresholds(
                validation_retry_rate,
                green_max=warning_retry_rate,
                yellow_max=critical_retry_rate,
            ),
            "safe_fallback_rate": _band_from_thresholds(
                safe_fallback_rate,
                green_max=warning_fallback_rate,
                yellow_max=critical_fallback_rate,
            ),
        },
    }


def _build_ai_pipeline_cost_tables(generations: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    by_flow: dict[str, dict[str, Any]] = {}
    for row in generations:
        meta = row.get("meta") or {}
        generation_id = str(meta.get("generation_id") or "").strip()
        model = str(meta.get("model") or "unknown").strip() or "unknown"
        flow = str(meta.get("flow") or "unknown").strip() or "unknown"
        cost_value = _safe_float(
            meta.get("estimated_cost_usd"),
            generation_id=generation_id,
            field="estimated_cost_usd",
        )
        token_value = _safe_int(meta.get("total_tokens"), default=0)

        model_item = by_model.setdefault(model, {"model": model, "requests": 0, "estimated_cost_total_usd": 0.0, "total_tokens": 0})
        model_item["requests"] += 1
        model_item["estimated_cost_total_usd"] += cost_value
        model_item["total_tokens"] += token_value

        flow_item = by_flow.setdefault(flow, {"flow": flow, "requests": 0, "estimated_cost_total_usd": 0.0, "total_tokens": 0})
        flow_item["requests"] += 1
        flow_item["estimated_cost_total_usd"] += cost_value
        flow_item["total_tokens"] += token_value

    def _finalize_rows(items: dict[str, dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in items.values():
            requests = max(1, int(item["requests"]))
            rows.append(
                {
                    key: item[key],
                    "requests": requests,
                    "estimated_cost_total_usd": round(float(item["estimated_cost_total_usd"]), 6),
                    "avg_cost_per_request_usd": round(float(item["estimated_cost_total_usd"]) / requests, 6),
                    "total_tokens": int(item["total_tokens"]),
                }
            )
        return sorted(rows, key=lambda value: (-float(value["estimated_cost_total_usd"]), -int(value["requests"]), str(value[key])))

    return {
        "by_model": _finalize_rows(by_model, key="model"),
        "by_flow": _finalize_rows(by_flow, key="flow"),
    }


def _build_top_inaccurate_generations(
    *,
    generations: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    by_generation_id = {
        str((row.get("meta") or {}).get("generation_id") or "").strip(): row
        for row in generations
        if str((row.get("meta") or {}).get("generation_id") or "").strip()
    }
    items: list[dict[str, Any]] = []
    for row in feedback:
        meta = row.get("meta") or {}
        generation_id = str(meta.get("generation_id") or "").strip()
        generation = by_generation_id.get(generation_id, {})
        generation_meta = generation.get("meta") or {}
        generation_cost = _safe_float(
            generation_meta.get("estimated_cost_usd"),
            generation_id=generation_id,
            field="estimated_cost_usd",
        )
        items.append(
            {
                "created_at": row.get("created_at"),
                "generation_id": generation_id,
                "flow": str(meta.get("flow") or generation_meta.get("flow") or "").strip(),
                "issues": list(meta.get("issues") or []),
                "note": str(meta.get("note") or "").strip(),
                "output_preview": str(generation_meta.get("output_preview") or "").strip(),
                "guard_status": str(generation_meta.get("guard_status") or "").strip(),
                "guard_warnings": list(generation_meta.get("guard_warnings") or []),
                "model": str(generation_meta.get("model") or "").strip(),
                "estimated_cost_usd": generation_cost,
            }
        )
    return items[: max(1, int(limit or 10))]


def _build_policy_action_log(
    *,
    quality_summary: dict[str, Any],
    flow_summaries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    guard_fail_rate = quality_summary.get("guard_fail_rate")
    wrong_law_rate = quality_summary.get("wrong_law_rate")
    hallucination_rate = quality_summary.get("hallucination_rate")
    unsupported_article_rate = quality_summary.get("unsupported_article_rate")
    new_fact_validation_rate = quality_summary.get("new_fact_validation_rate")
    format_violation_rate = quality_summary.get("format_violation_rate")
    validation_retry_rate = quality_summary.get("validation_retry_rate")
    safe_fallback_rate = quality_summary.get("safe_fallback_rate")
    law_qa_p95 = (flow_summaries.get("law_qa") or {}).get("latency_ms_p95")
    suggest_p95 = (flow_summaries.get("suggest") or {}).get("latency_ms_p95")

    if isinstance(guard_fail_rate, (int, float)) and guard_fail_rate > 3.0:
        actions.append(
            {
                "severity": "danger",
                "title": "Disable nano for 6h",
                "reason": f"guard_fail_rate={guard_fail_rate}%",
            }
        )
    if isinstance(wrong_law_rate, (int, float)) and wrong_law_rate > 4.0:
        actions.append(
            {
                "severity": "danger",
                "title": "Force full for law_qa for 24h",
                "reason": f"wrong_law_rate={wrong_law_rate}%",
            }
        )
    if isinstance(hallucination_rate, (int, float)) and hallucination_rate > 1.5:
        actions.append(
            {
                "severity": "danger",
                "title": "Enable strict mode for low-confidence",
                "reason": f"hallucination_rate={hallucination_rate}%",
            }
        )
    if isinstance(unsupported_article_rate, (int, float)) and unsupported_article_rate > _point3_monitoring_threshold("critical", "unsupported_article_rate", 0.03):
        actions.append(
            {
                "severity": "danger",
                "title": "Rollback to factual_only for article references",
                "reason": f"unsupported_article_rate={unsupported_article_rate}%",
            }
        )
    if isinstance(new_fact_validation_rate, (int, float)) and new_fact_validation_rate > _point3_monitoring_threshold("critical", "new_fact_rate", 0.02):
        actions.append(
            {
                "severity": "danger",
                "title": "Investigate invented-fact spike",
                "reason": f"new_fact_validation_rate={new_fact_validation_rate}%",
            }
        )
    if isinstance(format_violation_rate, (int, float)) and format_violation_rate > _point3_monitoring_threshold("critical", "format_violation_rate", 0.05):
        actions.append(
            {
                "severity": "warn",
                "title": "Tighten prompt format enforcement",
                "reason": f"format_violation_rate={format_violation_rate}%",
            }
        )
    if isinstance(validation_retry_rate, (int, float)) and validation_retry_rate > _point3_monitoring_threshold("critical", "validation_retry_rate", 0.12):
        actions.append(
            {
                "severity": "warn",
                "title": "Review point3 retry volume",
                "reason": f"validation_retry_rate={validation_retry_rate}%",
            }
        )
    if isinstance(safe_fallback_rate, (int, float)) and safe_fallback_rate > _point3_monitoring_threshold("critical", "safe_fallback_rate", 0.12):
        actions.append(
            {
                "severity": "warn",
                "title": "Review safe factual fallback spike",
                "reason": f"safe_fallback_rate={safe_fallback_rate}%",
            }
        )
    if isinstance(law_qa_p95, (int, float)) and law_qa_p95 > 10000:
        actions.append(
            {
                "severity": "warn",
                "title": "Review law_qa latency tiering",
                "reason": f"p95_latency_law_qa={law_qa_p95}ms",
            }
        )
    if isinstance(suggest_p95, (int, float)) and suggest_p95 > 13000:
        actions.append(
            {
                "severity": "warn",
                "title": "Review suggest latency tiering",
                "reason": f"p95_latency_suggest={suggest_p95}ms",
            }
        )

    if not actions:
        actions.append(
            {
                "severity": "success-soft",
                "title": "No active policy triggers",
                "reason": "Recent quality and latency sample stays within configured bands.",
            }
        )
    return actions


def _save_admin_tasks_to_disk() -> None:
    try:
        _ADMIN_TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ADMIN_TASKS_PATH.write_text(
            json.dumps(_ADMIN_TASKS, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _load_admin_tasks_from_disk() -> None:
    try:
        raw = _ADMIN_TASKS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except Exception:
        return
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return
    if isinstance(parsed, dict):
        _ADMIN_TASKS.clear()
        for key, value in parsed.items():
            if isinstance(value, dict):
                _ADMIN_TASKS[str(key)] = value


def _put_admin_task(task: dict[str, Any]) -> None:
    with _ADMIN_TASKS_LOCK:
        _ADMIN_TASKS[str(task["task_id"])] = deepcopy(task)
        _save_admin_tasks_to_disk()


def _patch_admin_task(task_id: str, **changes: Any) -> None:
    with _ADMIN_TASKS_LOCK:
        current = _ADMIN_TASKS.get(task_id)
        if not current:
            return
        current.update(changes)
        _ADMIN_TASKS[task_id] = current
        _save_admin_tasks_to_disk()


def _load_admin_task(task_id: str) -> dict[str, Any] | None:
    with _ADMIN_TASKS_LOCK:
        if task_id not in _ADMIN_TASKS:
            _load_admin_tasks_from_disk()
        item = _ADMIN_TASKS.get(task_id)
        return deepcopy(item) if item else None


def _load_admin_tasks() -> list[dict[str, Any]]:
    with _ADMIN_TASKS_LOCK:
        _load_admin_tasks_from_disk()
        return [deepcopy(item) for item in _ADMIN_TASKS.values() if isinstance(item, dict)]


def _find_active_law_rebuild_task(*, server_code: str) -> dict[str, Any] | None:
    with _ADMIN_TASKS_LOCK:
        _load_admin_tasks_from_disk()
        return find_active_law_rebuild_task(tasks=_ADMIN_TASKS, server_code=server_code)


def _claim_law_rebuild_task(*, server_code: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    with _ADMIN_TASKS_LOCK:
        _load_admin_tasks_from_disk()
        active_task = find_active_law_rebuild_task(tasks=_ADMIN_TASKS, server_code=server_code)
        if active_task:
            return active_task, None
        task = {
            "task_id": f"law-rebuild-{uuid.uuid4().hex}",
            "scope": "law_sources_rebuild",
            "server_code": server_code,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": "",
            "finished_at": "",
            "progress": {"done": 0, "total": 1},
            "result": None,
            "error": "",
        }
        _ADMIN_TASKS[str(task["task_id"])] = deepcopy(task)
        _save_admin_tasks_to_disk()
        return None, deepcopy(task)


def _get_content_workflow_service_for_request(request: Request) -> ContentWorkflowService:
    override = getattr(request.app, "dependency_overrides", {}).get(get_content_workflow_service)
    if override is None:
        return get_content_workflow_service(request)
    try:
        return override()
    except TypeError:
        return override(request)


_load_admin_tasks_from_disk()


def _apply_bulk_action(
    *,
    payload: AdminBulkActionPayload,
    user: AuthUser,
    metrics_store: AdminMetricsStore,
    user_store: UserStore,
    task_id: str | None = None,
) -> dict[str, Any]:
    action = str(payload.action or "").strip().lower()
    if action == "set_daily_quota" and payload.daily_limit is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Для set_daily_quota обязательно поле daily_limit."])
    usernames = [str(item or "").strip().lower() for item in payload.usernames if str(item or "").strip()]
    if not usernames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Не переданы пользователи для массовой операции."])

    results: list[dict[str, Any]] = []
    success_count = 0
    for index, username in enumerate(usernames, start=1):
        try:
            if action == "verify_email":
                user_store.admin_mark_email_verified(username)
                event_type = "admin_verify_email"
                meta: dict[str, Any] = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/verify-email"
            elif action == "block":
                user_store.admin_set_access_blocked(username, payload.reason)
                event_type = "admin_block_user"
                meta = {"target_username": username, "reason": payload.reason, "bulk": True}
                path = f"/api/admin/users/{username}/block"
            elif action == "unblock":
                user_store.admin_clear_access_blocked(username)
                event_type = "admin_unblock_user"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/unblock"
            elif action == "grant_tester":
                user_store.admin_set_tester_status(username, True)
                event_type = "admin_grant_tester"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/grant-tester"
            elif action == "revoke_tester":
                user_store.admin_set_tester_status(username, False)
                event_type = "admin_revoke_tester"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/revoke-tester"
            elif action == "grant_gka":
                user_store.admin_set_gka_status(username, True)
                event_type = "admin_grant_gka"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/grant-gka"
            elif action == "revoke_gka":
                user_store.admin_set_gka_status(username, False)
                event_type = "admin_revoke_gka"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/revoke-gka"
            elif action == "deactivate":
                user_store.admin_deactivate_user(username, payload.reason)
                event_type = "admin_deactivate_user"
                meta = {"target_username": username, "reason": payload.reason, "bulk": True}
                path = f"/api/admin/users/{username}/deactivate"
            elif action == "reactivate":
                user_store.admin_reactivate_user(username)
                event_type = "admin_reactivate_user"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/reactivate"
            elif action == "set_daily_quota":
                safe_limit = int(payload.daily_limit or 0)
                user_store.admin_set_daily_quota(username, safe_limit)
                event_type = "admin_set_daily_quota"
                meta = {"target_username": username, "daily_limit": safe_limit, "bulk": True}
                path = f"/api/admin/users/{username}/daily-quota"
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[f"Неизвестное bulk-действие: {action}."])
            metrics_store.log_event(
                event_type=event_type,
                username=user.username,
                server_code=user.server_code,
                path=path,
                method="POST",
                status_code=200,
                meta=meta,
            )
            success_count += 1
            results.append({"username": username, "ok": True})
        except Exception as exc:  # noqa: BLE001
            results.append({"username": username, "ok": False, "error": str(exc)})
        if task_id:
            _patch_admin_task(task_id, progress={"done": index, "total": len(usernames)})

    return {
        "action": action,
        "total": len(usernames),
        "success_count": success_count,
        "failed_count": len(usernames) - success_count,
        "results": results,
    }


def _admin_template_payload(request: Request, user: AuthUser, *, admin_focus: str) -> dict[str, Any]:
    user_store = request.app.state.user_store
    server_config, permissions = resolve_user_server_context(user_store, user.username)
    shell_context = extract_server_shell_context(server_config, permissions)
    return page_context(
        username=user.username,
        nav_active="admin",
        is_admin=permissions.is_admin,
        show_test_pages=permissions.can_access_exam_import,
        show_tester_pages=permissions.can_access_court_claims,
        **shell_context,
        admin_focus=admin_focus,
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user: AuthUser = Depends(requires_permission("manage_servers"))):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="dashboard"),
    )


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request, user: AuthUser = Depends(requires_permission("view_analytics"))):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="dashboard"),
    )


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, user: AuthUser = Depends(requires_permission("manage_servers"))):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="users"),
    )


@router.get("/admin/servers", response_class=HTMLResponse)
async def admin_servers_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="servers"),
    )


@router.get("/admin/laws", response_class=HTMLResponse)
async def admin_laws_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="laws"),
    )


@router.get("/admin/templates", response_class=HTMLResponse)
async def admin_templates_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="templates"),
    )


@router.get("/admin/features", response_class=HTMLResponse)
async def admin_features_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="features"),
    )


@router.get("/admin/rules", response_class=HTMLResponse)
async def admin_rules_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="rules"),
    )




@router.get("/api/admin/runtime-servers")
async def admin_runtime_servers_list(
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
):
    _ = user
    return list_runtime_servers_payload(store=store)


@router.post("/api/admin/runtime-servers")
async def admin_runtime_servers_create(
    payload: AdminRuntimeServerPayload,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = create_runtime_server_payload(store=store, code=payload.code, title=payload.title)
    except ValueError as exc:
        _raise_bad_request(exc)
    row = result["item"]
    metrics_store.log_event(
        event_type="admin_runtime_server_create",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/runtime-servers",
        method="POST",
        status_code=200,
        meta={"code": row["code"]},
    )
    return _admin_ok(**result)


@router.put("/api/admin/runtime-servers/{server_code}")
async def admin_runtime_servers_update(
    server_code: str,
    payload: AdminRuntimeServerPayload,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    normalized_code = _normalize_code(server_code)
    if normalized_code != payload.code:
        _raise_bad_request("server_code_mismatch")
    try:
        result = update_runtime_server_payload(store=store, code=normalized_code, title=payload.title)
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    row = result["item"]
    metrics_store.log_event(
        event_type="admin_runtime_server_update",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/runtime-servers/{normalized_code}",
        method="PUT",
        status_code=200,
        meta={"code": row["code"]},
    )
    return _admin_ok(**result)


@router.post("/api/admin/runtime-servers/{server_code}/activate")
async def admin_runtime_servers_activate(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    normalized_code = _normalize_code(server_code)
    try:
        result = set_runtime_server_active_payload(store=store, code=normalized_code, is_active=True)
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    row = result["item"]
    metrics_store.log_event(
        event_type="admin_runtime_server_activate",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/activate",
        method="POST",
        status_code=200,
        meta={"code": row["code"]},
    )
    return _admin_ok(**result)


@router.get("/api/admin/runtime-servers/{server_code}/health")
async def admin_runtime_server_health(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    law_sets_store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    normalized_code = _normalize_code(server_code)
    payload = build_runtime_server_health_payload(
        server_code=normalized_code,
        runtime_servers_store=store,
        law_sets_store=law_sets_store,
    )
    if not payload["checks"]["server"]["ok"]:
        _raise_not_found("server_not_found")
    metrics_store.log_event(
        event_type="admin_runtime_server_health",
        username=user.username,
        server_code=normalized_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/health",
        method="GET",
        status_code=200,
        meta=payload.get("summary") or {},
    )
    return payload


@router.post("/api/admin/runtime-servers/{server_code}/deactivate")
async def admin_runtime_servers_deactivate(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_runtime_servers")),
    store: RuntimeServersStore = Depends(get_runtime_servers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    normalized_code = _normalize_code(server_code)
    try:
        result = set_runtime_server_active_payload(store=store, code=normalized_code, is_active=False)
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    row = result["item"]
    metrics_store.log_event(
        event_type="admin_runtime_server_deactivate",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/deactivate",
        method="POST",
        status_code=200,
        meta={"code": row["code"]},
    )
    return _admin_ok(**result)


@router.get("/api/admin/runtime-servers/{server_code}/law-sets")
async def admin_runtime_server_law_sets(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
):
    _ = user
    return list_runtime_server_law_sets_payload(store=store, server_code=server_code)


@router.get("/api/admin/runtime-servers/{server_code}/law-bindings")
async def admin_runtime_server_law_bindings(
    server_code: str,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
):
    _ = user
    return list_runtime_server_law_bindings_payload(store=store, server_code=server_code)


@router.post("/api/admin/runtime-servers/{server_code}/law-bindings")
async def admin_runtime_server_law_bindings_add(
    server_code: str,
    payload: AdminServerLawBindingPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = add_runtime_server_law_binding_payload(
            store=store,
            server_code=server_code,
            law_code=payload.law_code,
            source_id=payload.source_id,
            effective_from=payload.effective_from,
            priority=payload.priority,
            law_set_id=payload.law_set_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    normalized_code = result["server_code"]
    item = result["item"]
    metrics_store.log_event(
        event_type="admin_server_law_binding_add",
        username=user.username,
        server_code=normalized_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/law-bindings",
        method="POST",
        status_code=200,
        meta={"law_set_id": item.get("law_set_id"), "law_code": item.get("law_code")},
    )
    return _admin_ok(item=item)


@router.post("/api/admin/runtime-servers/{server_code}/law-sets")
async def admin_runtime_server_law_sets_create(
    server_code: str,
    payload: AdminLawSetPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = create_runtime_server_law_set_payload(
            store=store,
            server_code=server_code,
            name=payload.name,
            items=[item.model_dump() for item in payload.items],
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    normalized_code = result["server_code"]
    law_set = result["law_set"]
    items = result["items"]
    metrics_store.log_event(
        event_type="admin_law_set_create",
        username=user.username,
        server_code=normalized_code,
        path=f"/api/admin/runtime-servers/{normalized_code}/law-sets",
        method="POST",
        status_code=200,
        meta={"law_set_id": law_set.get("id"), "items_count": len(items)},
    )
    return _admin_ok(law_set=law_set, items=items)


@router.put("/api/admin/law-sets/{law_set_id}")
async def admin_law_set_update(
    law_set_id: int,
    payload: AdminLawSetPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = update_law_set_payload(
            store=store,
            law_set_id=law_set_id,
            name=payload.name,
            is_active=payload.is_active,
            items=[item.model_dump() for item in payload.items],
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    law_set = result["law_set"]
    items = result["items"]
    metrics_store.log_event(
        event_type="admin_law_set_update",
        username=user.username,
        server_code=str(law_set.get("server_code") or user.server_code),
        path=f"/api/admin/law-sets/{law_set_id}",
        method="PUT",
        status_code=200,
        meta={"law_set_id": law_set_id, "items_count": len(items)},
    )
    return _admin_ok(law_set=law_set, items=items)


@router.post("/api/admin/law-sets/{law_set_id}/publish")
async def admin_law_set_publish(
    law_set_id: int,
    user: AuthUser = Depends(requires_permission("publish_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = publish_law_set_payload(store=store, law_set_id=law_set_id)
    except KeyError as exc:
        _raise_not_found(exc)
    law_set = result["law_set"]
    metrics_store.log_event(
        event_type="admin_law_set_publish",
        username=user.username,
        server_code=str(law_set.get("server_code") or user.server_code),
        path=f"/api/admin/law-sets/{law_set_id}/publish",
        method="POST",
        status_code=200,
        meta={"law_set_id": law_set_id},
    )
    return _admin_ok(law_set=law_set)


@router.post("/api/admin/law-sets/{law_set_id}/rebuild")
async def admin_law_set_rebuild(
    law_set_id: int,
    payload: AdminLawSetRebuildPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        context = resolve_law_set_rebuild_context(store=store, law_set_id=law_set_id)
    except KeyError as exc:
        _raise_not_found(exc)
    except ValueError as exc:
        _raise_bad_request(exc)
    service = LawAdminService(workflow_service)
    result = service.rebuild_index(
        server_code=context["server_code"],
        source_urls=context["source_urls"],
        actor_user_id=actor_user_id,
        request_id=getattr(request.state, "request_id", ""),
        persist_sources=True,
        dry_run=bool(payload.dry_run),
    )
    metrics_store.log_event(
        event_type="admin_law_set_rebuild",
        username=user.username,
        server_code=context["server_code"],
        path=f"/api/admin/law-sets/{law_set_id}/rebuild",
        method="POST",
        status_code=200,
        meta={"law_set_id": law_set_id, "law_version_id": result.get("law_version_id")},
    )
    return _admin_ok(
        law_set_id=law_set_id,
        server_code=context["server_code"],
        source_urls=context["source_urls"],
        result=result,
    )


@router.post("/api/admin/law-sets/{law_set_id}/rollback")
async def admin_law_set_rollback(
    law_set_id: int,
    payload: AdminLawSetRollbackPayload,
    user: AuthUser = Depends(requires_permission("publish_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        context = resolve_law_set_rollback_context(store=store, law_set_id=law_set_id)
    except KeyError as exc:
        _raise_not_found(exc)
    service = LawAdminService(workflow_service)
    try:
        result = service.rollback_active_version(
            server_code=context["server_code"],
            law_version_id=payload.law_version_id,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_law_set_rollback",
        username=user.username,
        server_code=context["server_code"],
        path=f"/api/admin/law-sets/{law_set_id}/rollback",
        method="POST",
        status_code=200,
        meta={"law_set_id": law_set_id, "law_version_id": payload.law_version_id},
    )
    return _admin_ok(law_set_id=law_set_id, result=result)


@router.get("/api/admin/law-source-registry")
async def admin_law_source_registry_list(
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
):
    _ = user
    return list_law_source_registry_payload(store=store)


@router.post("/api/admin/law-source-registry")
async def admin_law_source_registry_create(
    payload: AdminLawSourceRegistryPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = create_law_source_registry_payload(store=store, name=payload.name, kind=payload.kind, url=payload.url)
    except ValueError as exc:
        _raise_bad_request(exc)
    metrics_store.log_event(
        event_type="admin_law_source_registry_create",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/law-source-registry",
        method="POST",
        status_code=200,
        meta={"source_id": result["item"]["id"]},
    )
    return _admin_ok(**result)


@router.get("/api/admin/law-jobs/overview")
async def admin_law_jobs_overview(
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
):
    _ = user
    return build_law_jobs_overview_payload(tasks=_load_admin_tasks())


@router.get("/api/admin/async-jobs/overview")
async def admin_async_jobs_overview(
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    user_store: UserStore = Depends(get_user_store),
):
    _ = user
    service = _get_async_job_service(request, user_store)
    items = [
        enrich_job_status(item, subsystem="async_job")
        for item in service.list_jobs(server_id=user.server_code, limit=100)
    ]
    return build_async_jobs_overview_payload(items=items)


@router.get("/api/admin/exam-import/overview")
async def admin_exam_import_overview(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    exam_store: ExamAnswersStore = Depends(get_exam_answers_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    payload = build_exam_import_overview_payload(exam_store=exam_store, metrics_store=metrics_store)
    return {
        "ok": True,
        "summary": payload["summary"],
        "last_sync": payload.get("last_sync"),
        "last_score": payload.get("last_score"),
        "recent_failures": list(payload.get("recent_failures") or [])[:5],
        "recent_row_failures": list(payload.get("recent_row_failures") or [])[:5],
        "failed_entries": list(payload.get("failed_entries") or [])[:5],
    }


@router.get("/api/admin/generated-documents/{document_id}/provenance", response_model=DocumentVersionProvenanceResponse)
async def admin_generated_document_provenance(
    document_id: int,
    _: AuthUser = Depends(requires_permission("view_analytics")),
    store: UserStore = Depends(get_user_store),
) -> DocumentVersionProvenanceResponse:
    bundle = require_admin_generated_document_trace_bundle(store=store, document_id=document_id)
    payload = resolve_generated_document_provenance_payload_from_bundle(store=store, bundle=bundle)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Provenance trace not found."])
    return DocumentVersionProvenanceResponse(**payload)


@router.get("/api/admin/generated-documents/recent")
async def admin_recent_generated_documents(
    limit: int = Query(default=8, ge=1, le=20),
    _: AuthUser = Depends(requires_permission("view_analytics")),
    store: UserStore = Depends(get_user_store),
):
    return {
        "items": list_admin_recent_generated_documents(store=store, limit=limit),
    }


@router.get("/api/admin/generated-documents/{document_id}/review-context")
async def admin_generated_document_review_context(
    document_id: int,
    _: AuthUser = Depends(requires_permission("view_analytics")),
    store: UserStore = Depends(get_user_store),
):
    bundle = require_admin_generated_document_trace_bundle(store=store, document_id=document_id)
    return resolve_generated_document_review_context_payload_from_bundle(store=store, bundle=bundle)


@router.put("/api/admin/law-source-registry/{source_id}")
async def admin_law_source_registry_update(
    source_id: int,
    payload: AdminLawSourceRegistryPayload,
    user: AuthUser = Depends(requires_permission("manage_law_sets")),
    store: RuntimeLawSetsStore = Depends(get_runtime_law_sets_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    try:
        result = update_law_source_registry_payload(
            store=store,
            source_id=source_id,
            name=payload.name,
            kind=payload.kind,
            url=payload.url,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        _raise_bad_request(exc)
    except KeyError as exc:
        _raise_not_found(exc)
    metrics_store.log_event(
        event_type="admin_law_source_registry_update",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/law-source-registry/{source_id}",
        method="PUT",
        status_code=200,
        meta={"source_id": result["item"]["id"]},
    )
    return _admin_ok(**result)


def _resolve_actor_user_id(user_store: UserStore, username: str) -> int:
    actor_user_id = user_store.get_user_id(username)
    if actor_user_id is None:
        _raise_bad_request("actor_not_found")
    return int(actor_user_id)


def _resolve_law_sources_server_code(
    user: AuthUser,
    user_store: UserStore,
    requested_server_code: str = "",
) -> str:
    normalized = str(requested_server_code or "").strip().lower()
    target_server_code = normalized or user.server_code
    if target_server_code == user.server_code:
        return target_server_code

    current_permissions = resolve_user_server_permissions(user_store, user.username, server_code=user.server_code)
    if not current_permissions.has("manage_servers"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=["Недостаточно прав для управления источниками законов другого сервера."],
        )

    target_permissions = resolve_user_server_permissions(user_store, user.username, server_code=target_server_code)
    if not target_permissions.has("manage_laws"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=[f"Недостаточно прав manage_laws для сервера '{target_server_code}'."],
        )

    return target_server_code


def _resolve_active_change_request_id(item: dict[str, Any], change_requests: list[dict[str, Any]]) -> int | None:
    item_status = str(item.get("status") or "").strip().lower()
    if not change_requests:
        return None
    if item_status in {"draft", "in_review", "approved"}:
        for change_request in change_requests:
            if str(change_request.get("status") or "").strip().lower() == item_status:
                try:
                    return int(change_request.get("id"))
                except (TypeError, ValueError):
                    continue
    try:
        return int(change_requests[0].get("id"))
    except (TypeError, ValueError, IndexError):
        return None

def _resolve_active_change_request(item: dict[str, Any], change_requests: list[dict[str, Any]]) -> dict[str, Any] | None:
    active_change_request_id = _resolve_active_change_request_id(item, change_requests)
    if active_change_request_id is None:
        return None
    for change_request in change_requests:
        try:
            if int(change_request.get("id")) == active_change_request_id:
                return change_request
        except (TypeError, ValueError):
            continue
    return None


def _build_catalog_payload_config(payload: AdminCatalogItemPayload) -> dict[str, Any]:
    typed_fields: dict[str, Any] = {
        "key": payload.key,
        "description": payload.description,
        "status": payload.status,
        "server_code": payload.server_code,
        "base_url": payload.base_url,
        "timeout_sec": payload.timeout_sec,
        "law_code": payload.law_code,
        "source": payload.source,
        "effective_from": payload.effective_from,
        "template_type": payload.template_type,
        "document_kind": payload.document_kind,
        "output_format": payload.output_format,
        "feature_flag": payload.feature_flag,
        "rollout_percent": payload.rollout_percent,
        "audience": payload.audience,
        "rule_type": payload.rule_type,
        "priority": payload.priority,
        "applies_to": payload.applies_to,
    }
    cleaned_typed = {
        key: value
        for key, value in typed_fields.items()
        if value not in (None, "", [], {})
    }
    merged = {
        key: value
        for key, value in (payload.config or {}).items()
        if value is not None
    }
    merged.update(cleaned_typed)
    if "key" not in merged:
        merged["key"] = str(payload.title or "").strip().lower().replace(" ", "_")
    if "status" not in merged:
        merged["status"] = payload.status or "draft"
    if not str(merged.get("key") or "").strip():
        raise ValueError("key_required")
    return merged


@router.get("/api/admin/platform-blueprint/status")
async def admin_platform_blueprint_status(user: AuthUser = Depends(require_admin_user)):
    stage = _resolve_admin_platform_stage()
    return {
        "ok": True,
        "stage": stage,
        "server_code": user.server_code,
    }


@router.get("/api/admin/catalog/audit")
async def admin_catalog_audit(
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    limit: int = Query(100, ge=1, le=500),
    entity_type: str = Query(""),
    entity_id: str = Query(""),
):
    normalized_entity_type = str(entity_type or "").strip().lower()
    normalized_entity_id = str(entity_id or "").strip()
    try:
        audit = workflow_service.list_audit_trail(
            server_scope="server",
            server_id=user.server_code,
            entity_type=normalized_entity_type,
            entity_id=normalized_entity_id,
            limit=limit,
        )
    except ValueError as exc:
        _raise_admin_http_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="admin_catalog_audit_bad_request",
            message=str(exc) or "invalid_audit_filter",
        )
    except (KeyError, PermissionError) as exc:
        _raise_admin_http_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="admin_catalog_audit_not_found",
            message=str(exc) or "audit_scope_not_found",
        )
    return {
        "items": audit,
        "filters": {
            "entity_type": normalized_entity_type,
            "entity_id": normalized_entity_id,
            "limit": limit,
        },
    }


@router.get("/api/admin/catalog/{entity_type}")
async def admin_catalog_list(
    entity_type: str,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    try:
        normalized_entity_type = _normalize_admin_catalog_entity_type(entity_type)
        result = workflow_service.list_content_items(
            server_scope="server",
            server_id=user.server_code,
            content_type=normalized_entity_type,
            include_legacy_fallback=False,
        )
        audit = workflow_service.list_audit_trail(
            server_scope="server",
            server_id=user.server_code,
            entity_type="",
            entity_id="",
            limit=100,
        )
        enriched_items: list[dict[str, Any]] = []
        for item in result["items"]:
            item_copy = dict(item)
            change_requests = workflow_service.list_change_requests(
                content_item_id=int(item_copy.get("id")),
                server_scope="server",
                server_id=user.server_code,
            )
            active_change_request = _resolve_active_change_request(item_copy, change_requests)
            item_copy["active_change_request_id"] = (
                int(active_change_request.get("id")) if active_change_request and active_change_request.get("id") is not None else None
            )
            item_copy["active_change_request_status"] = (
                str(active_change_request.get("status") or "").strip().lower() if active_change_request else ""
            )
            enriched_items.append(item_copy)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    return {"entity_type": entity_type, "items": enriched_items, "legacy_fallback": result["legacy_fallback"], "audit": audit}


@router.get("/api/admin/catalog/{entity_type}/{item_id}")
async def admin_catalog_get_item(
    entity_type: str,
    item_id: str,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    _ = entity_type
    try:
        item = workflow_service.get_content_item(
            content_item_id=int(item_id),
            server_scope="server",
            server_id=user.server_code,
        )
        versions = workflow_service.list_versions(
            content_item_id=int(item_id),
            server_scope="server",
            server_id=user.server_code,
        )
        change_requests = workflow_service.list_change_requests(
            content_item_id=int(item_id),
            server_scope="server",
            server_id=user.server_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except (KeyError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    versions_by_id = {
        int(version.get("id")): version
        for version in versions
        if isinstance(version, dict) and version.get("id") is not None
    }
    latest_change_request = change_requests[0] if change_requests else None
    effective_version = None
    effective_payload: dict[str, Any] = {}

    published_version_id = item.get("current_published_version_id")
    if published_version_id is not None:
        effective_version = versions_by_id.get(int(published_version_id))

    if not effective_version and latest_change_request:
        candidate_version_id = latest_change_request.get("candidate_version_id")
        if candidate_version_id is not None:
            effective_version = versions_by_id.get(int(candidate_version_id))

    if not effective_version and versions:
        effective_version = versions[-1]

    if effective_version:
        payload_candidate = effective_version.get("payload_json")
        if isinstance(payload_candidate, dict):
            effective_payload = payload_candidate

    return {
        "item": item,
        "versions": versions,
        "change_requests": change_requests,
        "effective_version": effective_version,
        "effective_payload": effective_payload,
        "latest_change_request": latest_change_request,
    }


@router.get("/api/admin/catalog/{entity_type}/{item_id}/versions")
async def admin_catalog_versions(
    entity_type: str,
    item_id: str,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    _ = entity_type
    try:
        versions = workflow_service.list_versions(
            content_item_id=int(item_id),
            server_scope="server",
            server_id=user.server_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except (KeyError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    return {"versions": versions}


@router.post("/api/admin/change-requests/{change_request_id}/review")
async def admin_catalog_review_action(
    change_request_id: int,
    request: Request,
    decision: str = Query("approve"),
    comment: str = Query(""),
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        result = workflow_service.review_change_request(
            change_request_id=change_request_id,
            reviewer_user_id=actor_user_id,
            decision=decision,
            comment=comment,
            diff_json={"review_via": "admin_api"},
            request_id=getattr(request.state, "request_id", ""),
            server_scope="server",
            server_id=user.server_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except (KeyError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    return {"ok": True, "result": result}


@router.get("/api/admin/change-requests/{change_request_id}/validate")
async def admin_catalog_validate_change_request(
    change_request_id: int,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
):
    try:
        result = workflow_service.validate_change_request(
            change_request_id=change_request_id,
            server_scope="server",
            server_id=user.server_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except (KeyError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    return {"ok": True, "result": result}




@router.post("/api/admin/catalog/{entity_type}")
async def admin_catalog_create(
    entity_type: str,
    payload: AdminCatalogItemPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        normalized_entity_type = _normalize_admin_catalog_entity_type(entity_type)
        final_config = _build_catalog_payload_config(payload)
        item = workflow_service.create_content_item(
            server_scope="server",
            server_id=user.server_code,
            content_type=normalized_entity_type,
            content_key=str(final_config.get("key") or payload.title or "").strip().lower().replace(" ", "_"),
            title=payload.title,
            metadata_json={"config": final_config},
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(event_type=f"admin_catalog_{entity_type}_create", username=user.username, server_code=user.server_code, path=f"/api/admin/catalog/{entity_type}", method="POST", status_code=200, meta={"entity_id": item.get("id"), "author": user.username})
    return {"ok": True, "item": item}


@router.put("/api/admin/catalog/{entity_type}/{item_id}")
async def admin_catalog_update(
    entity_type: str,
    item_id: str,
    payload: AdminCatalogItemPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    try:
        final_config = _build_catalog_payload_config(payload)
        result = workflow_service.create_draft_version(
            content_item_id=int(item_id),
            payload_json=final_config,
            schema_version=1,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            server_scope="server",
            server_id=user.server_code,
            comment=f"update:{payload.title}",
        )
        item = result["content_item"]
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    metrics_store.log_event(event_type=f"admin_catalog_{entity_type}_update", username=user.username, server_code=user.server_code, path=f"/api/admin/catalog/{entity_type}/{item_id}", method="PUT", status_code=200, meta={"entity_id": item_id, "author": user.username})
    return {"ok": True, "item": item, "change_request": result["change_request"], "version": result["version"]}


@router.delete("/api/admin/catalog/{entity_type}/{item_id}")
async def admin_catalog_delete(
    entity_type: str,
    item_id: str,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = entity_type
    _ = item_id
    metrics_store.log_event(event_type=f"admin_catalog_{entity_type}_delete_blocked", username=user.username, server_code=user.server_code, path=f"/api/admin/catalog/{entity_type}/{item_id}", method="DELETE", status_code=405, meta={"entity_id": item_id, "author": user.username})
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail=["delete_not_supported_in_versioned_workflow"])


@router.post("/api/admin/catalog/{entity_type}/{item_id}/workflow")
async def admin_catalog_workflow(
    entity_type: str,
    item_id: str,
    payload: AdminCatalogWorkflowPayload,
    request: Request,
    cr_id: int = Query(0),
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    _ = entity_type
    try:
        action = str(payload.action or "").strip().lower()
        change_request_id = int(payload.change_request_id or cr_id or 0)
        if change_request_id <= 0:
            raise ValueError("change_request_id_required")
        if action == "submit_for_review":
            response = workflow_service.submit_change_request(change_request_id=change_request_id, actor_user_id=actor_user_id, request_id=getattr(request.state, "request_id", ""), server_scope="server", server_id=user.server_code)
        elif action == "approve":
            response = workflow_service.review_change_request(change_request_id=change_request_id, reviewer_user_id=actor_user_id, decision="approve", comment="approved_via_admin_route", diff_json={"source": "admin_route"}, request_id=getattr(request.state, "request_id", ""), server_scope="server", server_id=user.server_code)
        elif action == "request_changes":
            response = workflow_service.review_change_request(change_request_id=change_request_id, reviewer_user_id=actor_user_id, decision="request_changes", comment="requested_changes_via_admin_route", diff_json={"source": "admin_route"}, request_id=getattr(request.state, "request_id", ""), server_scope="server", server_id=user.server_code)
        elif action == "publish":
            response = workflow_service.publish_change_request(change_request_id=change_request_id, actor_user_id=actor_user_id, request_id=getattr(request.state, "request_id", ""), summary_json={"source": "admin_route"}, server_scope="server", server_id=user.server_code)
        else:
            raise ValueError("unsupported_workflow_action")
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    metrics_store.log_event(event_type=f"admin_catalog_{entity_type}_workflow", username=user.username, server_code=user.server_code, path=f"/api/admin/catalog/{entity_type}/{item_id}/workflow", method="POST", status_code=200, meta={"entity_id": item_id, "author": user.username, "action": payload.action, "change_request_id": payload.change_request_id or cr_id})
    return {"ok": True, "result": response}


@router.post("/api/admin/catalog/{entity_type}/{item_id}/rollback")
async def admin_catalog_rollback(
    entity_type: str,
    item_id: str,
    payload: AdminCatalogRollbackPayload,
    request: Request,
    user: AuthUser = Depends(require_admin_user),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    _ = entity_type
    _ = item_id
    try:
        result = workflow_service.rollback_publish_batch(
            publish_batch_id=int(payload.version),
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            reason="manual_admin_rollback",
            server_scope="server",
            server_id=user.server_code,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=[str(exc)]) from exc
    metrics_store.log_event(event_type=f"admin_catalog_{entity_type}_rollback", username=user.username, server_code=user.server_code, path=f"/api/admin/catalog/{entity_type}/{item_id}/rollback", method="POST", status_code=200, meta={"entity_id": item_id, "author": user.username, "rollback_batch": payload.version})
    return {"ok": True, "result": result}


@router.get("/api/admin/law-sources")
async def admin_law_sources_status(
    server_code: str = Query(default="", description="Runtime server code override"),
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, server_code)
    service = LawAdminService(workflow_service)
    snapshot = service.get_effective_sources(server_code=target_server_code)
    metrics_store.log_event(
        event_type="admin_law_sources_status",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources",
        method="GET",
        status_code=200,
    )
    return {
        "server_code": target_server_code,
        "source_urls": list(snapshot.source_urls),
        "source_origin": snapshot.source_origin,
        "manifest_item": snapshot.manifest_item,
        "manifest_version": snapshot.manifest_version,
        "active_law_version": snapshot.active_law_version,
        "bundle_meta": snapshot.bundle_meta,
    }


@router.post("/api/admin/law-sources/sync")
async def admin_law_sources_sync(
    request: Request,
    server_code: str = Query(default="", description="Runtime server code override"),
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, server_code)
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    service = LawAdminService(workflow_service)
    try:
        result = service.sync_sources_manifest_from_server_config(
            server_code=target_server_code,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            safe_rerun=True,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_law_sources_sync",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/sync",
        method="POST",
        status_code=200,
        meta={"changed": bool(result.get("changed"))},
    )
    return result


@router.post("/api/admin/law-sources/rebuild")
async def admin_law_sources_rebuild(
    payload: AdminLawSourcesPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, payload.server_code)
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    service = LawAdminService(workflow_service)
    try:
        result = service.rebuild_index(
            server_code=target_server_code,
            source_urls=payload.source_urls,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            persist_sources=bool(payload.persist_sources),
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_law_sources_rebuild",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/rebuild",
        method="POST",
        status_code=200,
        meta={"law_version_id": result.get("law_version_id"), "article_count": result.get("article_count")},
    )
    return result


@router.post("/api/admin/law-sources/rebuild-async")
async def admin_law_sources_rebuild_async(
    payload: AdminLawSourcesPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, payload.server_code)
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    request_id = getattr(request.state, "request_id", "")
    active_task, queued_task = _claim_law_rebuild_task(server_code=target_server_code)
    if active_task:
        metrics_store.log_event(
            event_type="admin_law_sources_rebuild_async_conflict",
            username=user.username,
            server_code=target_server_code,
            path="/api/admin/law-sources/rebuild-async",
            method="POST",
            status_code=409,
            meta={"active_task_id": active_task.get("task_id"), "active_status": active_task.get("status")},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=[f"law_rebuild_already_in_progress:{active_task.get('task_id')}"],
        )
    assert queued_task is not None
    task_id = str(queued_task["task_id"])

    def _runner() -> None:
        _patch_admin_task(task_id, status="running", started_at=datetime.now(timezone.utc).isoformat())
        try:
            workflow_service = _get_content_workflow_service_for_request(request)
            service = LawAdminService(workflow_service)
            result = service.rebuild_index(
                server_code=target_server_code,
                source_urls=payload.source_urls,
                actor_user_id=actor_user_id,
                request_id=request_id,
                persist_sources=bool(payload.persist_sources),
            )
            _patch_admin_task(
                task_id,
                status="finished",
                finished_at=datetime.now(timezone.utc).isoformat(),
                progress={"done": 1, "total": 1},
                result=result,
            )
            metrics_store.log_event(
                event_type="admin_law_sources_rebuild_async_finished",
                username=user.username,
                server_code=target_server_code,
                path="/api/admin/law-sources/rebuild-async",
                method="POST",
                status_code=200,
                meta={"task_id": task_id, "law_version_id": result.get("law_version_id")},
            )
        except Exception as exc:  # noqa: BLE001
            _patch_admin_task(
                task_id,
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )
            metrics_store.log_event(
                event_type="admin_law_sources_rebuild_async_failed",
                username=user.username,
                server_code=target_server_code,
                path="/api/admin/law-sources/rebuild-async",
                method="POST",
                status_code=500,
                meta={"task_id": task_id, "error": str(exc)},
            )

    threading.Thread(target=_runner, daemon=True).start()
    metrics_store.log_event(
        event_type="admin_law_sources_rebuild_async_queued",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/rebuild-async",
        method="POST",
        status_code=200,
        meta={"task_id": task_id},
    )
    return {"ok": True, "task_id": task_id, "status": "queued"}


@router.post("/api/admin/law-sources/save")
async def admin_law_sources_save(
    payload: AdminLawSourcesPayload,
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, payload.server_code)
    actor_user_id = _resolve_actor_user_id(user_store, user.username)
    service = LawAdminService(workflow_service)
    try:
        result = service.publish_sources_manifest(
            server_code=target_server_code,
            source_urls=payload.source_urls,
            actor_user_id=actor_user_id,
            request_id=getattr(request.state, "request_id", ""),
            comment="law_sources_save_only",
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_law_sources_save",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/save",
        method="POST",
        status_code=200,
        meta={"sources_count": len(result.get("source_urls") or [])},
    )
    return result


@router.post("/api/admin/law-sources/preview")
async def admin_law_sources_preview(
    payload: AdminLawSourcesPayload,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, payload.server_code)
    service = LawAdminService(workflow_service)
    result = service.preview_sources(source_urls=payload.source_urls)
    metrics_store.log_event(
        event_type="admin_law_sources_preview",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/preview",
        method="POST",
        status_code=200,
        meta={
            "accepted_count": result.get("accepted_count"),
            "invalid_count": result.get("invalid_count"),
            "duplicate_count": result.get("duplicate_count"),
        },
    )
    return result


@router.get("/api/admin/law-sources/history")
async def admin_law_sources_history(
    server_code: str = Query(default="", description="Runtime server code override"),
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    user_store: UserStore = Depends(get_user_store),
    limit: int = Query(default=10, ge=1, le=100),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, server_code)
    service = LawAdminService(workflow_service)
    result = service.list_recent_versions(server_code=target_server_code, limit=limit)
    metrics_store.log_event(
        event_type="admin_law_sources_history",
        username=user.username,
        server_code=target_server_code,
        path="/api/admin/law-sources/history",
        method="GET",
        status_code=200,
        meta={"count": result.get("count", 0), "limit": limit},
    )
    return result


@router.get("/api/admin/law-sources/dependencies")
async def admin_law_sources_dependencies(
    user: AuthUser = Depends(requires_permission("manage_laws")),
    workflow_service: ContentWorkflowService = Depends(get_content_workflow_service),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    service = LawAdminService(workflow_service)
    result = service.describe_sources_dependencies()
    metrics_store.log_event(
        event_type="admin_law_sources_dependencies",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/law-sources/dependencies",
        method="GET",
        status_code=200,
        meta={"server_count": result.get("server_count"), "source_count": result.get("source_count")},
    )
    return result


@router.get("/api/admin/law-sources/tasks/{task_id}")
async def admin_law_sources_task_status(
    task_id: str,
    server_code: str = Query(default="", description="Runtime server code override"),
    user: AuthUser = Depends(requires_permission("manage_laws")),
    user_store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    target_server_code = _resolve_law_sources_server_code(user, user_store, server_code)
    task = _load_admin_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Задача не найдена."])
    if task.get("scope") != "law_sources_rebuild":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Задача не найдена."])
    if str(task.get("server_code") or "") != target_server_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Доступ запрещён."])
    metrics_store.log_event(
        event_type="admin_law_sources_task_status",
        username=user.username,
        server_code=target_server_code,
        path=f"/api/admin/law-sources/tasks/{task_id}",
        method="GET",
        status_code=200,
        meta={"status": task.get("status")},
    )
    return enrich_job_status(task, subsystem="admin_task")


@router.get("/api/admin/dashboard")
async def admin_dashboard_data(
    user: AuthUser = Depends(requires_permission("view_analytics")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    exam_store: ExamAnswersStore = Depends(get_exam_answers_store),
    user_store: UserStore = Depends(get_user_store),
):
    _ = user
    users = user_store.list_users()
    overview = metrics_store.get_overview(users=users)
    performance = metrics_store.get_performance_overview(window_minutes=30, top_endpoints=5)
    exam_import = metrics_store.get_exam_import_summary(pending_scores=exam_store.count_entries_needing_scores())
    totals = overview.get("totals", {})
    users_with_metrics = overview.get("users", [])
    blocked_count = sum(1 for row in users_with_metrics if row.get("access_blocked"))
    unverified_count = sum(1 for row in users_with_metrics if not row.get("email_verified"))

    kpis = [
        {
            "id": "users_total",
            "label": "Всего аккаунтов",
            "value": int(totals.get("users_total") or 0),
            "period": "за все время",
            "status": "neutral",
        },
        {
            "id": "events_last_24h",
            "label": "Активность за сутки",
            "value": int(totals.get("events_last_24h") or 0),
            "period": "24 часа",
            "status": "neutral",
        },
        {
            "id": "complaints_total",
            "label": "Подготовлено жалоб",
            "value": int(totals.get("complaints_total") or 0),
            "period": "за все время",
            "status": "success-soft",
        },
        {
            "id": "rehabs_total",
            "label": "Подготовлено реабилитаций",
            "value": int(totals.get("rehabs_total") or 0),
            "period": "за все время",
            "status": "success-soft",
        },
        {
            "id": "pending_scores",
            "label": "Ожидают проверки экзамена",
            "value": int(exam_import.get("pending_scores") or 0),
            "period": "текущее состояние",
            "status": "warn",
        },
        {
            "id": "error_rate",
            "label": "Доля ошибок API",
            "value": f"{round(float(performance.get('error_rate') or 0) * 100, 2)}%",
            "period": "30 минут",
            "status": "danger" if float(performance.get("error_rate") or 0) >= 0.05 else "neutral",
        },
        {
            "id": "blocked_accounts",
            "label": "Заблокированные аккаунты",
            "value": blocked_count,
            "period": "текущее состояние",
            "status": "danger" if blocked_count else "neutral",
        },
        {
            "id": "unverified_accounts",
            "label": "Неподтвержденные email",
            "value": unverified_count,
            "period": "текущее состояние",
            "status": "warn" if unverified_count else "neutral",
        },
    ]

    alerts: list[dict[str, Any]] = []
    if float(performance.get("error_rate") or 0) >= 0.05:
        alerts.append(
            {
                "severity": "danger",
                "title": "Высокая доля ошибок API",
                "description": "Проверьте журнал событий и проблемные endpoint'ы.",
                "action_url": "/admin#admin-section-events",
            }
        )
    if int(exam_import.get("pending_scores") or 0) > 0:
        alerts.append(
            {
                "severity": "warn",
                "title": "Есть очередь проверки экзаменов",
                "description": "Запустите проверку импортированных строк.",
                "action_url": "/exam-import-test",
            }
        )
    if blocked_count:
        alerts.append(
            {
                "severity": "warn",
                "title": "Есть заблокированные аккаунты",
                "description": "Проверьте причины блокировки и актуальность ограничений.",
                "action_url": "/admin#admin-section-users",
            }
        )

    quick_links = [
        {"label": "Пользователи", "url": "/admin#admin-section-users"},
        {"label": "Импорт экзаменов", "url": "/admin#admin-section-import"},
        {"label": "События и ошибки", "url": "/admin#admin-section-events"},
        {"label": "Профиль", "url": "/profile"},
    ]

    return {
        "kpis": kpis,
        "alerts": alerts,
        "quick_links": quick_links,
        "recent_events": overview.get("recent_events", [])[:10],
        "top_endpoints": performance.get("endpoint_overview", []),
        "generated_at": performance.get("generated_at"),
    }


@router.get("/api/admin/dashboard/sections/{section}")
async def admin_dashboard_section_data(
    section: str,
    user: AuthUser = Depends(requires_permission("view_analytics")),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
):
    normalized = str(section or "").strip().lower()
    try:
        payload = dashboard_service.get_section(section=normalized, username=user.username, server_id=user.server_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=[f"Unknown dashboard section: {normalized}"]) from exc
    return {"section": normalized, "data": payload}


@router.get("/api/admin/dashboard/v2")
async def admin_dashboard_v2_data(
    user: AuthUser = Depends(requires_permission("view_analytics")),
    dashboard_service: AdminDashboardService = Depends(get_admin_dashboard_service),
):
    return dashboard_service.get_dashboard(username=user.username, server_id=user.server_code)


@router.get("/api/admin/ai-pipeline")
async def admin_ai_pipeline_data(
    flow: str = Query(default="", max_length=32),
    issue_type: str = Query(default="", max_length=64),
    retrieval_context_mode: str = Query(default="", max_length=64),
    guard_warning: str = Query(default="", max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthUser = Depends(requires_permission("view_analytics")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    normalized_flow = str(flow or "").strip().lower()
    normalized_issue_type = str(issue_type or "").strip().lower()
    normalized_context_mode = str(retrieval_context_mode or "").strip().lower()
    normalized_guard_warning = str(guard_warning or "").strip().lower()
    safe_history_limit = AI_PIPELINE_RECENT_HISTORY_LIMIT

    partial_errors: list[dict[str, str]] = []
    failed_blocks: set[str] = set()

    summary: dict[str, Any] = {}
    generations: list[dict[str, Any]] = []
    feedback: list[dict[str, Any]] = []
    recent_generations: list[dict[str, Any]] = []
    recent_feedback: list[dict[str, Any]] = []
    quality_summary: dict[str, Any] = _build_ai_pipeline_quality_summary(generations=[], feedback=[])
    cost_tables: dict[str, Any] = _build_ai_pipeline_cost_tables([])
    top_inaccurate_generations: list[dict[str, Any]] = []
    flow_summaries: dict[str, dict[str, Any]] = {"law_qa": {}, "suggest": {}}
    policy_actions: list[dict[str, Any]] = []

    try:
        summary = metrics_store.summarize_ai_generation_logs(
            flow=normalized_flow,
            retrieval_context_mode=normalized_context_mode,
            guard_warning=normalized_guard_warning,
            limit=min(limit * 4, 500),
        )
    except Exception as exc:  # noqa: BLE001
        partial_errors.append(_normalize_api_error(exc, source="summary"))
        failed_blocks.add("summary")

    try:
        generations = metrics_store.list_ai_generation_logs(
            flow=normalized_flow,
            retrieval_context_mode=normalized_context_mode,
            guard_warning=normalized_guard_warning,
            limit=safe_history_limit,
        )
    except Exception as exc:  # noqa: BLE001
        partial_errors.append(_normalize_api_error(exc, source="generations"))
        failed_blocks.add("generations")
        generations = []

    try:
        feedback = metrics_store.list_ai_feedback(
            flow=normalized_flow,
            issue_type=normalized_issue_type,
            limit=safe_history_limit,
        )
    except Exception as exc:  # noqa: BLE001
        partial_errors.append(_normalize_api_error(exc, source="feedback"))
        failed_blocks.add("feedback")
        feedback = []

    try:
        recent_generations = _filter_recent_metric_items(generations, since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS)
        recent_feedback = _filter_recent_metric_items(feedback, since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS)
        recent_law_qa_generations = _filter_recent_metric_items(
            metrics_store.list_ai_generation_logs(flow="law_qa", limit=safe_history_limit),
            since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS,
        )
        recent_suggest_generations = _filter_recent_metric_items(
            metrics_store.list_ai_generation_logs(flow="suggest", limit=safe_history_limit),
            since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS,
        )
        flow_summaries = {
            "law_qa": _summarize_generation_rows(recent_law_qa_generations),
            "suggest": _summarize_generation_rows(recent_suggest_generations),
        }
        quality_summary = _build_ai_pipeline_quality_summary(
            generations=recent_generations,
            feedback=recent_feedback,
        )
        top_inaccurate_generations = _build_top_inaccurate_generations(
            generations=recent_generations,
            feedback=recent_feedback,
            limit=min(limit, 10),
        )
    except Exception as exc:  # noqa: BLE001
        partial_errors.append(_normalize_api_error(exc, source="quality"))
        failed_blocks.add("quality")
        recent_generations = _filter_recent_metric_items(generations, since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS)
        recent_feedback = _filter_recent_metric_items(feedback, since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS)
        quality_summary = _build_ai_pipeline_quality_summary(generations=[], feedback=[])
        top_inaccurate_generations = []
        flow_summaries = {"law_qa": {}, "suggest": {}}

    try:
        cost_tables = _build_ai_pipeline_cost_tables(recent_generations)
    except Exception as exc:  # noqa: BLE001
        partial_errors.append(_normalize_api_error(exc, source="cost"))
        failed_blocks.add("cost")
        cost_tables = _build_ai_pipeline_cost_tables([])

    try:
        policy_actions = _build_policy_action_log(
            quality_summary=quality_summary,
            flow_summaries=flow_summaries,
        )
    except Exception as exc:  # noqa: BLE001
        partial_errors.append(_normalize_api_error(exc, source="policy_actions"))
        failed_blocks.add("policy_actions")
        policy_actions = []

    if len(failed_blocks) == 6:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=["Не удалось загрузить AI Pipeline: все блоки недоступны."],
        )

    return {
        "flow": normalized_flow,
        "issue_type": normalized_issue_type,
        "retrieval_context_mode": normalized_context_mode,
        "guard_warning": normalized_guard_warning,
        "limit": limit,
        "summary": summary,
        "quality_summary": quality_summary,
        "flow_summaries": flow_summaries,
        "cost_tables": cost_tables,
        "top_inaccurate_generations": top_inaccurate_generations,
        "policy_actions": policy_actions,
        "generations": generations[:limit],
        "feedback": feedback[:limit],
        "partial_errors": partial_errors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/admin/users")
async def admin_users_data(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    user_sort: str = "complaints",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    _ = user
    overview = metrics_store.get_overview(
        users=user_store.list_users(),
        search=search,
        blocked_only=blocked_only,
        tester_only=tester_only,
        gka_only=gka_only,
        unverified_only=unverified_only,
        user_sort=user_sort,
    )
    users = overview.get("users", [])
    total = len(users)
    paged = users[offset : offset + limit]
    return {
        "items": paged,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "search": search,
            "blocked_only": blocked_only,
            "tester_only": tester_only,
            "gka_only": gka_only,
            "unverified_only": unverified_only,
            "user_sort": user_sort,
        },
    }


@router.get("/api/admin/users/{username}")
async def admin_user_details(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    _ = user
    normalized = str(username or "").strip().lower()
    overview = metrics_store.get_overview(users=user_store.list_users(), search=normalized)
    users = overview.get("users", [])
    target = next((item for item in users if str(item.get("username", "")).strip().lower() == normalized), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Пользователь не найден."])

    recent_actions = [
        event
        for event in overview.get("recent_events", [])
        if str(event.get("username", "")).strip().lower() == normalized
        or str((event.get("meta") or {}).get("target_username", "")).strip().lower() == normalized
    ][:20]

    permission_codes = user_store.get_permission_codes(normalized, server_code=target.get("server_code"))
    effective_permissions = {
        "manage_servers": "manage_servers" in permission_codes,
        "manage_laws": "manage_laws" in permission_codes,
        "view_analytics": "view_analytics" in permission_codes,
        "exam_import": "exam_import" in permission_codes,
        "court_claims": "court_claims" in permission_codes,
        "complaint_presets": "complaint_presets" in permission_codes,
    }

    recent_events = [event for event in overview.get("recent_events", []) if str(event.get("username", "")).strip().lower() == normalized][:20]
    failed_events = [event for event in recent_events if int(event.get("status_code") or 0) >= 400]
    activity_snapshot = {
        "api_requests": int(target.get("api_requests") or 0),
        "failed_api_requests": int(target.get("failed_api_requests") or 0),
        "complaints": int(target.get("complaints") or 0),
        "rehabs": int(target.get("rehabs") or 0),
        "ai_suggestions": int(target.get("ai_suggestions") or 0),
        "ai_ocr_requests": int(target.get("ai_ocr_requests") or 0),
        "resource_units": int(target.get("resource_units") or 0),
        "risk_score": int(target.get("risk_score") or 0),
        "risk_flags": list(target.get("risk_flags") or []),
        "recent_events_count": len(recent_events),
        "recent_errors_count": len(failed_events),
    }

    return {
        "user": target,
        "effective_permissions": effective_permissions,
        "recent_admin_actions": recent_actions,
        "recent_events": recent_events,
        "activity_snapshot": activity_snapshot,
    }


@router.get("/api/admin/role-history")
async def admin_role_history(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    limit: int = Query(default=100, ge=1, le=1000),
):
    _ = user
    overview = metrics_store.get_overview(users=user_store.list_users())
    role_events = {
        "admin_grant_tester",
        "admin_revoke_tester",
        "admin_grant_gka",
        "admin_revoke_gka",
    }
    items = [event for event in overview.get("recent_events", []) if str(event.get("event_type", "")) in role_events]
    return {
        "items": items[:limit],
        "total": len(items),
    }


@router.get("/api/admin/overview")
async def admin_overview(
    user: AuthUser = Depends(requires_permission("view_analytics")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    exam_store: ExamAnswersStore = Depends(get_exam_answers_store),
    user_store: UserStore = Depends(get_user_store),
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    event_search: str = "",
    event_type: str = "",
    failed_events_only: bool = False,
    users_limit: int = 0,
    user_sort: str = "complaints",
):
    _ = user
    partial_errors: list[dict[str, str]] = []
    safe_user_limit = None
    try:
        safe_user_limit = int(users_limit)
        if safe_user_limit <= 0:
            safe_user_limit = None
    except (TypeError, ValueError):
        safe_user_limit = None
    payload: dict[str, Any] = {
        "totals": {},
        "users": [],
        "users_filtered_total": 0,
        "top_endpoints": [],
        "recent_events": [],
        "recent_events_filtered_total": 0,
        "filters": {"user_sort": user_sort},
        "error_explorer": {
            "items": [],
            "total": 0,
            "by_event_type": [],
            "by_path": [],
        },
    }

    users: list[dict[str, Any]] = []
    try:
        users = user_store.list_users(limit=safe_user_limit)
    except Exception as exc:  # noqa: BLE001
        partial_errors.append(_normalize_api_error(exc, source="users"))

    if users:
        try:
            payload = metrics_store.get_overview(
                users=users,
                search=search,
                blocked_only=blocked_only,
                tester_only=tester_only,
                gka_only=gka_only,
                unverified_only=unverified_only,
                event_search=event_search,
                event_type=event_type,
                failed_events_only=failed_events_only,
                user_sort=user_sort,
            )
        except Exception as exc:  # noqa: BLE001
            partial_errors.append(_normalize_api_error(exc, source="overview"))
            payload["totals"] = {"users_total": len(users)}
    else:
        payload["totals"] = {"users_total": 0}

    payload["exam_import"] = build_exam_import_overview_payload(
        exam_store=exam_store,
        metrics_store=metrics_store,
        include_recent_entries=True,
        on_error=lambda source, exc: partial_errors.append(_normalize_api_error(exc, source=source)),
    )
    try:
        ai_summary = metrics_store.summarize_ai_generation_logs(limit=300)
        totals = payload.setdefault("totals", {})
        totals["ai_generation_total"] = int(ai_summary.get("total_generations") or 0)
        totals["ai_input_tokens_total"] = int(ai_summary.get("input_tokens_total") or 0)
        totals["ai_output_tokens_total"] = int(ai_summary.get("output_tokens_total") or 0)
        totals["ai_total_tokens_total"] = int(ai_summary.get("total_tokens_total") or 0)
        totals["ai_estimated_cost_total_usd"] = round(float(ai_summary.get("estimated_cost_total_usd") or 0.0), 6)
        totals["ai_estimated_cost_samples"] = int(ai_summary.get("estimated_cost_samples") or 0)
    except Exception as exc:  # noqa: BLE001
        partial_errors.append(_normalize_api_error(exc, source="ai_costs"))

    try:
        payload["model_policy"] = _load_model_policy()
    except Exception as exc:  # noqa: BLE001
        partial_errors.append(_normalize_api_error(exc, source="model_policy"))
        payload["model_policy"] = {}

    try:
        error_items = metrics_store.list_error_events(
            event_search=event_search,
            event_type=event_type,
            limit=120,
        )
        by_event_type: dict[str, int] = {}
        by_path: dict[str, int] = {}
        for item in error_items:
            event_key = str(item.get("event_type") or "unknown")
            path_key = str(item.get("path") or "-")
            by_event_type[event_key] = by_event_type.get(event_key, 0) + 1
            by_path[path_key] = by_path.get(path_key, 0) + 1
        payload["error_explorer"] = {
            "items": error_items,
            "total": len(error_items),
            "by_event_type": [
                {"event_type": key, "count": value}
                for key, value in sorted(by_event_type.items(), key=lambda pair: (-pair[1], pair[0]))[:10]
            ],
            "by_path": [
                {"path": key, "count": value}
                for key, value in sorted(by_path.items(), key=lambda pair: (-pair[1], pair[0]))[:10]
            ],
        }
    except Exception as exc:  # noqa: BLE001
        partial_errors.append(_normalize_api_error(exc, source="error_explorer"))

    payload["synthetic"] = _build_synthetic_summary(payload.get("recent_events", []))
    payload["partial_errors"] = partial_errors
    return payload


@router.post("/api/admin/synthetic/run")
async def run_synthetic_suite(
    request: Request,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
):
    _ = user
    body = await request.json()
    suite = str((body or {}).get("suite") or "").strip().lower()
    trigger = str((body or {}).get("trigger") or "manual").strip().lower() or "manual"
    server_code = str((body or {}).get("server_code") or user.server_code or "blackberry").strip().lower() or "blackberry"
    if suite not in {"smoke", "nightly", "load", "fault"}:
        raise HTTPException(status_code=400, detail=["suite must be one of smoke|nightly|load|fault"])
    runner = SyntheticRunnerService(metrics_store)
    return runner.run_suite(suite=suite, server_code=server_code, trigger=trigger)


@router.get("/api/admin/performance")
async def admin_performance(
    user: AuthUser = Depends(requires_permission("view_analytics")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    window_minutes: int = 15,
    top_endpoints: int = 10,
):
    _ = user
    safe_window = max(1, min(int(window_minutes or 1), 60 * 24))
    safe_endpoints = max(1, min(int(top_endpoints or 10), 50))
    cache_key = _cache_key(window_minutes=safe_window, top_endpoints=safe_endpoints)
    cached_payload = _load_cached_performance_payload(cache_key)
    if cached_payload is not None:
        return cached_payload

    payload = metrics_store.get_performance_overview(
        window_minutes=safe_window,
        top_endpoints=safe_endpoints,
    )
    total_requests = int(payload.get("total_api_requests") or 0)
    failed_requests = int(payload.get("error_count") or 0)
    throughput_rps = float(payload.get("throughput_rps") or 0.0)
    p50_ms = payload.get("p50_ms")
    p95_ms = payload.get("p95_ms")
    avg_ms = payload.get("avg_ms")
    payload["latency"] = {
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
        "avg_ms": avg_ms,
    }
    payload["rates"] = {
        "requests_per_second": round(throughput_rps, 4),
        "error_rate": float(payload.get("error_rate") or 0.0),
    }
    payload["top_endpoints"] = list(payload.get("endpoint_overview") or [])
    payload["totals"] = {
        **dict(payload.get("totals") or {}),
        "total_requests": total_requests,
        "failed_requests": failed_requests,
    }
    payload["window_minutes"] = safe_window
    payload["top_endpoints_limit"] = safe_endpoints
    payload["snapshot_at"] = datetime.now(timezone.utc).isoformat()
    payload["cached"] = False
    _store_performance_payload(cache_key, payload)
    return payload


@router.get("/api/admin/users.csv")
async def admin_users_csv(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    users_limit: int = 0,
    user_sort: str = "complaints",
) -> Response:
    _ = user
    safe_user_limit = None
    try:
        safe_user_limit = int(users_limit)
        if safe_user_limit <= 0:
            safe_user_limit = None
    except (TypeError, ValueError):
        safe_user_limit = None
    content = metrics_store.export_users_csv(
        users=user_store.list_users(limit=safe_user_limit),
        search=search,
        blocked_only=blocked_only,
        tester_only=tester_only,
        gka_only=gka_only,
        unverified_only=unverified_only,
        user_sort=user_sort,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="admin-users.csv"'},
    )


@router.get("/api/admin/events.csv")
async def admin_events_csv(
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    event_search: str = "",
    event_type: str = "",
    failed_events_only: bool = False,
) -> Response:
    _ = user
    content = metrics_store.export_events_csv(
        event_search=event_search,
        event_type=event_type,
        failed_events_only=failed_events_only,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="admin-events.csv"'},
    )


@router.post("/api/admin/users/{username}/verify-email")
async def admin_verify_email(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_mark_email_verified(username)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_verify_email",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/verify-email",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/block")
async def admin_block_user(
    username: str,
    payload: AdminBlockPayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_access_blocked(username, payload.reason)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_block_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/block",
        method="POST",
        status_code=200,
        meta={"target_username": username, "reason": payload.reason},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/unblock")
async def admin_unblock_user(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_clear_access_blocked(username)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_unblock_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/unblock",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/grant-tester")
async def admin_grant_tester(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_tester_status(username, True)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_grant_tester",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/grant-tester",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/revoke-tester")
async def admin_revoke_tester(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_tester_status(username, False)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_revoke_tester",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/revoke-tester",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/grant-gka")
async def admin_grant_gka(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_gka_status(username, True)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_grant_gka",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/grant-gka",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/revoke-gka")
async def admin_revoke_gka(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_gka_status(username, False)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_revoke_gka",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/revoke-gka",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/email")
async def admin_update_email(
    username: str,
    payload: AdminEmailUpdatePayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_update_email(username, payload.email)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_update_email",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/email",
        method="POST",
        status_code=200,
        meta={"target_username": username, "email": payload.email},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/reset-password")
async def admin_reset_password(
    username: str,
    payload: AdminPasswordResetPayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_reset_password(username, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_reset_password",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/reset-password",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/deactivate")
async def admin_deactivate_user(
    username: str,
    payload: AdminDeactivatePayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_deactivate_user(username, payload.reason)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_deactivate_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/deactivate",
        method="POST",
        status_code=200,
        meta={"target_username": username, "reason": payload.reason},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/reactivate")
async def admin_reactivate_user(
    username: str,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_reactivate_user(username)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_reactivate_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/reactivate",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/daily-quota")
async def admin_set_daily_quota(
    username: str,
    payload: AdminQuotaPayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_daily_quota(username, payload.daily_limit)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_set_daily_quota",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/daily-quota",
        method="POST",
        status_code=200,
        meta={"target_username": username, "daily_limit": payload.daily_limit},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/exam-import/reset-scores")
async def admin_reset_exam_scores_for_user(
    payload: AdminExamScoreResetPayload,
    user: AuthUser = Depends(requires_permission("manage_laws")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    exam_store: ExamAnswersStore = Depends(get_exam_answers_store),
):
    if not any([payload.full_name, payload.discord_tag, payload.passport]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Нужно указать хотя бы один фильтр: full_name, discord_tag или passport."],
        )
    reset_count = exam_store.reset_scores_for_user(
        full_name=payload.full_name,
        discord_tag=payload.discord_tag,
        passport=payload.passport,
    )
    metrics_store.log_event(
        event_type="admin_reset_exam_scores",
        username=user.username,
        server_code=user.server_code,
        path="/api/admin/exam-import/reset-scores",
        method="POST",
        status_code=200,
        meta={
            "full_name": payload.full_name,
            "discord_tag": payload.discord_tag,
            "passport": payload.passport,
            "reset_count": reset_count,
        },
    )
    return {"ok": True, "reset_count": reset_count}


@router.post("/api/admin/users/bulk-actions")
async def admin_bulk_actions(
    payload: AdminBulkActionPayload,
    user: AuthUser = Depends(requires_permission("manage_servers")),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    if payload.run_async:
        task_id = f"admin-bulk-{uuid.uuid4().hex}"
        created_at = datetime.now(timezone.utc).isoformat()
        _put_admin_task(
            {
                "task_id": task_id,
                "status": "queued",
                "created_at": created_at,
                "started_at": "",
                "finished_at": "",
                "progress": {"done": 0, "total": len(payload.usernames)},
                "result": None,
                "error": "",
            }
        )

        def _runner() -> None:
            _patch_admin_task(task_id, status="running", started_at=datetime.now(timezone.utc).isoformat())
            try:
                result = _apply_bulk_action(
                    payload=payload,
                    user=user,
                    metrics_store=metrics_store,
                    user_store=user_store,
                    task_id=task_id,
                )
                _patch_admin_task(
                    task_id,
                    status="finished",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    result=result,
                )
            except Exception as exc:  # noqa: BLE001
                _patch_admin_task(
                    task_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    error=str(exc),
                )

        threading.Thread(target=_runner, daemon=True).start()
        return {"ok": True, "task_id": task_id, "status": "queued"}

    result = _apply_bulk_action(payload=payload, user=user, metrics_store=metrics_store, user_store=user_store)
    return {"ok": True, "status": "finished", "result": result}


@router.get("/api/admin/tasks/{task_id}")
async def admin_task_status(task_id: str, _: AuthUser = Depends(requires_permission("manage_servers"))):
    task = _load_admin_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Задача не найдена."])
    return enrich_job_status(task, subsystem="admin_task")
