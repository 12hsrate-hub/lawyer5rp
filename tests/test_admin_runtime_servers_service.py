from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_config_debt_summary,
    build_runtime_config_posture_summary,
    build_runtime_resolution_policy_summary,
    build_runtime_server_health_payload,
    create_runtime_server_payload,
    list_runtime_servers_payload,
    set_runtime_server_active_payload,
    update_runtime_server_payload,
)
from ogp_web.services.admin_server_laws_workspace_service import (
    build_activation_gap_summary,
    build_bridge_shrink_checklist_summary,
    build_cutover_blockers_breakdown_summary,
    build_cutover_readiness_summary,
    build_promotion_blockers_summary,
    build_promotion_review_signal_summary,
    build_runtime_bridge_policy_summary,
    build_runtime_operating_mode_summary,
    build_runtime_policy_violations_summary,
    build_runtime_cutover_mode_summary,
    build_runtime_convergence_summary,
    build_cutover_guardrails_summary,
)
from ogp_web.services.law_version_service import ResolvedLawVersion
from tests.second_server_fixtures import orange_published_pack


class _FakeRuntimeServersStore:
    class _Record:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def __init__(self):
        self.rows = {
            "blackberry": {
                "code": "blackberry",
                "title": "BlackBerry",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        }

    @staticmethod
    def to_payload(record):
        return dict(record.__dict__)

    def list_servers(self):
        return [self._Record(**value) for _, value in sorted(self.rows.items())]

    def get_server(self, *, code: str):
        row = self.rows.get(code)
        return self._Record(**row) if row else None

    def create_server(self, *, code: str, title: str):
        row = {"code": code, "title": title, "is_active": False, "created_at": "2026-04-14T00:00:00+00:00"}
        self.rows[code] = row
        return self._Record(**row)

    def update_server(self, *, code: str, title: str):
        self.rows[code]["title"] = title
        return self._Record(**self.rows[code])

    def set_active(self, *, code: str, is_active: bool):
        self.rows[code]["is_active"] = bool(is_active)
        return self._Record(**self.rows[code])


class _FakeRuntimeLawSetsStore:
    def list_law_sets(self, *, server_code: str):
        return [{"id": 1, "server_code": server_code, "name": "Default", "is_active": True, "is_published": True}]

    def list_server_law_bindings(self, *, server_code: str):
        return [{"law_set_id": 1, "law_code": "uk"}]


class _FakeProjectionRun:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeProjectionsStore:
    def list_runs(self, *, server_code: str):
        if server_code != "orange":
            return []
        return [
            _FakeProjectionRun(
                id=4,
                server_code="orange",
                trigger_mode="manual",
                status="approved",
                summary_json={
                    "decision_status": "approved",
                    "materialization": {"law_set_id": 2},
                    "activation": {"law_version_id": 88},
                },
                created_at="2026-04-16T06:00:00+00:00",
            )
        ]


def test_runtime_server_payload_helpers_cover_crud_shape():
    store = _FakeRuntimeServersStore()
    law_sets_store = _FakeRuntimeLawSetsStore()

    listed = list_runtime_servers_payload(store=store, law_sets_store=law_sets_store, projections_store=_FakeProjectionsStore())
    created = create_runtime_server_payload(store=store, law_sets_store=law_sets_store, code="city2", title="City 2")
    updated = update_runtime_server_payload(store=store, law_sets_store=law_sets_store, code="city2", title="City 2 RU")
    deactivated = set_runtime_server_active_payload(store=store, law_sets_store=law_sets_store, code="city2", is_active=False)

    assert listed["count"] == 1
    assert listed["items"][0]["onboarding"]["highest_completed_state"] == "workflow-ready"
    assert created["item"]["code"] == "city2"
    assert created["item"]["is_active"] is False
    assert created["item"]["onboarding"]["highest_completed_state"] == "not-ready"
    assert created["item"]["onboarding"]["resolution_mode"] == "neutral_fallback"
    assert created["item"]["onboarding"]["requires_explicit_runtime_pack"] is True
    assert created["item"]["projection_bridge"] is None
    assert updated["item"]["title"] == "City 2 RU"
    assert deactivated["item"]["is_active"] is False


def test_runtime_server_list_payload_exposes_projection_bridge_summary_without_health_match():
    store = _FakeRuntimeServersStore()
    store.rows["orange"] = {
        "code": "orange",
        "title": "Orange City",
        "is_active": True,
        "created_at": "2026-04-16T00:00:00+00:00",
    }
    listed = list_runtime_servers_payload(
        store=store,
        law_sets_store=_FakeRuntimeLawSetsStore(),
        projections_store=_FakeProjectionsStore(),
    )

    orange_item = next(item for item in listed["items"] if item["code"] == "orange")
    assert orange_item["projection_bridge"]["run_id"] == 4
    assert orange_item["projection_bridge"]["law_set_id"] == 2
    assert orange_item["projection_bridge"]["law_version_id"] == 88
    assert orange_item["projection_bridge"]["matches_active_law_version"] is None


def test_build_runtime_server_health_payload_reports_ready_state(monkeypatch):
    monkeypatch.setattr(
        "ogp_web.services.admin_runtime_servers_service.resolve_active_law_version",
        lambda *, server_code: ResolvedLawVersion(
            id=77,
            server_code=server_code,
            generated_at_utc="2026-04-14T00:00:00+00:00",
            effective_from="2026-04-14",
            effective_to="",
            fingerprint="fp",
            chunk_count=12,
        ),
    )
    monkeypatch.setattr(
        "ogp_web.services.admin_runtime_servers_service.load_law_bundle_meta",
        lambda server_code: type("BundleMeta", (), {"chunk_count": 12})(),
    )

    payload = build_runtime_server_health_payload(
        server_code="blackberry",
        runtime_servers_store=_FakeRuntimeServersStore(),
        law_sets_store=_FakeRuntimeLawSetsStore(),
    )

    assert payload["summary"]["is_ready"] is True
    assert payload["summary"]["ready_count"] == payload["summary"]["total_count"]
    assert payload["checks"]["health"]["active_law_version_id"] == 77
    assert payload["checks"]["config_resolution"]["ok"] is True
    assert payload["runtime_provenance"]["mode"] == "legacy_runtime_shell"
    assert payload["runtime_provenance"]["is_projection_backed"] is False
    assert payload["runtime_alignment"]["status"] == "legacy_only"
    assert payload["runtime_alignment"]["active_law_set_id"] == 1
    assert payload["runtime_alignment"]["active_law_version_id"] == 77
    assert payload["onboarding"]["highest_completed_state"] == "rollout-ready"
    assert payload["onboarding"]["next_required_state"] == "production-ready"


def test_second_server_published_pack_health_payload_reports_release_candidate_state(monkeypatch):
    store = _FakeRuntimeServersStore()
    store.rows["orange"] = {
        "code": "orange",
        "title": "Orange City",
        "is_active": True,
        "created_at": "2026-04-16T00:00:00+00:00",
    }

    class OrangeLawSetsStore:
        def list_law_sets(self, *, server_code: str):
            if server_code == "orange":
                return [{"id": 2, "server_code": "orange", "name": "Orange Draft", "is_active": True, "is_published": True}]
            return [{"id": 1, "server_code": server_code, "name": "Default", "is_active": True, "is_published": True}]

        def list_server_law_bindings(self, *, server_code: str):
            if server_code == "orange":
                return [{"law_set_id": 2, "law_code": "orange_code"}]
            return [{"law_set_id": 1, "law_code": "uk"}]

    monkeypatch.setattr(
        "ogp_web.services.admin_runtime_servers_service.resolve_active_law_version",
        lambda *, server_code: ResolvedLawVersion(
            id=88,
            server_code=server_code,
            generated_at_utc="2026-04-16T00:00:00+00:00",
            effective_from="2026-04-16",
            effective_to="",
            fingerprint="orange-fp",
            chunk_count=9,
        ),
    )
    monkeypatch.setattr(
        "ogp_web.services.admin_runtime_servers_service.load_law_bundle_meta",
        lambda server_code: type("BundleMeta", (), {"chunk_count": 9})(),
    )
    monkeypatch.setattr(
        "ogp_web.server_config.registry._load_effective_pack_from_db",
        lambda *, server_code, at_timestamp=None: orange_published_pack() if server_code == "orange" else None,
    )

    payload = build_runtime_server_health_payload(
        server_code="orange",
        runtime_servers_store=store,
        law_sets_store=OrangeLawSetsStore(),
        projections_store=_FakeProjectionsStore(),
    )

    assert payload["summary"]["is_ready"] is True
    assert payload["onboarding"]["resolution_mode"] == "published_pack"
    assert payload["onboarding"]["uses_transitional_fallback"] is False
    assert payload["checks"]["config_resolution"]["ok"] is True
    assert payload["runtime_provenance"]["mode"] == "projection_backed"
    assert payload["runtime_provenance"]["is_projection_backed"] is True
    assert payload["runtime_alignment"]["status"] == "aligned"
    assert payload["runtime_alignment"]["matches_active_law_set"] is True
    assert payload["runtime_alignment"]["matches_active_law_version"] is True
    assert payload["onboarding"]["highest_completed_state"] == "rollout-ready"
    assert payload["checks"]["health"]["active_law_version_id"] == 88
    assert payload["projection_bridge"]["run_id"] == 4
    assert payload["projection_bridge"]["law_set_id"] == 2
    assert payload["projection_bridge"]["law_version_id"] == 88
    assert payload["projection_bridge"]["matches_active_law_version"] is True


def test_runtime_config_posture_and_debt_distinguish_published_bootstrap_and_fallback():
    fallback_health = {
        "onboarding": {
            "resolution_mode": "neutral_fallback",
            "highest_completed_state": "not-ready",
            "next_required_state": "bootstrap-ready",
            "requires_explicit_runtime_pack": True,
        },
        "checks": {
            "config_resolution": {
                "resolution_mode": "neutral_fallback",
                "requires_explicit_runtime_pack": True,
            }
        },
    }
    bootstrap_health = {
        "onboarding": {
            "resolution_mode": "bootstrap_pack",
            "highest_completed_state": "workflow-ready",
            "next_required_state": "rollout-ready",
            "requires_explicit_runtime_pack": False,
        },
        "checks": {
            "config_resolution": {
                "resolution_mode": "bootstrap_pack",
                "requires_explicit_runtime_pack": False,
            }
        },
    }
    published_health = {
        "onboarding": {
            "resolution_mode": "published_pack",
            "highest_completed_state": "rollout-ready",
            "next_required_state": "production-ready",
            "requires_explicit_runtime_pack": False,
        },
        "checks": {
            "config_resolution": {
                "resolution_mode": "published_pack",
                "requires_explicit_runtime_pack": False,
            }
        },
    }

    assert build_runtime_config_posture_summary(health_payload=fallback_health)["status"] == "fallback_only"
    assert build_runtime_config_debt_summary(health_payload=fallback_health)["status"] == "high"
    assert build_runtime_config_posture_summary(health_payload=bootstrap_health)["status"] == "bootstrap_transition"
    assert build_runtime_config_debt_summary(health_payload=bootstrap_health)["status"] == "medium"
    assert build_runtime_resolution_policy_summary(health_payload=bootstrap_health)["status"] == "transitional_bootstrap"
    assert build_runtime_config_posture_summary(health_payload=published_health)["status"] == "declared_ready"
    assert build_runtime_config_debt_summary(health_payload=published_health)["status"] == "low"
    assert build_runtime_resolution_policy_summary(health_payload=published_health)["status"] == "declared_runtime"
    assert build_runtime_resolution_policy_summary(health_payload=fallback_health)["status"] == "compatibility_exception"


def test_advisory_review_delta_does_not_block_runtime_convergence_or_cutover():
    promotion_blockers = build_promotion_blockers_summary(
        projection_bridge_readiness={"status": "ready", "detail": "Bridge readiness signals are green.", "blockers": [], "next_step": ""},
        promotion_candidate={"status": "review_needed", "detail": "Latest projection candidate differs from the previous baseline and should be reviewed.", "next_step": "Проверьте diff и подтвердите, что изменения ожидаемы."},
        promotion_delta={"status": "attention", "detail": "Latest projection candidate has changes or content gaps that deserve review."},
        runtime_item_parity={"status": "aligned", "detail": "Aligned."},
        runtime_version_parity={"status": "aligned", "detail": "Aligned."},
        projection_bridge_lifecycle={"status": "activated", "detail": "Activated."},
    )
    assert promotion_blockers["status"] == "review"

    promotion_review_signal = build_promotion_review_signal_summary(
        promotion_candidate={"status": "review_needed", "detail": "Latest projection candidate differs from the previous baseline and should be reviewed.", "next_step": "Проверьте diff и подтвердите, что изменения ожидаемы.", "counts": {"selected_count": 1, "changed": 1}},
        promotion_delta={"status": "attention", "detail": "Latest projection candidate has changes or content gaps that deserve review.", "counts": {"added": 1, "removed": 0, "changed": 1, "missing_content": 0, "error_count": 0}},
        promotion_blockers=promotion_blockers,
    )
    assert promotion_review_signal["status"] == "review"
    assert promotion_review_signal["counts"]["advisory_count"] == 2

    activation_gap = build_activation_gap_summary(
        projection_bridge_readiness={"status": "ready", "detail": "Bridge readiness signals are green.", "blockers": [], "next_step": ""},
        runtime_version_parity={"status": "aligned", "detail": "Aligned.", "active_law_version_id": 247, "projected_law_version_id": 247},
        projection_bridge_lifecycle={"status": "activated", "detail": "Activated."},
        promotion_blockers=promotion_blockers,
    )
    assert activation_gap["status"] == "closed"

    runtime_shell_debt = {"status": "low", "detail": "Runtime shell debt looks low in the current read model.", "next_step": ""}
    runtime_convergence = build_runtime_convergence_summary(
        promotion_blockers=promotion_blockers,
        activation_gap=activation_gap,
        runtime_shell_debt=runtime_shell_debt,
    )
    assert runtime_convergence["status"] == "converged"

    cutover_readiness = build_cutover_readiness_summary(
        projection_bridge_readiness={"status": "ready", "detail": "Bridge readiness signals are green.", "blockers": [], "next_step": ""},
        runtime_convergence=runtime_convergence,
        runtime_shell_debt=runtime_shell_debt,
        activation_gap=activation_gap,
    )
    assert cutover_readiness["status"] == "ready_for_cutover"

    bridge_shrink_checklist = build_bridge_shrink_checklist_summary(
        projection_bridge_readiness={"status": "ready", "detail": "Bridge readiness signals are green.", "blockers": [], "next_step": ""},
        activation_gap=activation_gap,
        runtime_shell_debt=runtime_shell_debt,
        runtime_convergence=runtime_convergence,
        cutover_readiness=cutover_readiness,
    )
    assert bridge_shrink_checklist["status"] == "ready"

    cutover_blockers_breakdown = build_cutover_blockers_breakdown_summary(
        promotion_blockers=promotion_blockers,
        runtime_shell_debt=runtime_shell_debt,
        activation_gap=activation_gap,
        cutover_readiness=cutover_readiness,
    )
    assert cutover_blockers_breakdown["status"] == "clear"

    runtime_cutover_mode = build_runtime_cutover_mode_summary(
        cutover_readiness=cutover_readiness,
        runtime_convergence=runtime_convergence,
        runtime_shell_debt=runtime_shell_debt,
        runtime_config_debt={"status": "low", "detail": "Low.", "next_step": ""},
    )
    assert runtime_cutover_mode["status"] == "projection_preferred"
    runtime_bridge_policy = build_runtime_bridge_policy_summary(
        runtime_resolution_policy={"status": "declared_runtime", "detail": "", "next_step": ""},
        runtime_cutover_mode=runtime_cutover_mode,
        cutover_readiness=cutover_readiness,
    )
    assert runtime_bridge_policy["status"] == "prefer_projection_runtime"
    runtime_operating_mode = build_runtime_operating_mode_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_config_posture={"status": "declared_ready", "detail": "", "next_step": ""},
        runtime_provenance={"mode": "projection_backed", "detail": ""},
        runtime_cutover_mode=runtime_cutover_mode,
    )
    assert runtime_operating_mode["status"] == "projection_runtime"
    runtime_policy_violations = build_runtime_policy_violations_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_config_posture={"status": "declared_ready", "detail": "", "next_step": ""},
        runtime_provenance={"mode": "projection_backed", "detail": ""},
        runtime_shell_debt=runtime_shell_debt,
        cutover_readiness=cutover_readiness,
    )
    assert runtime_policy_violations["status"] == "clear"
    cutover_guardrails = build_cutover_guardrails_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_policy_violations=runtime_policy_violations,
        cutover_readiness=cutover_readiness,
    )
    assert cutover_guardrails["status"] == "enforced"
    assert build_runtime_bridge_policy_summary(
        runtime_resolution_policy={"status": "compatibility_exception", "detail": "", "next_step": ""},
        runtime_cutover_mode={"status": "compatibility_mode", "detail": "", "next_step": ""},
        cutover_readiness={"status": "needs_activation_alignment", "detail": "", "next_step": ""},
    )["status"] == "keep_compatibility"
