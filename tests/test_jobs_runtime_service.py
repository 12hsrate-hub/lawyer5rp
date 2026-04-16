from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from fastapi import HTTPException

from ogp_web.services.jobs_runtime_service import JobsRuntimeService


class _DummyAsyncJobService:
    def __init__(self):
        self.calls = []

    def create_job(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "id": 42,
            "status": "queued",
            "job_type": kwargs["job_type"],
        }


class _RuntimeServiceUnderTest(JobsRuntimeService):
    def __init__(self, async_job_service: _DummyAsyncJobService):
        self._async_job_service = async_job_service

    def _service(self, *, store, request):
        return self._async_job_service

    def _actor_id(self, *, store, username: str) -> int | None:
        return 77


def _request(request_id: str = "req-1"):
    return SimpleNamespace(state=SimpleNamespace(request_id=request_id))


def _user(username: str = "tester", server_code: str = "blackberry"):
    return SimpleNamespace(username=username, server_code=server_code)


def test_create_reindex_job_uses_default_idempotency_key():
    async_job_service = _DummyAsyncJobService()
    service = _RuntimeServiceUnderTest(async_job_service)

    payload = service.create_reindex_job(
        scope="all",
        idempotency_key=None,
        request=_request(),
        store=object(),
        user=_user(),
    )

    assert payload["job_id"] == 42
    assert async_job_service.calls[0]["idempotency_key"] == "content_reindex:all"
    assert async_job_service.calls[0]["payload_json"] == {"scope": "all", "request_id": "req-1"}


def test_create_import_job_requires_non_empty_source():
    async_job_service = _DummyAsyncJobService()
    service = _RuntimeServiceUnderTest(async_job_service)

    try:
        service.create_import_job(
            source="   ",
            idempotency_key=None,
            request=_request(),
            store=object(),
            user=_user(),
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == ["source обязателен."]
    else:
        raise AssertionError("HTTPException was not raised for an empty import source")


def test_create_document_generation_job_builds_canonical_payload():
    async_job_service = _DummyAsyncJobService()
    service = _RuntimeServiceUnderTest(async_job_service)

    payload = service.create_document_generation_job(
        document_id=15,
        content_json={"body": "hello"},
        idempotency_key="gen-key",
        publish_batch_id=91,
        request=_request("req-doc"),
        store=object(),
        user=_user("alice", "orange"),
    )

    assert payload["job_id"] == 42
    assert async_job_service.calls[0]["payload_json"] == {
        "document_id": 15,
        "content_json": {"body": "hello"},
        "username": "alice",
        "user_server_id": "orange",
        "request_id": "req-doc",
        "publish_batch_id": 91,
    }
