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

from ogp_web.schemas import AdminCatalogItemPayload, AdminCatalogRollbackPayload, AdminCatalogWorkflowPayload
from ogp_web.services.admin_catalog_service import (
    build_catalog_item_payload,
    build_catalog_list_payload,
    build_catalog_payload_config,
    execute_catalog_workflow_payload,
)


class _FakeContentWorkflowService:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def list_content_items(self, *, server_scope: str, server_id: str | None, content_type: str | None = None, include_legacy_fallback: bool = False):
        self.calls.append({"kind": "list_content_items", "content_type": content_type})
        return {
            "items": [{"id": 42, "title": "Complaint law index", "content_type": content_type, "status": "draft"}],
            "legacy_fallback": [],
        }

    def list_change_requests(self, *, content_item_id: int, server_scope: str, server_id: str | None):
        self.calls.append({"kind": "list_change_requests", "content_item_id": content_item_id})
        return [{"id": 77, "status": "draft", "candidate_version_id": 701}]

    def list_audit_trail(self, *, server_scope: str, server_id: str | None, entity_type: str = "", entity_id: str = "", limit: int = 100):
        self.calls.append({"kind": "list_audit_trail", "entity_type": entity_type, "entity_id": entity_id, "limit": limit})
        return [{"id": 1, "entity_type": entity_type or "law", "entity_id": entity_id or "42"}]

    def get_content_item(self, *, content_item_id: int, server_scope: str, server_id: str | None):
        self.calls.append({"kind": "get_content_item", "content_item_id": content_item_id})
        return {"id": content_item_id, "current_published_version_id": 700}

    def list_versions(self, *, content_item_id: int, server_scope: str, server_id: str | None):
        self.calls.append({"kind": "list_versions", "content_item_id": content_item_id})
        return [
            {"id": 700, "payload_json": {"key": "published", "status": "published"}},
            {"id": 701, "payload_json": {"key": "draft", "status": "draft"}},
        ]

    def submit_change_request(self, **kwargs):
        self.calls.append({"kind": "submit_change_request", **kwargs})
        return {"id": kwargs["change_request_id"], "status": "in_review"}

    def review_change_request(self, **kwargs):
        self.calls.append({"kind": "review_change_request", **kwargs})
        return {"change_request": {"id": kwargs["change_request_id"], "status": "approved"}}

    def publish_change_request(self, **kwargs):
        self.calls.append({"kind": "publish_change_request", **kwargs})
        return {"batch": {"id": 9}}


class AdminCatalogServiceTests(unittest.TestCase):
    def test_build_catalog_list_payload_enriches_active_change_request(self):
        service = _FakeContentWorkflowService()

        payload = build_catalog_list_payload(
            workflow_service=service,
            server_code="blackberry",
            entity_type="laws",
        )

        self.assertEqual(payload["entity_type"], "laws")
        self.assertEqual(payload["items"][0]["content_type"], "procedures")
        self.assertEqual(payload["items"][0]["active_change_request_id"], 77)
        self.assertEqual(payload["items"][0]["active_change_request_status"], "draft")

    def test_build_catalog_item_payload_prefers_published_version(self):
        service = _FakeContentWorkflowService()

        payload = build_catalog_item_payload(
            workflow_service=service,
            server_code="blackberry",
            item_id=42,
        )

        self.assertEqual(payload["effective_version"]["id"], 700)
        self.assertEqual(payload["effective_payload"]["key"], "published")
        self.assertEqual(payload["latest_change_request"]["id"], 77)

    def test_build_catalog_payload_config_merges_typed_fields(self):
        payload = AdminCatalogItemPayload(
            title="Law Index",
            key="law_index",
            status="draft",
            law_code="uk",
            config={"extra": "value"},
        )

        result = build_catalog_payload_config(payload)

        self.assertEqual(result["key"], "law_index")
        self.assertEqual(result["law_code"], "uk")
        self.assertEqual(result["extra"], "value")

    def test_execute_catalog_workflow_payload_routes_actions(self):
        service = _FakeContentWorkflowService()

        submit = execute_catalog_workflow_payload(
            workflow_service=service,
            server_code="blackberry",
            actor_user_id=5,
            request_id="r1",
            payload=AdminCatalogWorkflowPayload(action="submit_for_review", change_request_id=11),
        )
        approve = execute_catalog_workflow_payload(
            workflow_service=service,
            server_code="blackberry",
            actor_user_id=5,
            request_id="r2",
            payload=AdminCatalogWorkflowPayload(action="approve", change_request_id=12),
        )

        self.assertTrue(submit["ok"])
        self.assertEqual(submit["result"]["id"], 11)
        self.assertTrue(approve["ok"])
        self.assertEqual(approve["result"]["change_request"]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
