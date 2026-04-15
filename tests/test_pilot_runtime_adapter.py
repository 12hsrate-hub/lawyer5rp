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
    resolve_pilot_complaint_runtime_context,
    supports_pilot_runtime_adapter,
)
from ogp_web.storage.user_repository import UserRepository
from ogp_web.storage.user_store import UserStore
from tests.temp_helpers import make_temporary_directory
from tests.test_web_storage import PostgresBackend


def test_pilot_runtime_adapter_supports_only_blackberry_complaint():
    assert supports_pilot_runtime_adapter(server_code="blackberry", document_kind="complaint") is True
    assert supports_pilot_runtime_adapter(server_code="blackberry", document_kind="rehab") is False
    assert supports_pilot_runtime_adapter(server_code="other", document_kind="complaint") is False

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
