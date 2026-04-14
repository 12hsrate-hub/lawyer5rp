from __future__ import annotations

import json
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ogp_web.db.types import DatabaseBackend
from ogp_web.providers.queue_provider import QueueProvider, QueueMessage, build_queue_provider_from_env


TERMINAL_STATUSES = {"succeeded", "dead_lettered", "cancelled"}
ACTIVE_STATUSES = {"pending", "queued", "processing", "failed"}


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: int
    allow_manual_retry: bool = True
    allow_cancel: bool = True


JOB_POLICIES: dict[str, RetryPolicy] = {
    "document_generation": RetryPolicy(max_attempts=3, base_delay_seconds=10),
    "document_export": RetryPolicy(max_attempts=3, base_delay_seconds=10),
    "content_reindex": RetryPolicy(max_attempts=4, base_delay_seconds=30),
    "content_import": RetryPolicy(max_attempts=4, base_delay_seconds=30),
}


class AsyncJobService:
    def __init__(self, backend: DatabaseBackend, queue_provider: QueueProvider | None = None):
        self.backend = backend
        self.queue_provider = queue_provider or build_queue_provider_from_env()

    def _connect(self):
        return self.backend.connect()

    def _queue_publish(self, *, job: dict[str, Any]) -> None:
        payload_json = dict(job.get("payload_json") or {})
        self.queue_provider.publish(
            message=QueueMessage(
                job_id=int(job["id"]),
                server_scope=str(job.get("server_scope") or "server"),
                server_id=str(job.get("server_id") or "") or None,
                job_type=str(job.get("job_type") or ""),
                request_id=str(payload_json.get("request_id") or ""),
                publish_batch_id=int(payload_json["publish_batch_id"]) if payload_json.get("publish_batch_id") is not None else None,
                dedup_key=str(job.get("idempotency_key") or "") or None,
            )
        )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _decode_json(value: Any, *, default: Any):
        if value in (None, ""):
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except Exception:
            return default

    def _deserialize_job(self, row: Any) -> dict[str, Any]:
        payload = dict(row)
        payload["payload_json"] = self._decode_json(payload.get("payload_json"), default={})
        payload["result_json"] = self._decode_json(payload.get("result_json"), default={})
        payload["created_at"] = self._as_text(payload.get("created_at"))
        payload["updated_at"] = self._as_text(payload.get("updated_at"))
        payload["next_run_at"] = self._as_text(payload.get("next_run_at"))
        return payload

    def _deserialize_attempt(self, row: Any) -> dict[str, Any]:
        payload = dict(row)
        payload["error_details_json"] = self._decode_json(payload.get("error_details_json"), default={})
        payload["result_snapshot_json"] = self._decode_json(payload.get("result_snapshot_json"), default={})
        payload["started_at"] = self._as_text(payload.get("started_at"))
        payload["finished_at"] = self._as_text(payload.get("finished_at"))
        return payload

    def _validate_scope(self, *, server_scope: str, server_id: str | None) -> tuple[str, str | None]:
        normalized_scope = str(server_scope or "").strip().lower()
        normalized_server_id = str(server_id or "").strip().lower() or None
        if normalized_scope not in {"server", "global"}:
            raise ValueError("Некорректный server_scope для job.")
        if normalized_scope == "server" and not normalized_server_id:
            raise ValueError("server_id обязателен для server-scoped job.")
        if normalized_scope == "global":
            normalized_server_id = None
        return normalized_scope, normalized_server_id

    def _policy_for(self, job_type: str) -> RetryPolicy:
        try:
            return JOB_POLICIES[job_type]
        except KeyError as exc:
            raise ValueError(f"Неподдерживаемый тип job: {job_type}") from exc

    def _build_idempotency_key(self, *, job_type: str, entity_type: str, entity_id: int | None, payload_json: dict[str, Any], key: str | None) -> str | None:
        normalized_key = str(key or "").strip()
        if normalized_key:
            return normalized_key
        if job_type in {"document_generation", "document_export", "content_import"}:
            seed = {
                "job_type": job_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": payload_json,
            }
            return uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(seed, sort_keys=True, ensure_ascii=False)).hex
        return None

    def create_job(
        self,
        *,
        server_scope: str,
        server_id: str | None,
        job_type: str,
        entity_type: str,
        entity_id: int | None,
        payload_json: dict[str, Any],
        created_by: int | None,
        idempotency_key: str | None = None,
        enqueue: bool = True,
    ) -> dict[str, Any]:
        policy = self._policy_for(job_type)
        normalized_scope, normalized_server_id = self._validate_scope(server_scope=server_scope, server_id=server_id)
        resolved_key = self._build_idempotency_key(
            job_type=job_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload_json,
            key=idempotency_key,
        )
        with closing(self._connect()) as conn:
            if resolved_key:
                existing = conn.execute(
                    """
                    SELECT id, server_scope, server_id, job_type, status, entity_type, entity_id,
                           CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                           idempotency_key, attempt_count, max_attempts, next_run_at,
                           last_error_code, last_error_message, created_by, created_at, updated_at
                    FROM async_jobs
                    WHERE idempotency_key = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    (resolved_key,),
                ).fetchone()
                if existing is not None:
                    existing_payload = self._decode_json(existing.get("payload_json"), default={})
                    if existing_payload == payload_json and str(existing.get("status") or "") in ACTIVE_STATUSES.union({"succeeded"}):
                        return self._deserialize_job(existing)

            now = self._utc_now()
            next_status = "queued" if enqueue else "pending"
            row = conn.execute(
                """
                INSERT INTO async_jobs (
                    server_scope, server_id, job_type, status, entity_type, entity_id,
                    payload_json, result_json, idempotency_key,
                    attempt_count, max_attempts, next_run_at, created_by,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s::jsonb, '{}'::jsonb, %s,
                    0, %s, %s, %s,
                    NOW(), NOW()
                )
                RETURNING id, server_scope, server_id, job_type, status, entity_type, entity_id,
                          CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                          idempotency_key, attempt_count, max_attempts, next_run_at,
                          last_error_code, last_error_message, created_by, created_at, updated_at
                """,
                (
                    normalized_scope,
                    normalized_server_id,
                    job_type,
                    next_status,
                    entity_type,
                    entity_id,
                    json.dumps(payload_json, ensure_ascii=False),
                    resolved_key,
                    int(policy.max_attempts),
                    now,
                    created_by,
                ),
            ).fetchone()
            conn.commit()
            job = self._deserialize_job(row)
            if enqueue:
                self._queue_publish(job=job)
            return job

    def list_jobs(self, *, server_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, server_scope, server_id, job_type, status, entity_type, entity_id,
                       CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                       idempotency_key, attempt_count, max_attempts, next_run_at,
                       last_error_code, last_error_message, created_by, created_at, updated_at
                FROM async_jobs
                WHERE (server_scope = 'global' AND server_id IS NULL) OR (server_scope = 'server' AND server_id = %s)
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (server_id, max(1, min(int(limit), 200))),
            ).fetchall()
        return [self._deserialize_job(row) for row in rows]

    def get_job(self, *, job_id: int, server_id: str) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT id, server_scope, server_id, job_type, status, entity_type, entity_id,
                       CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                       idempotency_key, attempt_count, max_attempts, next_run_at,
                       last_error_code, last_error_message, created_by, created_at, updated_at
                FROM async_jobs
                WHERE id = %s
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            raise LookupError("Job не найдена.")
        item = self._deserialize_job(row)
        if item["server_scope"] == "server" and item.get("server_id") != server_id:
            raise PermissionError("Недостаточно прав для этой job.")
        return item

    def list_attempts(self, *, job_id: int, server_id: str) -> list[dict[str, Any]]:
        self.get_job(job_id=job_id, server_id=server_id)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, async_job_id, attempt_number, status, worker_id,
                       started_at, finished_at, error_code, error_message,
                       CAST(error_details_json AS TEXT) AS error_details_json,
                       CAST(result_snapshot_json AS TEXT) AS result_snapshot_json
                FROM job_attempts
                WHERE async_job_id = %s
                ORDER BY attempt_number ASC, id ASC
                """,
                (job_id,),
            ).fetchall()
        return [self._deserialize_attempt(row) for row in rows]

    def claim_available_jobs(self, *, worker_id: str, server_id: str | None, limit: int = 10) -> list[dict[str, Any]]:
        claimed: list[dict[str, Any]] = []
        with closing(self._connect()) as conn:
            conn.execute("BEGIN")
            rows = conn.execute(
                """
                SELECT id
                FROM async_jobs
                WHERE status IN ('queued', 'pending', 'failed')
                  AND next_run_at <= NOW()
                  AND (
                    server_scope = 'global'
                    OR (%s IS NOT NULL AND server_scope = 'server' AND server_id = %s)
                  )
                ORDER BY next_run_at ASC, id ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (server_id, server_id, max(1, min(int(limit), 100))),
            ).fetchall()
            for row in rows:
                job_id = int(row["id"])
                job = conn.execute(
                    """
                    UPDATE async_jobs
                    SET status = 'processing', updated_at = NOW(), last_error_code = NULL, last_error_message = NULL
                    WHERE id = %s
                    RETURNING id, server_scope, server_id, job_type, status, entity_type, entity_id,
                              CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                              idempotency_key, attempt_count, max_attempts, next_run_at,
                              last_error_code, last_error_message, created_by, created_at, updated_at
                    """,
                    (job_id,),
                ).fetchone()
                attempt_number = int(job["attempt_count"] or 0) + 1
                conn.execute(
                    """
                    INSERT INTO job_attempts (
                        async_job_id, attempt_number, status, worker_id, started_at,
                        error_details_json, result_snapshot_json
                    ) VALUES (%s, %s, 'started', %s, NOW(), '{}'::jsonb, '{}'::jsonb)
                    """,
                    (job_id, attempt_number, worker_id),
                )
                claimed.append(self._deserialize_job(job))
            conn.commit()
        return claimed

    def claim_job_by_id(self, *, job_id: int, worker_id: str, server_id: str | None) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN")
            row = conn.execute(
                """
                SELECT id
                FROM async_jobs
                WHERE id = %s
                  AND status IN ('queued', 'pending', 'failed')
                  AND next_run_at <= NOW()
                  AND (
                    server_scope = 'global'
                    OR (%s IS NOT NULL AND server_scope = 'server' AND server_id = %s)
                  )
                FOR UPDATE SKIP LOCKED
                """,
                (job_id, server_id, server_id),
            ).fetchone()
            if row is None:
                conn.rollback()
                return None
            job = conn.execute(
                """
                UPDATE async_jobs
                SET status = 'processing', updated_at = NOW(), last_error_code = NULL, last_error_message = NULL
                WHERE id = %s
                RETURNING id, server_scope, server_id, job_type, status, entity_type, entity_id,
                          CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                          idempotency_key, attempt_count, max_attempts, next_run_at,
                          last_error_code, last_error_message, created_by, created_at, updated_at
                """,
                (job_id,),
            ).fetchone()
            attempt_number = int(job["attempt_count"] or 0) + 1
            conn.execute(
                """
                INSERT INTO job_attempts (
                    async_job_id, attempt_number, status, worker_id, started_at,
                    error_details_json, result_snapshot_json
                ) VALUES (%s, %s, 'started', %s, NOW(), '{}'::jsonb, '{}'::jsonb)
                """,
                (job_id, attempt_number, worker_id),
            )
            conn.commit()
        return self._deserialize_job(job)

    def mark_succeeded(self, *, job_id: int, worker_id: str, result_json: dict[str, Any]) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE job_attempts
                SET status = 'succeeded', finished_at = NOW(), result_snapshot_json = %s::jsonb
                WHERE async_job_id = %s AND worker_id = %s AND status = 'started'
                """,
                (json.dumps(result_json, ensure_ascii=False), job_id, worker_id),
            )
            row = conn.execute(
                """
                UPDATE async_jobs
                SET status = 'succeeded', attempt_count = attempt_count + 1,
                    result_json = %s::jsonb, updated_at = NOW(), last_error_code = NULL, last_error_message = NULL
                WHERE id = %s
                RETURNING id, server_scope, server_id, job_type, status, entity_type, entity_id,
                          CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                          idempotency_key, attempt_count, max_attempts, next_run_at,
                          last_error_code, last_error_message, created_by, created_at, updated_at
                """,
                (json.dumps(result_json, ensure_ascii=False), job_id),
            ).fetchone()
            conn.commit()
        return self._deserialize_job(row)

    def mark_failed(
        self,
        *,
        job_id: int,
        worker_id: str,
        error_code: str,
        error_message: str,
        error_details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT id, server_scope, server_id, job_type, status, entity_type, entity_id,
                       CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                       idempotency_key, attempt_count, max_attempts, next_run_at,
                       last_error_code, last_error_message, created_by, created_at, updated_at
                FROM async_jobs WHERE id = %s LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                raise LookupError("Job не найдена.")
            attempt_count = int(row["attempt_count"] or 0) + 1
            max_attempts = int(row["max_attempts"] or 1)
            policy = self._policy_for(str(row["job_type"]))
            conn.execute(
                """
                UPDATE job_attempts
                SET status = 'failed', finished_at = NOW(),
                    error_code = %s, error_message = %s, error_details_json = %s::jsonb
                WHERE async_job_id = %s AND worker_id = %s AND status = 'started'
                """,
                (error_code, error_message[:1000], json.dumps(error_details or {}, ensure_ascii=False), job_id, worker_id),
            )

            if attempt_count >= max_attempts:
                job_row = conn.execute(
                    """
                    UPDATE async_jobs
                    SET status = 'dead_lettered', attempt_count = %s, updated_at = NOW(),
                        last_error_code = %s, last_error_message = %s
                    WHERE id = %s
                    RETURNING id, server_scope, server_id, job_type, status, entity_type, entity_id,
                              CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                              idempotency_key, attempt_count, max_attempts, next_run_at,
                              last_error_code, last_error_message, created_by, created_at, updated_at
                    """,
                    (attempt_count, error_code, error_message[:1000], job_id),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO job_dead_letters (
                        async_job_id, dead_letter_reason, payload_snapshot_json,
                        last_error_code, last_error_message, created_at
                    ) VALUES (%s, %s, %s::jsonb, %s, %s, NOW())
                    """,
                    (
                        job_id,
                        "max_attempts_exceeded",
                        row["payload_json"],
                        error_code,
                        error_message[:1000],
                    ),
                )
                self.queue_provider.dead_letter(
                    message=QueueMessage(
                        job_id=job_id,
                        server_scope=str(row.get("server_scope") or "server"),
                        server_id=str(row.get("server_id") or "") or None,
                        job_type=str(row.get("job_type") or ""),
                        request_id=str(self._decode_json(row.get("payload_json"), default={}).get("request_id") or ""),
                        publish_batch_id=self._decode_json(row.get("payload_json"), default={}).get("publish_batch_id"),
                        dedup_key=str(row.get("idempotency_key") or "") or None,
                    ),
                    reason="max_attempts_exceeded",
                )
            else:
                delay_seconds = policy.base_delay_seconds * (2 ** (attempt_count - 1))
                next_run_at = self._utc_now() + timedelta(seconds=delay_seconds)
                job_row = conn.execute(
                    """
                    UPDATE async_jobs
                    SET status = 'queued', attempt_count = %s, updated_at = NOW(),
                        next_run_at = %s,
                        last_error_code = %s, last_error_message = %s
                    WHERE id = %s
                    RETURNING id, server_scope, server_id, job_type, status, entity_type, entity_id,
                              CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                              idempotency_key, attempt_count, max_attempts, next_run_at,
                              last_error_code, last_error_message, created_by, created_at, updated_at
                    """,
                    (attempt_count, next_run_at, error_code, error_message[:1000], job_id),
                ).fetchone()
                self._queue_publish(job=self._deserialize_job(job_row))
            conn.commit()
        return self._deserialize_job(job_row)

    def retry_job(self, *, job_id: int, server_id: str) -> dict[str, Any]:
        job = self.get_job(job_id=job_id, server_id=server_id)
        policy = self._policy_for(job["job_type"])
        if not policy.allow_manual_retry:
            raise ValueError("Manual retry отключён для этого типа job.")
        if job["status"] not in {"failed", "dead_lettered", "cancelled"}:
            raise ValueError("Job не находится в состоянии для ручного retry.")
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                UPDATE async_jobs
                SET status = 'queued', next_run_at = NOW(), updated_at = NOW(),
                    last_error_code = NULL, last_error_message = NULL
                WHERE id = %s
                RETURNING id, server_scope, server_id, job_type, status, entity_type, entity_id,
                          CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                          idempotency_key, attempt_count, max_attempts, next_run_at,
                          last_error_code, last_error_message, created_by, created_at, updated_at
                """,
                (job_id,),
            ).fetchone()
            conn.commit()
        job_row = self._deserialize_job(row)
        self._queue_publish(job=job_row)
        return job_row

    def cancel_job(self, *, job_id: int, server_id: str) -> dict[str, Any]:
        job = self.get_job(job_id=job_id, server_id=server_id)
        policy = self._policy_for(job["job_type"])
        if not policy.allow_cancel:
            raise ValueError("Cancel отключён для этого типа job.")
        if job["status"] in TERMINAL_STATUSES:
            raise ValueError("Job уже завершена.")
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                UPDATE async_jobs
                SET status = 'cancelled', updated_at = NOW()
                WHERE id = %s
                RETURNING id, server_scope, server_id, job_type, status, entity_type, entity_id,
                          CAST(payload_json AS TEXT) AS payload_json, CAST(result_json AS TEXT) AS result_json,
                          idempotency_key, attempt_count, max_attempts, next_run_at,
                          last_error_code, last_error_message, created_by, created_at, updated_at
                """,
                (job_id,),
            ).fetchone()
            conn.commit()
        return self._deserialize_job(row)
