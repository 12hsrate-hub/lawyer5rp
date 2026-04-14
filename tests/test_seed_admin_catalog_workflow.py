from __future__ import annotations

import scripts.seed_admin_catalog_workflow as seed_script


class _FakeRepository:
    def get_content_item_by_identity(self, **kwargs):
        return None

    def list_content_versions(self, **kwargs):
        return []


class _FakeService:
    last_instance: "_FakeService | None" = None

    def __init__(self, repository, *, legacy_store=None):
        self.repository = repository
        self.review_calls: list[dict[str, object]] = []
        self._content_item_id = 100
        self._change_request_id = 200
        self._publish_batch_id = 300
        _FakeService.last_instance = self

    def create_content_item(self, **kwargs):
        self._content_item_id += 1
        return {"id": self._content_item_id}

    def create_draft_version(self, **kwargs):
        self._change_request_id += 1
        return {
            "change_request": {"id": self._change_request_id},
            "version": {"id": self._change_request_id + 1000},
        }

    def submit_change_request(self, **kwargs):
        return {"id": kwargs["change_request_id"]}

    def review_change_request(self, **kwargs):
        self.review_calls.append(dict(kwargs))
        return {"review": {"id": 1}, "change_request": {"id": kwargs["change_request_id"], "status": "approved"}}

    def publish_change_request(self, **kwargs):
        self._publish_batch_id += 1
        return {"batch": {"id": self._publish_batch_id}}


def test_seed_uses_distinct_reviewer_for_auto_approval(monkeypatch):
    monkeypatch.setattr(seed_script, "load_web_env", lambda: None)
    monkeypatch.setattr(seed_script, "get_database_backend", lambda: object())
    monkeypatch.setattr(seed_script, "ContentWorkflowRepository", lambda backend: _FakeRepository())
    monkeypatch.setattr(seed_script, "ContentWorkflowService", _FakeService)
    monkeypatch.setattr(seed_script, "_resolve_actor_user_id", lambda: 11)
    monkeypatch.setattr(seed_script, "_resolve_reviewer_user_id", lambda actor_user_id: 22)

    summary = seed_script.seed()

    assert summary["created_count"] == sum(len(items) for items in seed_script.SEED_ITEMS.values())
    assert _FakeService.last_instance is not None
    assert _FakeService.last_instance.review_calls
    assert all(call["reviewer_user_id"] == 22 for call in _FakeService.last_instance.review_calls)
    assert all(call["reviewer_user_id"] != 11 for call in _FakeService.last_instance.review_calls)
