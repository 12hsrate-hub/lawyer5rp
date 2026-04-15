from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_WEB_SECRET", "test-secret")
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
os.environ.setdefault("OGP_SKIP_DEFAULT_APP_INIT", "1")

from ogp_web.services.admin_analytics_service import AdminAnalyticsService


class _DashboardMetricsStore:
    def get_overview(self, *, users, **kwargs):
        return {
            "totals": {
                "users_total": len(users),
                "events_last_24h": 12,
                "complaints_total": 7,
                "rehabs_total": 3,
            },
            "users": users,
            "recent_events": [{"event_type": "login"}, {"event_type": "generate"}],
        }

    def get_performance_overview(self, *, window_minutes, top_endpoints):
        return {
            "error_rate": 0.051,
            "endpoint_overview": [{"path": "/api/admin/overview", "requests": 4}],
            "generated_at": "2026-04-15T10:00:00+00:00",
            "total_api_requests": 20,
            "error_count": 2,
            "throughput_rps": 1.2345,
            "p50_ms": 120,
            "p95_ms": 350,
            "avg_ms": 180,
        }

    def get_exam_import_summary(self, *, pending_scores):
        return {"pending_scores": pending_scores}


class _OverviewMetricsStore(_DashboardMetricsStore):
    def summarize_ai_generation_logs(self, *, limit):
        return {
            "total_generations": 5,
            "input_tokens_total": 120,
            "output_tokens_total": 80,
            "total_tokens_total": 200,
            "estimated_cost_total_usd": 1.25,
            "estimated_cost_samples": 5,
        }

    def list_error_events(self, *, event_search, event_type, limit):
        return [
            {"event_type": "server_error", "path": "/api/admin/overview"},
            {"event_type": "server_error", "path": "/api/admin/overview"},
            {"event_type": "quota", "path": "/api/profile"},
        ]


class _UserStore:
    def list_users(self, limit=None):
        users = [
            {"username": "alpha", "access_blocked": True, "email_verified": False},
            {"username": "beta", "access_blocked": False, "email_verified": True},
        ]
        return users[:limit] if limit else users


class _ExamStore:
    def count_entries_needing_scores(self):
        return 3

    def list_entries(self, limit=8):
        return [{"id": 1}, {"id": 2}][:limit]

    def list_entries_with_failed_scores(self, limit=5):
        return [{"id": 9}][:limit]


def test_build_dashboard_payload_contains_kpis_alerts_and_links():
    service = AdminAnalyticsService()

    payload = service.build_dashboard_payload(
        metrics_store=_DashboardMetricsStore(),
        exam_store=_ExamStore(),
        user_store=_UserStore(),
    )

    assert len(payload["kpis"]) == 8
    assert any(item["severity"] == "danger" for item in payload["alerts"])
    assert any(item["label"] == "Пользователи" for item in payload["quick_links"])
    assert payload["top_endpoints"] == [{"path": "/api/admin/overview", "requests": 4}]


def test_build_overview_payload_collects_totals_model_policy_and_error_explorer():
    service = AdminAnalyticsService(model_policy_loader=lambda: {"recommended_defaults": {"default_tier": "gpt-5.4-mini"}})

    payload = service.build_overview_payload(
        metrics_store=_OverviewMetricsStore(),
        exam_store=_ExamStore(),
        user_store=_UserStore(),
        user_sort="username",
    )

    assert payload["totals"]["users_total"] == 2
    assert payload["totals"]["ai_total_tokens_total"] == 200
    assert payload["model_policy"]["recommended_defaults"]["default_tier"] == "gpt-5.4-mini"
    assert payload["error_explorer"]["total"] == 3
    assert payload["error_explorer"]["by_event_type"][0] == {"event_type": "server_error", "count": 2}


def test_build_performance_payload_returns_cached_second_response():
    metrics_store = _DashboardMetricsStore()
    service = AdminAnalyticsService()

    first = service.build_performance_payload(metrics_store=metrics_store, window_minutes=30, top_endpoints=6)
    second = service.build_performance_payload(metrics_store=metrics_store, window_minutes=30, top_endpoints=6)

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["totals"]["total_requests"] == 20
    assert second["top_endpoints_limit"] == 6
