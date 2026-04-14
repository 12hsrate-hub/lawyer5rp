from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.content_workflow_service import ContentWorkflowService


class InMemoryRepo:
    def __init__(self):
        self.next_ids = {
            "item": 1,
            "version": 1,
            "cr": 1,
            "review": 1,
            "batch": 1,
            "batch_item": 1,
            "audit": 1,
        }
        self.items: dict[int, dict[str, Any]] = {}
        self.versions: dict[int, dict[str, Any]] = {}
        self.change_requests: dict[int, dict[str, Any]] = {}
        self.reviews: dict[int, dict[str, Any]] = {}
        self.batches: dict[int, dict[str, Any]] = {}
        self.batch_items: dict[int, dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []

    def _id(self, k: str) -> int:
        n = self.next_ids[k]
        self.next_ids[k] += 1
        return n

    def list_content_items(self, *, server_scope, server_id, content_type=None):
        return [i for i in self.items.values() if i["server_scope"] == server_scope and i.get("server_id") == server_id and (not content_type or i["content_type"] == content_type)]

    def get_content_item(self, *, content_item_id):
        return self.items.get(content_item_id)

    def get_content_item_by_identity(self, *, server_scope, server_id, content_type, content_key):
        for i in self.items.values():
            if i["server_scope"] == server_scope and i.get("server_id") == server_id and i["content_type"] == content_type and i["content_key"] == content_key:
                return i
        return None

    def create_content_item(self, **kwargs):
        item_id = self._id("item")
        row = {"id": item_id, "current_published_version_id": None, **kwargs}
        self.items[item_id] = row
        return row

    def create_content_version(self, *, content_item_id, payload_json, schema_version, created_by):
        version_num = len([v for v in self.versions.values() if v["content_item_id"] == content_item_id]) + 1
        vid = self._id("version")
        row = {"id": vid, "content_item_id": content_item_id, "version_number": version_num, "payload_json": json.loads(json.dumps(payload_json)), "schema_version": schema_version, "created_by": created_by}
        self.versions[vid] = row
        return row

    def get_content_version(self, *, version_id):
        return self.versions.get(version_id)

    def create_change_request(self, **kwargs):
        cid = self._id("cr")
        row = {"id": cid, **kwargs}
        self.change_requests[cid] = row
        return row

    def get_change_request(self, *, change_request_id):
        return self.change_requests.get(change_request_id)

    def update_change_request_status(self, *, change_request_id, status):
        self.change_requests[change_request_id]["status"] = status
        return self.change_requests[change_request_id]

    def list_change_requests(self, *, content_item_id):
        return [c for c in self.change_requests.values() if c["content_item_id"] == content_item_id]

    def create_review(self, **kwargs):
        rid = self._id("review")
        row = {"id": rid, **kwargs}
        self.reviews[rid] = row
        return row

    def list_reviews(self, *, change_request_id):
        return [r for r in self.reviews.values() if r["change_request_id"] == change_request_id]

    def create_publish_batch(self, **kwargs):
        bid = self._id("batch")
        row = {"id": bid, **kwargs}
        self.batches[bid] = row
        return row

    def get_publish_batch(self, *, batch_id):
        return self.batches.get(batch_id)

    def create_publish_batch_item(self, **kwargs):
        iid = self._id("batch_item")
        row = {"id": iid, **kwargs}
        self.batch_items[iid] = row
        return row

    def list_publish_batch_items(self, *, publish_batch_id):
        return [i for i in self.batch_items.values() if i["publish_batch_id"] == publish_batch_id]

    def set_current_published_version(self, *, content_item_id, version_id, status="published"):
        self.items[content_item_id]["current_published_version_id"] = version_id
        self.items[content_item_id]["status"] = status
        return self.items[content_item_id]

    def append_audit_log(self, **kwargs):
        kwargs["id"] = self._id("audit")
        self.audit.append(kwargs)
        return kwargs

    def list_audit_logs(self, *, server_id, entity_type="", entity_id="", limit=100):
        rows = [a for a in self.audit if a.get("server_id") == server_id]
        if entity_type:
            rows = [a for a in rows if a["entity_type"] == entity_type]
        if entity_id:
            rows = [a for a in rows if a["entity_id"] == entity_id]
        return rows[-limit:]


def _service():
    return ContentWorkflowService(InMemoryRepo())


def test_lifecycle_review_publish_and_immutability():
    service = _service()
    item = service.create_content_item(server_scope="server", server_id="blackberry", content_type="procedures", content_key="k1", title="t", metadata_json={}, actor_user_id=1, request_id="r")
    draft = service.create_draft_version(content_item_id=item["id"], payload_json={"procedure_code": "k1", "title": "t", "steps": ["a"]}, schema_version=1, actor_user_id=1, request_id="r", server_scope="server", server_id="blackberry")
    submitted = service.submit_change_request(change_request_id=draft["change_request"]["id"], actor_user_id=2, request_id="r", server_scope="server", server_id="blackberry")
    assert submitted["status"] == "in_review"
    review = service.review_change_request(change_request_id=draft["change_request"]["id"], reviewer_user_id=3, decision="approve", comment="ok", diff_json={"x": [0, 1]}, request_id="r", server_scope="server", server_id="blackberry")
    assert review["change_request"]["status"] == "approved"
    published = service.publish_change_request(change_request_id=draft["change_request"]["id"], actor_user_id=4, request_id="r", summary_json={}, server_scope="server", server_id="blackberry")
    assert published["content_item"]["current_published_version_id"] == draft["version"]["id"]
    assert draft["version"]["payload_json"]["procedure_code"] == "k1"


def test_publish_without_approval_is_blocked():
    service = _service()
    item = service.create_content_item(server_scope="server", server_id="blackberry", content_type="validation_rules", content_key="k2", title="t", metadata_json={}, actor_user_id=1, request_id="r")
    draft = service.create_draft_version(content_item_id=item["id"], payload_json={"rule_code": "k2", "title": "t", "ruleset": {"a": 1}}, schema_version=1, actor_user_id=1, request_id="r", server_scope="server", server_id="blackberry")
    try:
        service.publish_change_request(change_request_id=draft["change_request"]["id"], actor_user_id=4, request_id="r", summary_json={}, server_scope="server", server_id="blackberry")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "publish_requires_approved_change_request"


def test_scope_isolation_and_rollback_creates_new_publish_fact():
    service = _service()
    item = service.create_content_item(server_scope="server", server_id="blackberry", content_type="templates", content_key="k3", title="t", metadata_json={}, actor_user_id=1, request_id="r")
    d1 = service.create_draft_version(content_item_id=item["id"], payload_json={"template_code": "k3", "title": "t", "body": "b1"}, schema_version=1, actor_user_id=1, request_id="r", server_scope="server", server_id="blackberry")
    service.submit_change_request(change_request_id=d1["change_request"]["id"], actor_user_id=1, request_id="r", server_scope="server", server_id="blackberry")
    service.review_change_request(change_request_id=d1["change_request"]["id"], reviewer_user_id=2, decision="approve", comment="ok", diff_json={}, request_id="r", server_scope="server", server_id="blackberry")
    p1 = service.publish_change_request(change_request_id=d1["change_request"]["id"], actor_user_id=1, request_id="r", summary_json={}, server_scope="server", server_id="blackberry")
    d2 = service.create_draft_version(content_item_id=item["id"], payload_json={"template_code": "k3", "title": "t", "body": "b2"}, schema_version=1, actor_user_id=1, request_id="r", server_scope="server", server_id="blackberry")
    service.submit_change_request(change_request_id=d2["change_request"]["id"], actor_user_id=1, request_id="r", server_scope="server", server_id="blackberry")
    service.review_change_request(change_request_id=d2["change_request"]["id"], reviewer_user_id=2, decision="approve", comment="ok", diff_json={}, request_id="r", server_scope="server", server_id="blackberry")
    p2 = service.publish_change_request(change_request_id=d2["change_request"]["id"], actor_user_id=1, request_id="r", summary_json={}, server_scope="server", server_id="blackberry")

    rollback = service.rollback_publish_batch(publish_batch_id=p2["batch"]["id"], actor_user_id=1, request_id="r", reason="oops", server_scope="server", server_id="blackberry")
    assert rollback["batch"]["rollback_of_batch_id"] == p2["batch"]["id"]
    assert rollback["items"][0]["published_version_id"] == p1["batch_item"]["published_version_id"]

    try:
        service.get_content_item(content_item_id=item["id"], server_scope="server", server_id="vice")
        assert False
    except PermissionError:
        assert True


def test_audit_log_has_actor_action_diff_and_entity_ref():
    service = _service()
    item = service.create_content_item(server_scope="server", server_id="blackberry", content_type="features", content_key="k4", title="t", metadata_json={}, actor_user_id=77, request_id="req-1")
    logs = service.list_audit_trail(server_scope="server", server_id="blackberry", limit=10)
    assert logs
    last = logs[-1]
    assert last["actor_user_id"] == 77
    assert last["entity_type"] == "content_item"
    assert last["entity_id"] == str(item["id"])
    assert "created" in last["diff_json"]


def test_create_content_item_rejects_non_canonical_type():
    service = _service()
    try:
        service.create_content_item(
            server_scope="server",
            server_id="blackberry",
            content_type="laws",
            content_key="legacy",
            title="Legacy",
            metadata_json={},
            actor_user_id=1,
            request_id="r",
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "unsupported_content_type"


def test_create_draft_version_validates_schema_contract():
    service = _service()
    item = service.create_content_item(
        server_scope="server",
        server_id="blackberry",
        content_type="features",
        content_key="f1",
        title="Feature",
        metadata_json={},
        actor_user_id=1,
        request_id="r",
    )
    try:
        service.create_draft_version(
            content_item_id=item["id"],
            payload_json={"feature_code": "f1", "title": "Feature", "enabled": "yes"},
            schema_version=1,
            actor_user_id=1,
            request_id="r",
            server_scope="server",
            server_id="blackberry",
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc).startswith("content_payload_contract_violation:")


def test_validate_change_request_returns_contract_errors_for_broken_candidate_version():
    service = _service()
    item = service.create_content_item(
        server_scope="server",
        server_id="blackberry",
        content_type="templates",
        content_key="tpl1",
        title="Template",
        metadata_json={},
        actor_user_id=1,
        request_id="r",
    )
    draft = service.create_draft_version(
        content_item_id=item["id"],
        payload_json={"template_code": "tpl1", "title": "Template", "body": "draft"},
        schema_version=1,
        actor_user_id=1,
        request_id="r",
        server_scope="server",
        server_id="blackberry",
    )
    draft["version"]["payload_json"] = {"template_code": "tpl1", "title": "Template", "body": 42}

    validation = service.validate_change_request(
        change_request_id=draft["change_request"]["id"],
        server_scope="server",
        server_id="blackberry",
    )

    assert validation["ok"] is False
    assert "invalid_field_type:body:string_required" in validation["errors"]


def test_submit_change_request_revalidates_candidate_version_before_review():
    service = _service()
    item = service.create_content_item(
        server_scope="server",
        server_id="blackberry",
        content_type="features",
        content_key="f2",
        title="Feature 2",
        metadata_json={},
        actor_user_id=1,
        request_id="r",
    )
    draft = service.create_draft_version(
        content_item_id=item["id"],
        payload_json={"feature_code": "f2", "title": "Feature 2", "enabled": True},
        schema_version=1,
        actor_user_id=1,
        request_id="r",
        server_scope="server",
        server_id="blackberry",
    )
    draft["version"]["payload_json"] = {"feature_code": "f2", "title": "Feature 2", "enabled": "broken"}

    try:
        service.submit_change_request(
            change_request_id=draft["change_request"]["id"],
            actor_user_id=2,
            request_id="r",
            server_scope="server",
            server_id="blackberry",
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc).startswith("change_request_validation_failed:")


def test_high_risk_entities_require_second_reviewer_for_approval():
    service = _service()
    item = service.create_content_item(
        server_scope="server",
        server_id="blackberry",
        content_type="templates",
        content_key="tpl2",
        title="Template 2",
        metadata_json={},
        actor_user_id=11,
        request_id="r",
    )
    draft = service.create_draft_version(
        content_item_id=item["id"],
        payload_json={"template_code": "tpl2", "title": "Template 2", "body": "body"},
        schema_version=1,
        actor_user_id=11,
        request_id="r",
        server_scope="server",
        server_id="blackberry",
    )
    service.submit_change_request(
        change_request_id=draft["change_request"]["id"],
        actor_user_id=11,
        request_id="r",
        server_scope="server",
        server_id="blackberry",
    )

    try:
        service.review_change_request(
            change_request_id=draft["change_request"]["id"],
            reviewer_user_id=11,
            decision="approve",
            comment="self-approve",
            diff_json={},
            request_id="r",
            server_scope="server",
            server_id="blackberry",
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "two_person_review_required_for_high_risk_entity"

    approved = service.review_change_request(
        change_request_id=draft["change_request"]["id"],
        reviewer_user_id=22,
        decision="approve",
        comment="peer-approve",
        diff_json={},
        request_id="r",
        server_scope="server",
        server_id="blackberry",
    )
    assert approved["change_request"]["status"] == "approved"
