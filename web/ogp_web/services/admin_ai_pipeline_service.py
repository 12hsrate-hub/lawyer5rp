from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ogp_web.services.point3_policy_service import load_point3_eval_thresholds
from ogp_web.storage.admin_metrics_store import AdminMetricsStore

LOGGER = logging.getLogger(__name__)
AI_PIPELINE_RECENT_WINDOW_HOURS = 24
AI_PIPELINE_RECENT_HISTORY_LIMIT = 5000


def _point3_monitoring_threshold(level: str, metric: str, fallback: float) -> float:
    payload = load_point3_eval_thresholds()
    monitoring = payload.get("monitoring") if isinstance(payload, dict) else {}
    level_payload = monitoring.get(level) if isinstance(monitoring, dict) else {}
    try:
        value = float((level_payload or {}).get(metric))
    except (TypeError, ValueError, AttributeError):
        value = fallback
    return value * 100.0


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


def filter_recent_metric_items(items: list[dict[str, Any]], *, since_hours: int = 24) -> list[dict[str, Any]]:
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0, *, generation_id: str = "", field: str = "value") -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        LOGGER.warning(
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


def _is_generation_fallback(meta: dict[str, Any]) -> bool:
    attempt_path = str(meta.get("attempt_path") or "").strip().lower()
    if meta.get("context_compacted"):
        return True
    return bool(attempt_path) and attempt_path not in {"direct", "proxy", "cache"}


def summarize_generation_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
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
            estimated_cost_total += safe_float(meta.get("estimated_cost_usd"), default=0.0)
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


def build_ai_pipeline_quality_summary(
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


def build_ai_pipeline_cost_tables(generations: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    by_flow: dict[str, dict[str, Any]] = {}
    for row in generations:
        meta = row.get("meta") or {}
        generation_id = str(meta.get("generation_id") or "").strip()
        model = str(meta.get("model") or "unknown").strip() or "unknown"
        flow = str(meta.get("flow") or "unknown").strip() or "unknown"
        cost_value = safe_float(
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


def build_top_inaccurate_generations(
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
        generation_cost = safe_float(
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


def build_policy_action_log(
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
        actions.append({"severity": "danger", "title": "Disable nano for 6h", "reason": f"guard_fail_rate={guard_fail_rate}%"})
    if isinstance(wrong_law_rate, (int, float)) and wrong_law_rate > 4.0:
        actions.append({"severity": "danger", "title": "Force full for law_qa for 24h", "reason": f"wrong_law_rate={wrong_law_rate}%"})
    if isinstance(hallucination_rate, (int, float)) and hallucination_rate > 1.5:
        actions.append({"severity": "danger", "title": "Enable strict mode for low-confidence", "reason": f"hallucination_rate={hallucination_rate}%"})
    if isinstance(unsupported_article_rate, (int, float)) and unsupported_article_rate > _point3_monitoring_threshold("critical", "unsupported_article_rate", 0.03):
        actions.append({"severity": "danger", "title": "Rollback to factual_only for article references", "reason": f"unsupported_article_rate={unsupported_article_rate}%"})
    if isinstance(new_fact_validation_rate, (int, float)) and new_fact_validation_rate > _point3_monitoring_threshold("critical", "new_fact_rate", 0.02):
        actions.append({"severity": "danger", "title": "Investigate invented-fact spike", "reason": f"new_fact_validation_rate={new_fact_validation_rate}%"})
    if isinstance(format_violation_rate, (int, float)) and format_violation_rate > _point3_monitoring_threshold("critical", "format_violation_rate", 0.05):
        actions.append({"severity": "warn", "title": "Tighten prompt format enforcement", "reason": f"format_violation_rate={format_violation_rate}%"})
    if isinstance(validation_retry_rate, (int, float)) and validation_retry_rate > _point3_monitoring_threshold("critical", "validation_retry_rate", 0.12):
        actions.append({"severity": "warn", "title": "Review point3 retry volume", "reason": f"validation_retry_rate={validation_retry_rate}%"})
    if isinstance(safe_fallback_rate, (int, float)) and safe_fallback_rate > _point3_monitoring_threshold("critical", "safe_fallback_rate", 0.12):
        actions.append({"severity": "warn", "title": "Review safe factual fallback spike", "reason": f"safe_fallback_rate={safe_fallback_rate}%"})
    if isinstance(law_qa_p95, (int, float)) and law_qa_p95 > 10000:
        actions.append({"severity": "warn", "title": "Review law_qa latency tiering", "reason": f"p95_latency_law_qa={law_qa_p95}ms"})
    if isinstance(suggest_p95, (int, float)) and suggest_p95 > 13000:
        actions.append({"severity": "warn", "title": "Review suggest latency tiering", "reason": f"p95_latency_suggest={suggest_p95}ms"})

    if not actions:
        actions.append(
            {
                "severity": "success-soft",
                "title": "No active policy triggers",
                "reason": "Recent quality and latency sample stays within configured bands.",
            }
        )
    return actions


class AdminAiPipelineService:
    def build_payload(
        self,
        *,
        metrics_store,
        flow: str = "",
        issue_type: str = "",
        retrieval_context_mode: str = "",
        guard_warning: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
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
        quality_summary: dict[str, Any] = build_ai_pipeline_quality_summary(generations=[], feedback=[])
        cost_tables: dict[str, Any] = build_ai_pipeline_cost_tables([])
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
            partial_errors.append({"source": "summary", "message": str(exc) or "summary_error"})
            failed_blocks.add("summary")

        try:
            generations = metrics_store.list_ai_generation_logs(
                flow=normalized_flow,
                retrieval_context_mode=normalized_context_mode,
                guard_warning=normalized_guard_warning,
                limit=safe_history_limit,
            )
        except Exception as exc:  # noqa: BLE001
            partial_errors.append({"source": "generations", "message": str(exc) or "generations_error"})
            failed_blocks.add("generations")
            generations = []

        try:
            feedback = metrics_store.list_ai_feedback(
                flow=normalized_flow,
                issue_type=normalized_issue_type,
                limit=safe_history_limit,
            )
        except Exception as exc:  # noqa: BLE001
            partial_errors.append({"source": "feedback", "message": str(exc) or "feedback_error"})
            failed_blocks.add("feedback")
            feedback = []

        try:
            recent_generations = filter_recent_metric_items(generations, since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS)
            recent_feedback = filter_recent_metric_items(feedback, since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS)
            recent_law_qa_generations = filter_recent_metric_items(
                metrics_store.list_ai_generation_logs(flow="law_qa", limit=safe_history_limit),
                since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS,
            )
            recent_suggest_generations = filter_recent_metric_items(
                metrics_store.list_ai_generation_logs(flow="suggest", limit=safe_history_limit),
                since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS,
            )
            flow_summaries = {
                "law_qa": summarize_generation_rows(recent_law_qa_generations),
                "suggest": summarize_generation_rows(recent_suggest_generations),
            }
            quality_summary = build_ai_pipeline_quality_summary(generations=recent_generations, feedback=recent_feedback)
            top_inaccurate_generations = build_top_inaccurate_generations(
                generations=recent_generations,
                feedback=recent_feedback,
                limit=min(limit, 10),
            )
        except Exception as exc:  # noqa: BLE001
            partial_errors.append({"source": "quality", "message": str(exc) or "quality_error"})
            failed_blocks.add("quality")
            recent_generations = filter_recent_metric_items(generations, since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS)
            recent_feedback = filter_recent_metric_items(feedback, since_hours=AI_PIPELINE_RECENT_WINDOW_HOURS)
            quality_summary = build_ai_pipeline_quality_summary(generations=[], feedback=[])
            top_inaccurate_generations = []
            flow_summaries = {"law_qa": {}, "suggest": {}}

        try:
            cost_tables = build_ai_pipeline_cost_tables(recent_generations)
        except Exception as exc:  # noqa: BLE001
            partial_errors.append({"source": "cost", "message": str(exc) or "cost_error"})
            failed_blocks.add("cost")
            cost_tables = build_ai_pipeline_cost_tables([])

        try:
            policy_actions = build_policy_action_log(
                quality_summary=quality_summary,
                flow_summaries=flow_summaries,
            )
        except Exception as exc:  # noqa: BLE001
            partial_errors.append({"source": "policy_actions", "message": str(exc) or "policy_actions_error"})
            failed_blocks.add("policy_actions")
            policy_actions = []

        if len(failed_blocks) == 6:
            raise RuntimeError("Не удалось загрузить AI Pipeline: все блоки недоступны.")

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
