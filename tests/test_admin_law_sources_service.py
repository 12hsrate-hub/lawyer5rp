from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_WEB_SECRET", "test-secret")
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
os.environ.setdefault("OGP_SKIP_DEFAULT_APP_INIT", "1")

from fastapi import HTTPException

from ogp_web.services.admin_law_sources_service import (
    backfill_law_sources_source_set_payload,
    require_law_sources_task_status_payload,
    resolve_law_sources_target_server_code,
)
from ogp_web.services.auth_service import AuthUser


class _Permissions:
    def __init__(self, allowed: set[str]):
        self.allowed = allowed

    def has(self, permission: str) -> bool:
        return permission in self.allowed


class _FakeUserStore:
    pass


class _FakeSourceSet:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeRevision:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeBinding:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeLawSourceSetsStore:
    def __init__(self):
        self.source_sets: dict[str, dict[str, object]] = {}
        self.revisions: dict[str, list[dict[str, object]]] = {}
        self.bindings: dict[str, list[dict[str, object]]] = {}
        self.next_revision_id = 1
        self.next_binding_id = 1

    def get_source_set(self, *, source_set_key: str):
        row = self.source_sets.get(source_set_key)
        return _FakeSourceSet(**row) if row else None

    def create_source_set(self, *, source_set_key: str, title: str, description: str = "", scope: str = "global"):
        row = {
            "source_set_key": source_set_key,
            "title": title,
            "description": description,
            "scope": scope,
        }
        self.source_sets[source_set_key] = row
        return _FakeSourceSet(**row)

    def list_revisions(self, *, source_set_key: str):
        return [_FakeRevision(**item) for item in self.revisions.get(source_set_key, [])]

    def create_revision(self, *, source_set_key: str, container_urls, adapter_policy_json=None, metadata_json=None, status="draft"):
        row = {
            "id": self.next_revision_id,
            "source_set_key": source_set_key,
            "revision": len(self.revisions.get(source_set_key, [])) + 1,
            "status": status,
            "container_urls": tuple(container_urls),
            "adapter_policy_json": dict(adapter_policy_json or {}),
            "metadata_json": dict(metadata_json or {}),
        }
        self.next_revision_id += 1
        self.revisions.setdefault(source_set_key, []).insert(0, row)
        return _FakeRevision(**row)

    def list_bindings(self, *, server_code: str):
        return [_FakeBinding(**item) for item in self.bindings.get(server_code, [])]

    def create_binding(self, *, server_code: str, source_set_key: str, priority: int = 100, is_active: bool = True, metadata_json=None, **kwargs):
        _ = kwargs
        row = {
            "id": self.next_binding_id,
            "server_code": server_code,
            "source_set_key": source_set_key,
            "priority": priority,
            "is_active": is_active,
            "metadata_json": dict(metadata_json or {}),
        }
        self.next_binding_id += 1
        self.bindings.setdefault(server_code, []).append(row)
        return _FakeBinding(**row)


class AdminLawSourcesServiceTests(unittest.TestCase):
    def test_resolve_law_sources_target_server_code_allows_same_server(self):
        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")
        resolved = resolve_law_sources_target_server_code(
            user=user,
            user_store=_FakeUserStore(),
            requested_server_code="",
        )
        self.assertEqual(resolved, "blackberry")

    def test_resolve_law_sources_target_server_code_requires_cross_server_permissions(self):
        user = AuthUser(username="tester", email="tester@example.com", server_code="blackberry")

        from unittest.mock import patch

        with patch(
            "ogp_web.services.admin_law_sources_service.resolve_user_server_permissions",
            side_effect=[_Permissions({"manage_laws"}), _Permissions({"manage_laws"})],
        ):
            with self.assertRaises(HTTPException) as exc:
                resolve_law_sources_target_server_code(
                    user=user,
                    user_store=_FakeUserStore(),
                    requested_server_code="orange",
                )
        self.assertEqual(exc.exception.status_code, 403)

    def test_require_law_sources_task_status_payload_validates_scope_and_server(self):
        task_loader = lambda task_id: {"task_id": task_id, "scope": "law_sources_rebuild", "server_code": "blackberry", "status": "finished"}
        payload = require_law_sources_task_status_payload(
            task_id="t1",
            target_server_code="blackberry",
            task_loader=task_loader,
        )
        self.assertEqual(payload["status"], "finished")
        self.assertEqual(payload["canonical_status"], "succeeded")

        with self.assertRaises(HTTPException) as missing_exc:
            require_law_sources_task_status_payload(
                task_id="missing",
                target_server_code="blackberry",
                task_loader=lambda _task_id: None,
            )
        self.assertEqual(missing_exc.exception.status_code, 404)

        with self.assertRaises(HTTPException) as server_exc:
            require_law_sources_task_status_payload(
                task_id="foreign",
                target_server_code="blackberry",
                task_loader=lambda task_id: {"task_id": task_id, "scope": "law_sources_rebuild", "server_code": "orange", "status": "running"},
            )
        self.assertEqual(server_exc.exception.status_code, 403)

    def test_backfill_law_sources_source_set_payload_creates_legacy_bridge_rows(self):
        store = _FakeLawSourceSetsStore()

        from unittest.mock import patch

        with patch(
            "ogp_web.services.admin_law_sources_service.LawAdminService.get_effective_sources",
            return_value=type(
                "Snapshot",
                (),
                {
                    "source_urls": ("https://example.com/law/a", "https://example.com/law/b"),
                    "source_origin": "content_workflow",
                },
            )(),
        ):
            payload = backfill_law_sources_source_set_payload(
                workflow_service=type("WF", (), {"repository": object()})(),
                source_sets_store=store,
                server_code="orange",
                actor_user_id=12,
                request_id="req-1",
            )

        self.assertTrue(payload["changed"])
        self.assertEqual(payload["source_set_key"], "legacy-orange-default")
        self.assertTrue(payload["source_set_created"])
        self.assertTrue(payload["revision_created"])
        self.assertTrue(payload["binding_created"])
        self.assertEqual(payload["revision"]["status"], "legacy_flat")
        self.assertEqual(payload["binding"]["source_set_key"], "legacy-orange-default")

    def test_backfill_law_sources_source_set_payload_is_idempotent_for_same_sources(self):
        store = _FakeLawSourceSetsStore()

        from unittest.mock import patch

        snapshot = type(
            "Snapshot",
            (),
            {
                "source_urls": ("https://example.com/law/a",),
                "source_origin": "server_config",
            },
        )()
        with patch(
            "ogp_web.services.admin_law_sources_service.LawAdminService.get_effective_sources",
            return_value=snapshot,
        ):
            first = backfill_law_sources_source_set_payload(
                workflow_service=type("WF", (), {"repository": object()})(),
                source_sets_store=store,
                server_code="blackberry",
                actor_user_id=7,
                request_id="req-1",
            )
            second = backfill_law_sources_source_set_payload(
                workflow_service=type("WF", (), {"repository": object()})(),
                source_sets_store=store,
                server_code="blackberry",
                actor_user_id=7,
                request_id="req-2",
            )

        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertFalse(second["source_set_created"])
        self.assertFalse(second["revision_created"])
        self.assertFalse(second["binding_created"])


if __name__ == "__main__":
    unittest.main()
