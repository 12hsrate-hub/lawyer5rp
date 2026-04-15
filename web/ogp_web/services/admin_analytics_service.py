from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Callable

import yaml

from ogp_web.services.admin_overview_service import build_exam_import_overview_payload

_PERFORMANCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PERFORMANCE_CACHE_TTL_SECONDS = 10
_PERFORMANCE_CACHE_LOCK = threading.Lock()
_MODEL_POLICY_PATH = Path(__file__).resolve().parents[3] / "config" / "model_policy.yaml"


def _normalize_api_error(exc: Exception, *, source: str) -> dict[str, str]:
    return {
        "source": source,
        "message": str(exc) or f"{source}_error",
    }


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
        cached_copy = deepcopy(payload)
        cached_copy["cached"] = True
        return cached_copy


def _store_performance_payload(cache_key: str, payload: dict[str, Any]) -> None:
    with _PERFORMANCE_CACHE_LOCK:
        _PERFORMANCE_CACHE[cache_key] = (monotonic(), deepcopy(payload))


def _load_model_policy() -> dict[str, Any]:
    if not _MODEL_POLICY_PATH.exists():
        return {}
    try:
        payload = yaml.safe_load(_MODEL_POLICY_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"failed_to_load_model_policy: {exc}") from exc
    return payload if isinstance(payload, dict) else {}


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
                "created_at": event.get("created_at"),
                "suite": str(raw_meta.get("suite") or "unknown"),
                "server_code": str(raw_meta.get("server_code") or event.get("server_code") or "unknown"),
                "status": str(raw_meta.get("status") or "ok"),
                "trigger": str(raw_meta.get("trigger") or "manual"),
                "failures": list(raw_meta.get("failures") or []),
            }
        )

    latest_runs = run_events[:10]
    failed_runs = [item for item in latest_runs if item.get("status") not in {"ok", "passed"}]
    return {
        "latest_runs": latest_runs,
        "failed_runs": failed_runs,
        "total_runs": len(run_events),
        "failed_runs_total": len([item for item in run_events if item.get("status") not in {"ok", "passed"}]),
        "status": "warn" if failed_runs else "ok",
    }


class AdminAnalyticsService:
    def __init__(self, *, model_policy_loader: Callable[[], dict[str, Any]] | None = None):
        self._model_policy_loader = model_policy_loader or _load_model_policy

    def build_dashboard_payload(self, *, metrics_store, exam_store, user_store) -> dict[str, Any]:
        users = user_store.list_users()
        overview = metrics_store.get_overview(users=users)
        performance = metrics_store.get_performance_overview(window_minutes=30, top_endpoints=5)
        exam_import = metrics_store.get_exam_import_summary(
            pending_scores=exam_store.count_entries_needing_scores()
        )
        totals = dict(overview.get("totals") or {})
        users_with_metrics = list(overview.get("users") or [])
        blocked_count = sum(1 for row in users_with_metrics if row.get("access_blocked"))
        unverified_count = sum(1 for row in users_with_metrics if not row.get("email_verified"))
        error_rate = float(performance.get("error_rate") or 0.0)

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
                "value": f"{round(error_rate * 100, 2)}%",
                "period": "30 минут",
                "status": "danger" if error_rate >= 0.05 else "neutral",
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
        if error_rate >= 0.05:
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

        return {
            "kpis": kpis,
            "alerts": alerts,
            "quick_links": [
                {"label": "Пользователи", "url": "/admin#admin-section-users"},
                {"label": "Импорт экзаменов", "url": "/admin#admin-section-import"},
                {"label": "События и ошибки", "url": "/admin#admin-section-events"},
                {"label": "Профиль", "url": "/profile"},
            ],
            "recent_events": list(overview.get("recent_events") or [])[:10],
            "top_endpoints": list(performance.get("endpoint_overview") or []),
            "generated_at": performance.get("generated_at"),
        }

    def build_overview_payload(
        self,
        *,
        metrics_store,
        exam_store,
        user_store,
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
    ) -> dict[str, Any]:
        partial_errors: list[dict[str, str]] = []
        safe_user_limit = self._normalize_optional_limit(users_limit)
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
            payload["model_policy"] = self._model_policy_loader()
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

        payload["synthetic"] = _build_synthetic_summary(list(payload.get("recent_events") or []))
        payload["partial_errors"] = partial_errors
        return payload

    def build_performance_payload(
        self,
        *,
        metrics_store,
        window_minutes: int = 15,
        top_endpoints: int = 10,
    ) -> dict[str, Any]:
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
        payload["latency"] = {
            "p50_ms": payload.get("p50_ms"),
            "p95_ms": payload.get("p95_ms"),
            "avg_ms": payload.get("avg_ms"),
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

    @staticmethod
    def _normalize_optional_limit(value: Any) -> int | None:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return None
        return normalized if normalized > 0 else None
