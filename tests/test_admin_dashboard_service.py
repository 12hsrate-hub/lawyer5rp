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

from ogp_web.services.admin_dashboard_service import AdminDashboardService


class FakeRepository:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def _track(self, method: str, server_id: str):
        self.calls.append((method, server_id))

    def get_release_section(self, *, server_id: str):
        self._track("release", server_id)
        return {
            "fallback_to_legacy_usage": 2,
            "new_domain_usage": 10,
            "rollback_history": [{"id": 1}],
            "warning_signals": [{"event_type": "rollout_error_rate", "total": 3}],
        }

    def get_generation_law_qa_section(self, *, server_id: str):
        self._track("generation_law_qa", server_id)
        return {"generation_totals": 12}

    def get_jobs_section(self, *, server_id: str):
        self._track("jobs", server_id)
        return {"job_statuses": [{"status": "queued", "total": 2}]}

    def get_validation_section(self, *, server_id: str):
        self._track("validation", server_id)
        return {"validation_runs": 4}

    def get_content_section(self, *, server_id: str):
        self._track("content", server_id)
        return {"workflow_breakdown": [{"status": "draft", "total": 7}]}

    def get_integrity_section(self, *, server_id: str):
        self._track("integrity", server_id)
        return {
            "orphan_broken_entities": 0,
            "versions_without_snapshot_or_citations": 1,
            "exports_without_artifact": 0,
            "attachments_not_finalized": 0,
            "cross_server_alerts": 0,
        }

    def get_synthetic_section(self, *, server_id: str):
        self._track("synthetic", server_id)
        return {
            "last_smoke_run": {"status_code": 200},
            "last_nightly_run": {"status_code": 200},
            "failed_scenarios": [{"id": "s1"}],
        }


def test_dashboard_aggregation_contains_all_sections():
    service = AdminDashboardService(FakeRepository())
    payload = service.get_dashboard(username="admin", server_id="blackberry")

    assert set(payload.keys()) == {"release", "generation_law_qa", "jobs", "validation", "content", "integrity", "synthetic"}
    assert isinstance(payload["release"]["feature_flags"], list)


def test_dashboard_scope_filtering_uses_user_server_scope():
    repository = FakeRepository()
    service = AdminDashboardService(repository)

    service.get_dashboard(username="admin", server_id="blackberry")

    assert repository.calls
    assert {server_id for _, server_id in repository.calls} == {"blackberry"}


def test_integrity_signal_status_is_derived_from_counts():
    service = AdminDashboardService(FakeRepository())

    section = service.get_section(section="integrity", username="admin", server_id="blackberry")

    assert section["status"] == "warn"
    assert section["versions_without_snapshot_or_citations"] == 1


def test_synthetic_section_status_is_exposed():
    service = AdminDashboardService(FakeRepository())

    section = service.get_section(section="synthetic", username="admin", server_id="blackberry")

    assert section["status"] == "warn"
    assert len(section["failed_scenarios"]) == 1
