from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_server_health_payload,
    create_runtime_server_payload,
    list_runtime_servers_payload,
    set_runtime_server_active_payload,
    update_runtime_server_payload,
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
    assert payload["onboarding"]["highest_completed_state"] == "rollout-ready"
    assert payload["checks"]["health"]["active_law_version_id"] == 88
    assert payload["projection_bridge"]["run_id"] == 4
    assert payload["projection_bridge"]["law_set_id"] == 2
    assert payload["projection_bridge"]["law_version_id"] == 88
    assert payload["projection_bridge"]["matches_active_law_version"] is True
