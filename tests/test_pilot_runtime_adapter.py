from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.auth_service import AuthUser
from ogp_web.services.complaint_service import build_generation_context_snapshot
from ogp_web.services.pilot_runtime_adapter import (
    PILOT_FORM_CONTENT_KEY,
    PILOT_PROCEDURE_CONTENT_KEY,
    PILOT_TEMPLATE_CONTENT_KEY,
    PILOT_VALIDATION_CONTENT_KEY,
    _resolve_content_version_specs,
    resolve_pilot_complaint_runtime_context,
    supports_pilot_runtime_adapter,
)
from ogp_web.storage.user_repository import UserRepository
from ogp_web.storage.user_store import UserStore
from tests.temp_helpers import make_temporary_directory
from tests.test_web_storage import PostgresBackend


def test_pilot_runtime_adapter_supports_complaint_for_any_explicit_server():
    def fake_read_runtime_pack_snapshot(*, server_code):
        if server_code == "orange":
            return type(
                "Snapshot",
                (),
                {
                    "pack_version": 1,
                    "metadata": {"template_bindings": {"complaint": {"template_key": "complaint_orange_v1"}}},
                },
            )()
        return type(
            "Snapshot",
            (),
            {
                "pack_version": 1,
                "metadata": {"template_bindings": {"complaint": {"template_key": "complaint_v1"}}},
            },
        )()

    from ogp_web.services import pilot_runtime_adapter as adapter_module

    original_reader = adapter_module.read_runtime_pack_snapshot
    adapter_module.read_runtime_pack_snapshot = fake_read_runtime_pack_snapshot
    try:
        assert supports_pilot_runtime_adapter(server_code="blackberry", document_kind="complaint") is True
        assert supports_pilot_runtime_adapter(server_code="orange", document_kind="complaint") is True
        assert supports_pilot_runtime_adapter(server_code="blackberry", document_kind="rehab") is False
        assert supports_pilot_runtime_adapter(server_code="", document_kind="complaint") is False
    finally:
        adapter_module.read_runtime_pack_snapshot = original_reader


def test_pilot_runtime_adapter_requires_explicit_complaint_template_binding(monkeypatch):
    monkeypatch.setattr(
        "ogp_web.services.pilot_runtime_adapter.read_runtime_pack_snapshot",
        lambda *, server_code: type(
            "Snapshot",
            (),
            {
                "pack_version": 1,
                "metadata": {"template_bindings": {"court_claim": {"template_key": "court_claim_orange_v1"}}},
            },
        )(),
    )
    assert supports_pilot_runtime_adapter(server_code="orange", document_kind="complaint") is False

def test_pilot_runtime_adapter_prefers_published_workflow_versions(monkeypatch):
    tmpdir = make_temporary_directory()
    store = None
    try:
        root = Path(tmpdir.name)
        store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(PostgresBackend()),
        )

        def fake_load(repository, *, server_code, content_type, content_key):
            _ = (repository, server_code)
            published = {
                ("procedures", PILOT_PROCEDURE_CONTENT_KEY): {"id": 101, "version_number": 3, "payload_json": {"procedure_code": "complaint", "document_kind": "complaint"}},
                ("forms", PILOT_FORM_CONTENT_KEY): {"id": 102, "version_number": 4, "payload_json": {"form_code": "complaint_form"}},
                ("validation_rules", PILOT_VALIDATION_CONTENT_KEY): {"id": 103, "version_number": 5, "payload_json": {"rule_code": "complaint_default"}},
                ("templates", PILOT_TEMPLATE_CONTENT_KEY): {"id": 104, "version_number": 6, "payload_json": {"template_code": "complaint_v1"}},
            }
            return published.get((content_type, content_key))

        monkeypatch.setattr(
            "ogp_web.services.pilot_runtime_adapter._load_published_content_version",
            fake_load,
        )
        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")
        context = resolve_pilot_complaint_runtime_context(store, user)
        assert context.procedure_version["version"] == "3"
        assert context.template_version["version"] == "6"
        assert "content_item_id" not in context.procedure_version
        assert "status" not in context.template_version
        assert context.feature_flags == ()
        snapshot = context.to_generation_context_snapshot()
        assert "runtime_adapter" not in snapshot
        assert snapshot["content_workflow"]["applied_published_versions"] == snapshot["effective_config_snapshot"]
    finally:
        if store is not None:
            store.repository.close()
        tmpdir.cleanup()


def test_pilot_runtime_adapter_resolves_dynamic_template_binding_from_server_pack():
    specs = _resolve_content_version_specs(
        server_pack_metadata={
            "template_bindings": {
                "complaint": {
                    "template_key": "complaint_orange_v1",
                }
            },
            "validation_profiles": {
                "complaint_default": {},
            },
        }
    )
    assert specs["template"] == ("templates", "complaint_orange_v1")
    assert specs["validation"] == ("validation_rules", "complaint_default")


def test_pilot_runtime_adapter_uses_server_specific_template_binding(monkeypatch):
    tmpdir = make_temporary_directory()
    store = None
    calls: list[tuple[str, str]] = []
    try:
        root = Path(tmpdir.name)
        store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(PostgresBackend()),
        )

        monkeypatch.setattr(
            "ogp_web.services.pilot_runtime_adapter.read_runtime_pack_snapshot",
            lambda *, server_code: type(
                "Snapshot",
                (),
                {
                    "pack_version": 3,
                    "metadata": {
                        "template_bindings": {
                            "complaint": {
                                "template_key": "complaint_orange_v1",
                            }
                        },
                        "validation_profiles": {
                            "complaint_default": {},
                        },
                    },
                },
            )(),
        )

        def fake_load(repository, *, server_code, content_type, content_key):
            _ = repository
            calls.append((content_type, content_key))
            published = {
                ("procedures", PILOT_PROCEDURE_CONTENT_KEY): {"id": 201, "version_number": 1, "payload_json": {"procedure_code": "complaint", "document_kind": "complaint"}},
                ("forms", PILOT_FORM_CONTENT_KEY): {"id": 202, "version_number": 1, "payload_json": {"form_code": "complaint_form"}},
                ("validation_rules", PILOT_VALIDATION_CONTENT_KEY): {"id": 203, "version_number": 1, "payload_json": {"rule_code": "complaint_default"}},
                ("templates", "complaint_orange_v1"): {"id": 204, "version_number": 2, "payload_json": {"template_code": "complaint_orange_v1"}},
                ("laws", "law_sources_manifest"): {"id": 205, "version_number": 1, "payload_json": {"key": "law_sources_manifest"}},
            }
            return published.get((content_type, content_key))

        monkeypatch.setattr(
            "ogp_web.services.pilot_runtime_adapter._load_published_content_version",
            fake_load,
        )
        monkeypatch.setattr(
            "ogp_web.services.pilot_runtime_adapter.load_law_bundle_meta",
            lambda server_code: type("Meta", (), {"fingerprint": "orange_bundle_hash"})(),
        )

        user = AuthUser(username="tester", email="tester@example.com", server_code="orange")
        context = resolve_pilot_complaint_runtime_context(store, user)
        assert context.server_code == "orange"
        assert context.template_version["template_code"] == "complaint_orange_v1"
        assert ("templates", "complaint_orange_v1") in calls
    finally:
        if store is not None:
            store.repository.close()
        tmpdir.cleanup()


def test_legacy_generation_context_snapshot_keeps_content_workflow_in_sync():
    tmpdir = make_temporary_directory()
    store = None
    try:
        root = Path(tmpdir.name)
        store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(PostgresBackend()),
        )
        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")
        snapshot = build_generation_context_snapshot(store, user, document_kind="complaint")
        assert snapshot["content_workflow"]["applied_published_versions"] == snapshot["effective_config_snapshot"]
    finally:
        if store is not None:
            store.repository.close()
        tmpdir.cleanup()


def test_legacy_generation_context_snapshot_uses_shared_server_context_resolver(monkeypatch):
    tmpdir = make_temporary_directory()
    store = None
    try:
        root = Path(tmpdir.name)
        store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(PostgresBackend()),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_server_identity",
            lambda **kwargs: type("Identity", (), {"code": "blackberry", "name": "BlackBerry"})(),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_server_feature_flags",
            lambda **kwargs: (),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_runtime_pack_feature_flags",
            lambda **kwargs: (),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_server_law_bundle_path",
            lambda **kwargs: "law_bundles/legacy.json",
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_runtime_pack_law_bundle_path",
            lambda **kwargs: "",
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.read_runtime_pack_snapshot",
            lambda *, server_code: type("Snapshot", (), {"pack_version": 2})(),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.load_law_bundle_meta",
            lambda server_code, bundle_path: type("Meta", (), {"fingerprint": "bundle_hash"})(),
        )

        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")
        snapshot = build_generation_context_snapshot(store, user, document_kind="complaint")
        assert snapshot["server"]["code"] == "blackberry"
        assert snapshot["law_version_set"]["hash"] == "bundle_hash"
    finally:
        if store is not None:
            store.repository.close()
        tmpdir.cleanup()


def test_legacy_generation_context_snapshot_prefers_runtime_pack_metadata(monkeypatch):
    tmpdir = make_temporary_directory()
    store = None
    try:
        root = Path(tmpdir.name)
        store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(PostgresBackend()),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_server_identity",
            lambda **kwargs: type("Identity", (), {"code": "blackberry", "name": "BlackBerry"})(),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_runtime_pack_feature_flags",
            lambda **kwargs: ("pack_alpha", "pack_beta"),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_server_feature_flags",
            lambda **kwargs: ("legacy_flag",),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_runtime_pack_law_bundle_path",
            lambda **kwargs: "law_bundles/runtime-pack.json",
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_server_law_bundle_path",
            lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy bundle path should not be used when runtime pack metadata is present")),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.read_runtime_pack_snapshot",
            lambda *, server_code: type("Snapshot", (), {"pack_version": 4})(),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.load_law_bundle_meta",
            lambda server_code, bundle_path: type("Meta", (), {"fingerprint": f"hash::{bundle_path}"})(),
        )

        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")
        snapshot = build_generation_context_snapshot(store, user, document_kind="complaint")
        assert snapshot["law_version_set"]["hash"] == "hash::law_bundles/runtime-pack.json"
        assert snapshot["feature_flags"] == ["pack_alpha", "pack_beta"]
    finally:
        if store is not None:
            store.repository.close()
        tmpdir.cleanup()


def test_legacy_generation_context_snapshot_respects_explicit_empty_pack_metadata(monkeypatch):
    tmpdir = make_temporary_directory()
    store = None
    try:
        root = Path(tmpdir.name)
        store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(PostgresBackend()),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_server_identity",
            lambda **kwargs: type("Identity", (), {"code": "blackberry", "name": "BlackBerry"})(),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_runtime_pack_feature_flags",
            lambda **kwargs: (),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_server_feature_flags",
            lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy feature flags should not be used when pack explicitly declares feature_flags")),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_runtime_pack_law_bundle_path",
            lambda **kwargs: "",
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.resolve_server_law_bundle_path",
            lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy bundle path should not be used when pack explicitly declares law_qa_bundle_path")),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.read_runtime_pack_snapshot",
            lambda *, server_code: type(
                "Snapshot",
                (),
                {
                    "pack_version": 5,
                    "metadata": {"feature_flags": [], "law_qa_bundle_path": ""},
                },
            )(),
        )
        monkeypatch.setattr(
            "ogp_web.services.complaint_service.load_law_bundle_meta",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bundle meta should not be loaded when explicit pack bundle path is empty")),
        )

        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")
        snapshot = build_generation_context_snapshot(store, user, document_kind="complaint")
        assert snapshot["feature_flags"] == []
        assert snapshot["law_version_set"]["hash"] == ""
    finally:
        if store is not None:
            store.repository.close()
        tmpdir.cleanup()


def test_pilot_runtime_adapter_resolves_without_server_config_lookup(monkeypatch):
    tmpdir = make_temporary_directory()
    store = None
    try:
        root = Path(tmpdir.name)
        store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(PostgresBackend()),
        )

        monkeypatch.setattr(
            "ogp_web.services.pilot_runtime_adapter.get_server_config",
            lambda server_code: (_ for _ in ()).throw(AssertionError(f"unexpected get_server_config lookup for {server_code}")),
            raising=False,
        )
        monkeypatch.setattr(
            "ogp_web.services.pilot_runtime_adapter.load_law_bundle_meta",
            lambda server_code: type("Meta", (), {"fingerprint": "bundle_hash"})(),
        )

        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")
        context = resolve_pilot_complaint_runtime_context(store, user)
        assert context.server_code == "blackberry"
        assert context.law_set_version["hash"] == "bundle_hash"
    finally:
        if store is not None:
            store.repository.close()
        tmpdir.cleanup()
