from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.async_job_service import AsyncJobService


class _DummyQueueProvider:
    def publish(self, message):  # noqa: ANN001
        return None

    def dead_letter(self, message, reason):  # noqa: ANN001
        return None


class _DummyBackend:
    def connect(self):
        raise NotImplementedError


def test_content_reindex_dedup_should_ignore_request_id_at_route_level():
    service = AsyncJobService(_DummyBackend(), queue_provider=_DummyQueueProvider())

    payload_one = {"scope": "all", "request_id": "req-1"}
    payload_two = {"scope": "all", "request_id": "req-2"}

    explicit_key = "content_reindex:all"
    first = service._build_idempotency_key(  # noqa: SLF001
        job_type="content_reindex",
        entity_type="content",
        entity_id=None,
        payload_json=payload_one,
        key=explicit_key,
    )
    second = service._build_idempotency_key(  # noqa: SLF001
        job_type="content_reindex",
        entity_type="content",
        entity_id=None,
        payload_json=payload_two,
        key=explicit_key,
    )

    assert first == explicit_key
    assert second == explicit_key
