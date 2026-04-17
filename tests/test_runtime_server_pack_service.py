from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.runtime_server_pack_service import (
    build_runtime_server_pack_publish_blockers_payload,
    publish_runtime_server_pack_payload,
    rollback_runtime_server_pack_payload,
)


class _Server:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Pack:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _RuntimeServersStore:
    backend = None

    def get_server(self, *, code: str):
        if code == "missing":
            return None
        return _Server(code=code, title=code.title(), is_active=True)


class _RuntimeServerPacksStore:
    def __init__(self, *, published=None, draft=None):
        self.published = published
        self.draft = draft

    def get_latest_published_pack(self, *, server_code: str):
        _ = server_code
        return self.published

    def get_latest_draft_pack(self, *, server_code: str):
        _ = server_code
        return self.draft

    def get_previous_published_pack(self, *, server_code: str):
        _ = server_code
        return None

    def get_published_pack_by_version(self, *, server_code: str, version: int):
        _ = (server_code, version)
        return self.published

    def save_draft_pack(self, *, server_code: str, metadata_json):
        self.draft = _Pack(
            id=10,
            server_code=server_code,
            version=int(getattr(self.published, "version", 0) or 0) + 1,
            status="draft",
            metadata_json=dict(metadata_json or {}),
            created_at="2026-04-17T00:00:00+00:00",
            published_at="",
        )
        return self.draft

    def publish_latest_draft_pack(self, *, server_code: str):
        _ = server_code
        if self.draft is None:
            raise KeyError("server_pack_draft_not_found")
        published = _Pack(**{**self.draft.__dict__, "status": "published", "published_at": "2026-04-17T01:00:00+00:00"})
        self.published = published
        self.draft = None
        return published

    def rollback_to_published_pack(self, *, server_code: str, target_version=None):
        _ = (server_code, target_version)
        if self.published is None:
            raise KeyError("server_pack_published_not_found")
        rolled_back = _Pack(
            id=11,
            server_code=self.published.server_code,
            version=int(self.published.version) + 1,
            status="published",
            metadata_json=dict(self.published.metadata_json or {}),
            created_at="2026-04-17T02:00:00+00:00",
            published_at="2026-04-17T02:00:00+00:00",
        )
        self.published = rolled_back
        return rolled_back

    @staticmethod
    def to_payload(record):
        if record is None:
            return None
        return {
            "id": record.id,
            "server_code": record.server_code,
            "version": record.version,
            "status": record.status,
            "metadata": dict(record.metadata_json or {}),
            "created_at": record.created_at,
            "published_at": record.published_at or None,
        }


class _WorkflowService:
    pass


class _UserStore:
    pass


class _LawSetsStore:
    pass


class _SourceSetsStore:
    pass


class _ProjectionsStore:
    pass


def test_runtime_server_pack_publish_blockers_include_law_readiness(monkeypatch):
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_resolution_snapshot",
        lambda *, server_code, title: {
            "server_code": server_code,
            "resolution_mode": "bootstrap_pack",
            "resolution_label": "bootstrap pack",
            "pack": {},
            "pack_metadata": {
                "organizations": ["GOV"],
                "template_bindings": {
                    "complaint": {"template_key": "complaint_v1"},
                    "court_claim": {"template_key": "court_claim_bbcode_v1"},
                },
                "validation_profiles": {
                    "complaint_default": {"required_sections": ["incident"]},
                    "court_claim_default": {},
                },
                "law_qa_sources": ["https://example.com/law"],
            },
        },
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_features_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_templates_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint_template"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_server_access_summary_payload",
        lambda **kwargs: {"summary": {"counts": {"active_users": 1, "assignments": 0}}},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_server_health_payload",
        lambda **kwargs: {
            "checks": {"bindings": {"count": 1}},
            "law_context_readiness": {
                "status": "blocked",
                "reason_code": "no_projection",
                "reason_detail": "Projection bridge is missing.",
            },
        },
    )

    payload = build_runtime_server_pack_publish_blockers_payload(
        server_code="blackberry",
        runtime_servers_store=_RuntimeServersStore(),
        runtime_server_packs_store=_RuntimeServerPacksStore(),
        law_sets_store=_LawSetsStore(),
        source_sets_store=_SourceSetsStore(),
        projections_store=_ProjectionsStore(),
        workflow_service=_WorkflowService(),
        user_store=_UserStore(),
    )

    assert payload["status"] == "blocked"
    assert any(item["code"] == "no_projection" for item in payload["items"])
    assert payload["candidate_runtime_requirements"]["blocked_count"] == 1
    assert payload["candidate_runtime_requirements"]["items"][2]["section_code"] == "law_qa"


def test_runtime_server_pack_publish_blockers_simulate_published_runtime_for_staged_cutover(monkeypatch):
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_resolution_snapshot",
        lambda *, server_code, title: {
            "server_code": server_code,
            "resolution_mode": "bootstrap_pack",
            "resolution_label": "bootstrap pack",
            "pack": {},
            "pack_metadata": {
                "organizations": ["GOV"],
                "template_bindings": {
                    "complaint": {"template_key": "complaint_v1"},
                    "court_claim": {"template_key": "court_claim_bbcode_v1"},
                },
                "validation_profiles": {
                    "complaint_default": {"required_sections": ["incident"]},
                    "court_claim_default": {},
                },
            },
        },
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_features_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_templates_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint_template"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_server_access_summary_payload",
        lambda **kwargs: {"summary": {"counts": {"active_users": 1, "assignments": 0}}},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_server_health_payload",
        lambda **kwargs: {
            "checks": {"bindings": {"count": 0}},
            "law_context_readiness": {
                "status": "ready",
                "reason_code": "ready",
                "reason_detail": "Ready.",
            },
        },
    )

    with patch.dict(os.environ, {"OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS": "complaint,court_claim"}, clear=False):
        payload = build_runtime_server_pack_publish_blockers_payload(
            server_code="blackberry",
            runtime_servers_store=_RuntimeServersStore(),
            runtime_server_packs_store=_RuntimeServerPacksStore(),
            law_sets_store=_LawSetsStore(),
            source_sets_store=_SourceSetsStore(),
            projections_store=_ProjectionsStore(),
            workflow_service=_WorkflowService(),
            user_store=_UserStore(),
        )

    assert payload["status"] == "ready"
    assert payload["can_publish"] is True
    assert payload["candidate_runtime_requirements"]["status"] == "ready"
    assert payload["candidate_runtime_requirements"]["blocked_count"] == 0


def test_runtime_server_pack_publish_promotes_compiled_candidate(monkeypatch):
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_resolution_snapshot",
        lambda *, server_code, title: {
            "server_code": server_code,
            "resolution_mode": "published_pack",
            "resolution_label": "published pack",
            "pack": {"id": 2, "version": 3},
            "pack_metadata": {
                "organizations": ["GOV"],
                "template_bindings": {
                    "complaint": {"template_key": "complaint_v1"},
                    "court_claim": {"template_key": "court_claim_bbcode_v1"},
                },
                "validation_profiles": {
                    "complaint_default": {"required_sections": ["incident"]},
                    "court_claim_default": {},
                },
                "law_qa_sources": ["https://example.com/law"],
            },
        },
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_features_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_templates_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint_template"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_server_access_summary_payload",
        lambda **kwargs: {"summary": {"counts": {"active_users": 1, "assignments": 0}}},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_server_health_payload",
        lambda **kwargs: {
            "checks": {"bindings": {"count": 1}},
            "law_context_readiness": {
                "status": "ready",
                "reason_code": "ready",
                "reason_detail": "Ready.",
                "projection": {"run_id": 7},
            },
        },
    )

    packs_store = _RuntimeServerPacksStore()
    result = publish_runtime_server_pack_payload(
        server_code="orange",
        runtime_servers_store=_RuntimeServersStore(),
        runtime_server_packs_store=packs_store,
        law_sets_store=_LawSetsStore(),
        source_sets_store=_SourceSetsStore(),
        projections_store=_ProjectionsStore(),
        workflow_service=_WorkflowService(),
        user_store=_UserStore(),
    )

    assert result["changed"] is True
    assert result["published_pack"]["status"] == "published"
    assert result["published_pack"]["metadata"]["runtime_pack_compiler"]["law_context"]["status"] == "ready"


def test_runtime_server_pack_publish_blockers_require_explicit_court_claim_bindings(monkeypatch):
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_resolution_snapshot",
        lambda *, server_code, title: {
            "server_code": server_code,
            "resolution_mode": "published_pack",
            "resolution_label": "published pack",
            "pack": {"id": 2, "version": 3},
            "pack_metadata": {
                "organizations": ["GOV"],
                "template_bindings": {"complaint": {"template_key": "complaint_v1"}},
                "validation_profiles": {"complaint_default": {"required_sections": ["incident"]}},
            },
        },
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_features_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_templates_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint_template"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_server_access_summary_payload",
        lambda **kwargs: {"summary": {"counts": {"active_users": 1, "assignments": 0}}},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_server_health_payload",
        lambda **kwargs: {
            "checks": {"bindings": {"count": 0}},
            "law_context_readiness": {"status": "ready", "reason_code": "ready", "reason_detail": "Ready."},
        },
    )

    payload = build_runtime_server_pack_publish_blockers_payload(
        server_code="blackberry",
        runtime_servers_store=_RuntimeServersStore(),
        runtime_server_packs_store=_RuntimeServerPacksStore(),
        law_sets_store=_LawSetsStore(),
        source_sets_store=_SourceSetsStore(),
        projections_store=_ProjectionsStore(),
        workflow_service=_WorkflowService(),
        user_store=_UserStore(),
    )

    assert payload["status"] == "blocked"
    assert any(item["code"] == "runtime_requirement:court_claim" for item in payload["items"])
    court_claim_item = next(
        item for item in payload["candidate_runtime_requirements"]["items"] if item["section_code"] == "court_claim"
    )
    assert court_claim_item["route_status"] == "blocked"
    assert court_claim_item["route_reason_code"] == "court_claim_template_binding_missing"


def test_runtime_server_pack_publish_blockers_require_explicit_complaint_bindings(monkeypatch):
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_resolution_snapshot",
        lambda *, server_code, title: {
            "server_code": server_code,
            "resolution_mode": "published_pack",
            "resolution_label": "published pack",
            "pack": {"id": 2, "version": 3},
            "pack_metadata": {
                "organizations": ["GOV"],
                "template_bindings": {"court_claim": {"template_key": "court_claim_bbcode_v1"}},
                "validation_profiles": {"court_claim_default": {}},
            },
        },
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_features_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_templates_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint_template"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_server_access_summary_payload",
        lambda **kwargs: {"summary": {"counts": {"active_users": 1, "assignments": 0}}},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_server_health_payload",
        lambda **kwargs: {
            "checks": {"bindings": {"count": 0}},
            "law_context_readiness": {"status": "ready", "reason_code": "ready", "reason_detail": "Ready."},
        },
    )

    payload = build_runtime_server_pack_publish_blockers_payload(
        server_code="blackberry",
        runtime_servers_store=_RuntimeServersStore(),
        runtime_server_packs_store=_RuntimeServerPacksStore(),
        law_sets_store=_LawSetsStore(),
        source_sets_store=_SourceSetsStore(),
        projections_store=_ProjectionsStore(),
        workflow_service=_WorkflowService(),
        user_store=_UserStore(),
    )

    assert payload["status"] == "blocked"
    assert any(item["code"] == "runtime_requirement:complaint" for item in payload["items"])
    complaint_item = next(
        item for item in payload["candidate_runtime_requirements"]["items"] if item["section_code"] == "complaint"
    )
    assert complaint_item["route_status"] == "blocked"
    assert complaint_item["route_reason_code"] == "complaint_template_binding_missing"


def test_runtime_server_pack_publish_blockers_include_candidate_runtime_requirement_failures(monkeypatch):
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_resolution_snapshot",
        lambda *, server_code, title: {
            "server_code": server_code,
            "resolution_mode": "published_pack",
            "resolution_label": "published pack",
            "pack": {"id": 2, "version": 3},
            "pack_metadata": {
                "organizations": ["GOV"],
                "template_bindings": {
                    "complaint": {"template_key": "complaint_v1"},
                    "court_claim": {"template_key": "court_claim_bbcode_v1"},
                },
                "validation_profiles": {
                    "complaint_default": {"required_sections": ["incident"]},
                    "court_claim_default": {},
                },
                "law_qa_sources": ["https://example.com/law"],
            },
        },
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_features_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_templates_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint_template"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_server_access_summary_payload",
        lambda **kwargs: {"summary": {"counts": {"active_users": 1, "assignments": 0}}},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_server_health_payload",
        lambda **kwargs: {
            "checks": {"bindings": {"count": 1}},
            "law_context_readiness": {
                "status": "blocked",
                "reason_code": "no_projection",
                "reason_detail": "Projection bridge is missing.",
            },
        },
    )

    payload = build_runtime_server_pack_publish_blockers_payload(
        server_code="orange",
        runtime_servers_store=_RuntimeServersStore(),
        runtime_server_packs_store=_RuntimeServerPacksStore(),
        law_sets_store=_LawSetsStore(),
        source_sets_store=_SourceSetsStore(),
        projections_store=_ProjectionsStore(),
        workflow_service=_WorkflowService(),
        user_store=_UserStore(),
    )

    assert payload["status"] == "blocked"
    assert any(item["code"] == "runtime_requirement:law_qa" for item in payload["items"])
    assert payload["candidate_runtime_requirements"]["blocked_count"] == 1


def test_runtime_server_pack_rollback_promotes_previous_metadata_as_new_published_fact(monkeypatch):
    current = _Pack(
        id=7,
        server_code="orange",
        version=3,
        status="published",
        metadata_json={"organizations": ["GOV", "LSPD"]},
        created_at="2026-04-17T00:00:00+00:00",
        published_at="2026-04-17T00:00:00+00:00",
    )
    target = _Pack(
        id=6,
        server_code="orange",
        version=2,
        status="published",
        metadata_json={"organizations": ["GOV"]},
        created_at="2026-04-16T00:00:00+00:00",
        published_at="2026-04-16T00:00:00+00:00",
    )
    packs_store = _RuntimeServerPacksStore(published=current)
    packs_store.get_previous_published_pack = lambda *, server_code: target
    packs_store.rollback_to_published_pack = lambda *, server_code, target_version=None: _Pack(
        id=8,
        server_code=server_code,
        version=4,
        status="published",
        metadata_json=dict(target.metadata_json),
        created_at="2026-04-17T03:00:00+00:00",
        published_at="2026-04-17T03:00:00+00:00",
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_resolution_snapshot",
        lambda *, server_code, title: {
            "server_code": server_code,
            "resolution_mode": "published_pack",
            "resolution_label": "published pack",
            "pack": {"id": current.id, "version": current.version},
            "pack_metadata": dict(current.metadata_json),
        },
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_features_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.list_server_templates_payload",
        lambda **kwargs: {"counts": {"effective": 1, "published_effective": 1}, "effective_items": [{"content_key": "complaint_template"}]},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_server_access_summary_payload",
        lambda **kwargs: {"summary": {"counts": {"active_users": 1, "assignments": 0}}},
    )
    monkeypatch.setattr(
        "ogp_web.services.runtime_server_pack_service.build_runtime_server_health_payload",
        lambda **kwargs: {
            "checks": {"bindings": {"count": 0}},
            "law_context_readiness": {"status": "ready", "reason_code": "ready", "reason_detail": "Ready."},
        },
    )

    result = rollback_runtime_server_pack_payload(
        server_code="orange",
        runtime_servers_store=_RuntimeServersStore(),
        runtime_server_packs_store=packs_store,
        law_sets_store=_LawSetsStore(),
        source_sets_store=_SourceSetsStore(),
        projections_store=_ProjectionsStore(),
        workflow_service=_WorkflowService(),
        user_store=_UserStore(),
    )

    assert result["changed"] is True
    assert result["reason"] == "rolled_back"
    assert result["published_pack"]["version"] == 4
    assert result["rollback_target"]["version"] == 2
