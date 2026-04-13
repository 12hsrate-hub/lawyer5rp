from __future__ import annotations

from typing import Any

from ogp_web.services.feature_flags import FEATURE_FLAGS, FeatureFlagService, RolloutContext
from ogp_web.storage.admin_dashboard_repository import AdminDashboardRepository


class AdminDashboardService:
    def __init__(self, repository: AdminDashboardRepository, flag_service: FeatureFlagService | None = None):
        self.repository = repository
        self.flag_service = flag_service or FeatureFlagService()

    def _release_flags(self, *, username: str, server_id: str) -> list[dict[str, Any]]:
        context = RolloutContext(username=username, server_id=server_id)
        payload: list[dict[str, Any]] = []
        for flag in FEATURE_FLAGS:
            decision = self.flag_service.evaluate(flag=flag, context=context)
            payload.append(
                {
                    "flag": flag,
                    "mode": decision.mode.value,
                    "cohort": decision.cohort.value,
                    "use_new_flow": bool(decision.use_new_flow),
                    "enforcement": decision.enforcement.value,
                }
            )
        return payload

    @staticmethod
    def _integrity_status(section: dict[str, Any]) -> str:
        total = sum(
            int(section.get(key) or 0)
            for key in (
                "orphan_broken_entities",
                "versions_without_snapshot_or_citations",
                "exports_without_artifact",
                "attachments_not_finalized",
                "cross_server_alerts",
            )
        )
        if total == 0:
            return "ok"
        if total < 10:
            return "warn"
        return "critical"

    @staticmethod
    def _synthetic_status(section: dict[str, Any]) -> str:
        failures = list(section.get("failed_scenarios") or [])
        if not failures:
            return "ok"
        if len(failures) < 3:
            return "warn"
        return "critical"

    def get_dashboard(self, *, username: str, server_id: str) -> dict[str, Any]:
        release = self.repository.get_release_section(server_id=server_id)
        release["feature_flags"] = self._release_flags(username=username, server_id=server_id)

        integrity = self.repository.get_integrity_section(server_id=server_id)
        integrity["status"] = self._integrity_status(integrity)

        synthetic = self.repository.get_synthetic_section(server_id=server_id)
        synthetic["status"] = self._synthetic_status(synthetic)

        return {
            "release": release,
            "generation_law_qa": self.repository.get_generation_law_qa_section(server_id=server_id),
            "jobs": self.repository.get_jobs_section(server_id=server_id),
            "validation": self.repository.get_validation_section(server_id=server_id),
            "content": self.repository.get_content_section(server_id=server_id),
            "integrity": integrity,
            "synthetic": synthetic,
        }

    def get_section(self, *, section: str, username: str, server_id: str) -> dict[str, Any]:
        payload = self.get_dashboard(username=username, server_id=server_id)
        if section not in payload:
            raise KeyError(section)
        return payload[section]
