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
        row = {"code": code, "title": title, "is_active": True, "created_at": "2026-04-14T00:00:00+00:00"}
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


def test_runtime_server_payload_helpers_cover_crud_shape():
    store = _FakeRuntimeServersStore()
    law_sets_store = _FakeRuntimeLawSetsStore()

    listed = list_runtime_servers_payload(store=store, law_sets_store=law_sets_store)
    created = create_runtime_server_payload(store=store, law_sets_store=law_sets_store, code="city2", title="City 2")
    updated = update_runtime_server_payload(store=store, law_sets_store=law_sets_store, code="city2", title="City 2 RU")
    deactivated = set_runtime_server_active_payload(store=store, law_sets_store=law_sets_store, code="city2", is_active=False)

    assert listed["count"] == 1
    assert listed["items"][0]["onboarding"]["highest_completed_state"] == "workflow-ready"
    assert created["item"]["code"] == "city2"
    assert created["item"]["onboarding"]["highest_completed_state"] == "not-ready"
    assert created["item"]["onboarding"]["resolution_mode"] == "neutral_fallback"
    assert updated["item"]["title"] == "City 2 RU"
    assert deactivated["item"]["is_active"] is False


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
    assert payload["onboarding"]["highest_completed_state"] == "rollout-ready"
    assert payload["onboarding"]["next_required_state"] == "production-ready"
