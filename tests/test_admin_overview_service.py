from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.admin_overview_service import (
    build_async_jobs_overview_payload,
    build_exam_import_overview_payload,
    build_law_jobs_overview_payload,
)


class _FakeExamStore:
    def count_entries_needing_scores(self):
        return 3

    def list_entries(self, limit: int = 8):
        return [{"id": 1}, {"id": 2}, {"id": 3}][:limit]

    def list_entries_with_failed_scores(self, limit: int = 5):
        return [{"id": 9}, {"id": 10}][:limit]


class _FakeMetricsStore:
    def get_exam_import_summary(self, *, pending_scores: int):
        return {
            "pending_scores": pending_scores,
            "last_sync": "2026-04-15T00:00:00+00:00",
            "last_score": "2026-04-15T01:00:00+00:00",
            "recent_failures": [{"kind": "sync_failed"}],
            "recent_row_failures": [{"row_id": "5"}],
        }


def test_build_exam_import_overview_payload_builds_summary_and_optional_recent_entries():
    payload = build_exam_import_overview_payload(
        exam_store=_FakeExamStore(),
        metrics_store=_FakeMetricsStore(),
        include_recent_entries=True,
    )

    assert payload["pending_scores"] == 3
    assert payload["summary"]["pending_scores"] == 3
    assert payload["summary"]["failed_entries"] == 2
    assert payload["summary"]["recent_failures"] == 1
    assert payload["summary"]["recent_row_failures"] == 1
    assert payload["summary"]["problem_signals"] == 4
    assert len(payload["recent_entries"]) == 3
    assert len(payload["failed_entries"]) == 2


def test_build_exam_import_overview_payload_reports_partial_errors_and_defaults():
    class _BrokenExamStore:
        def count_entries_needing_scores(self):
            raise RuntimeError("broken_count")

        def list_entries(self, limit: int = 8):
            raise RuntimeError("broken_entries")

        def list_entries_with_failed_scores(self, limit: int = 5):
            raise RuntimeError("broken_failed")

    class _BrokenMetricsStore:
        def get_exam_import_summary(self, *, pending_scores: int):
            raise RuntimeError("broken_summary")

    seen: list[tuple[str, str]] = []

    payload = build_exam_import_overview_payload(
        exam_store=_BrokenExamStore(),
        metrics_store=_BrokenMetricsStore(),
        include_recent_entries=True,
        on_error=lambda source, exc: seen.append((source, str(exc))),
    )

    assert payload["pending_scores"] == 0
    assert payload["summary"]["problem_signals"] == 0
    assert payload["recent_entries"] == []
    assert payload["failed_entries"] == []
    assert seen == [
        ("exam_pending_scores", "broken_count"),
        ("exam_summary", "broken_summary"),
        ("exam_failed_entries", "broken_failed"),
        ("exam_recent_entries", "broken_entries"),
    ]


def test_build_law_jobs_overview_payload_filters_scope_and_builds_alerts():
    payload = build_law_jobs_overview_payload(
        tasks=[
            {"task_id": "a", "scope": "law_sources_rebuild", "server_code": "blackberry", "status": "failed", "error": "boom"},
            {"task_id": "b", "scope": "law_sources_rebuild", "server_code": "blackberry", "status": "queued"},
            {"task_id": "c", "scope": "other", "server_code": "blackberry", "status": "failed"},
        ]
    )

    assert payload["summary"] == {
        "total_tasks": 2,
        "running_tasks": 1,
        "failed_tasks": 1,
        "alerts_count": 1,
    }
    assert payload["alerts"] == [
        {"kind": "failed_rebuild", "task_id": "a", "server_code": "blackberry", "error": "boom"}
    ]
    assert payload["running"] == [{"task_id": "b", "scope": "law_sources_rebuild", "server_code": "blackberry", "status": "queued"}]


def test_build_async_jobs_overview_payload_groups_problem_jobs_by_type():
    payload = build_async_jobs_overview_payload(
        items=[
            {"id": 1, "job_type": "content_reindex", "canonical_status": "retry_scheduled", "raw_status": "retry_scheduled"},
            {"id": 2, "job_type": "content_reindex", "canonical_status": "failed", "raw_status": "dead_lettered"},
            {"id": 3, "job_type": "document_export", "canonical_status": "running", "raw_status": "processing"},
        ]
    )

    assert payload["summary"] == {
        "total_jobs": 3,
        "problem_jobs": 2,
        "failed_jobs": 1,
        "retry_scheduled_jobs": 1,
        "running_jobs": 1,
    }
    assert len(payload["problem_jobs"]) == 2
    assert payload["by_job_type"] == [{"job_type": "content_reindex", "count": 2}]
