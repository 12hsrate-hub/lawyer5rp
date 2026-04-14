from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueueMessage:
    job_id: int
    server_scope: str
    server_id: str | None
    job_type: str
    request_id: str = ""
    publish_batch_id: int | None = None
    dedup_key: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "job_id": int(self.job_id),
                "server_scope": self.server_scope,
                "server_id": self.server_id,
                "job_type": self.job_type,
                "request_id": self.request_id,
                "publish_batch_id": self.publish_batch_id,
                "dedup_key": self.dedup_key,
            },
            ensure_ascii=False,
            sort_keys=True,
        )


class QueueProvider(Protocol):
    def publish(self, *, message: QueueMessage) -> None: ...

    def blocking_pop(self, *, timeout_seconds: int = 5) -> QueueMessage | None: ...

    def dead_letter(self, *, message: QueueMessage, reason: str) -> None: ...


class LocalQueueProvider:
    """Dev-only in-process queue adapter."""

    def __init__(self):
        self._queue: queue.Queue[QueueMessage] = queue.Queue()
        self._dead_letters: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def publish(self, *, message: QueueMessage) -> None:
        self._queue.put(message)

    def blocking_pop(self, *, timeout_seconds: int = 5) -> QueueMessage | None:
        try:
            return self._queue.get(timeout=max(1, int(timeout_seconds)))
        except queue.Empty:
            return None

    def dead_letter(self, *, message: QueueMessage, reason: str) -> None:
        with self._lock:
            self._dead_letters.append({"message": message.to_json(), "reason": reason, "ts": time.time()})


class RedisQueueProvider:
    def __init__(self, *, redis_url: str, queue_name: str = "ogp:jobs:queue", dlq_name: str = "ogp:jobs:dlq"):
        try:
            import redis
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("redis package is required for RedisQueueProvider") from exc
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self.queue_name = queue_name
        self.dlq_name = dlq_name

    def publish(self, *, message: QueueMessage) -> None:
        if message.dedup_key:
            dedup_key = f"ogp:jobs:dedup:{message.dedup_key}"
            was_set = self._redis.set(dedup_key, str(message.job_id), ex=60 * 60, nx=True)
            if not was_set:
                return
        self._redis.rpush(self.queue_name, message.to_json())

    def blocking_pop(self, *, timeout_seconds: int = 5) -> QueueMessage | None:
        raw = self._redis.blpop(self.queue_name, timeout=max(1, int(timeout_seconds)))
        if not raw:
            return None
        _, payload = raw
        data = json.loads(payload)
        return QueueMessage(
            job_id=int(data["job_id"]),
            server_scope=str(data.get("server_scope") or "server"),
            server_id=str(data.get("server_id") or "") or None,
            job_type=str(data.get("job_type") or ""),
            request_id=str(data.get("request_id") or ""),
            publish_batch_id=int(data["publish_batch_id"]) if data.get("publish_batch_id") is not None else None,
            dedup_key=str(data.get("dedup_key") or "") or None,
        )

    def dead_letter(self, *, message: QueueMessage, reason: str) -> None:
        payload = {"message": json.loads(message.to_json()), "reason": reason, "ts": int(time.time())}
        self._redis.rpush(self.dlq_name, json.dumps(payload, ensure_ascii=False))


def build_queue_provider_from_env() -> QueueProvider:
    provider = (os.getenv("OGP_QUEUE_PROVIDER") or "local").strip().lower()
    if provider == "redis":
        redis_url = (os.getenv("OGP_REDIS_URL") or "").strip()
        if not redis_url:
            raise RuntimeError("OGP_REDIS_URL is required when OGP_QUEUE_PROVIDER=redis")
        return RedisQueueProvider(redis_url=redis_url)
    return LocalQueueProvider()
