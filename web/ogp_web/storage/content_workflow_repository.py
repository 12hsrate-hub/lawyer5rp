from __future__ import annotations

import json
from typing import Any

from ogp_web.db.types import DatabaseBackend, DbConnectionLike


class ContentWorkflowRepository:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    def _connect(self) -> DbConnectionLike:
        return self.backend.connect()

    @staticmethod
    def _json_load(value: Any) -> Any:
        if value in (None, ""):
            return {}
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except Exception:
            return {}

    @staticmethod
    def _json_dump(value: Any) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)

    def _fetchone(self, conn: DbConnectionLike, query: str, params: tuple[Any, ...]):
        return conn.execute(query, params).fetchone()

    def _fetchall(self, conn: DbConnectionLike, query: str, params: tuple[Any, ...]):
        return conn.execute(query, params).fetchall()

    def list_content_items(self, *, server_scope: str, server_id: str | None, content_type: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = self._fetchall(
                conn,
                """
                SELECT id, server_scope, server_id, content_type, content_key, title, status,
                       current_published_version_id, CAST(metadata_json AS TEXT) AS metadata_json,
                       created_at, updated_at
                FROM content_items
                WHERE server_scope = %s
                  AND (((%s)::text IS NULL AND server_id IS NULL) OR server_id = (%s)::text)
                  AND (%s = '' OR content_type = %s)
                ORDER BY updated_at DESC, id DESC
                """,
                (server_scope, server_id, server_id, str(content_type or ""), str(content_type or "")),
            )
            return [self._map_content_item(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def get_content_item(self, *, content_item_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = self._fetchone(
                conn,
                """
                SELECT id, server_scope, server_id, content_type, content_key, title, status,
                       current_published_version_id, CAST(metadata_json AS TEXT) AS metadata_json,
                       created_at, updated_at
                FROM content_items
                WHERE id = %s
                LIMIT 1
                """,
                (content_item_id,),
            )
            return self._map_content_item(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def get_content_item_by_identity(
        self,
        *,
        server_scope: str,
        server_id: str | None,
        content_type: str,
        content_key: str,
    ) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = self._fetchone(
                conn,
                """
                SELECT id, server_scope, server_id, content_type, content_key, title, status,
                       current_published_version_id, CAST(metadata_json AS TEXT) AS metadata_json,
                       created_at, updated_at
                FROM content_items
                WHERE server_scope = %s
                  AND (((%s)::text IS NULL AND server_id IS NULL) OR server_id = (%s)::text)
                  AND content_type = %s
                  AND content_key = %s
                LIMIT 1
                """,
                (server_scope, server_id, server_id, content_type, content_key),
            )
            return self._map_content_item(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def create_content_item(
        self,
        *,
        server_scope: str,
        server_id: str | None,
        content_type: str,
        content_key: str,
        title: str,
        status: str = "draft",
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                INSERT INTO content_items (server_scope, server_id, content_type, content_key, title, status, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id, server_scope, server_id, content_type, content_key, title, status,
                          current_published_version_id, CAST(metadata_json AS TEXT) AS metadata_json,
                          created_at, updated_at
                """,
                (server_scope, server_id, content_type, content_key, title, status, self._json_dump(metadata_json or {})),
            ).fetchone()
            conn.commit()
            return self._map_content_item(row)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def list_content_versions(self, *, content_item_id: int) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = self._fetchall(
                conn,
                """
                SELECT id, content_item_id, version_number, CAST(payload_json AS TEXT) AS payload_json,
                       schema_version, created_by, created_at
                FROM content_versions
                WHERE content_item_id = %s
                ORDER BY version_number ASC
                """,
                (content_item_id,),
            )
            return [self._map_content_version(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def create_content_version(
        self,
        *,
        content_item_id: int,
        payload_json: dict[str, Any],
        schema_version: int,
        created_by: int,
    ) -> dict[str, Any]:
        conn = self._connect()
        try:
            last = conn.execute(
                """
                SELECT version_number
                FROM content_versions
                WHERE content_item_id = %s
                ORDER BY version_number DESC
                LIMIT 1
                """,
                (content_item_id,),
            ).fetchone()
            next_version = int(last["version_number"]) + 1 if last else 1
            row = conn.execute(
                """
                INSERT INTO content_versions (content_item_id, version_number, payload_json, schema_version, created_by)
                VALUES (%s, %s, %s::jsonb, %s, %s)
                RETURNING id, content_item_id, version_number, CAST(payload_json AS TEXT) AS payload_json,
                          schema_version, created_by, created_at
                """,
                (content_item_id, next_version, self._json_dump(payload_json), schema_version, created_by),
            ).fetchone()
            conn.commit()
            return self._map_content_version(row)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def get_content_version(self, *, version_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = self._fetchone(
                conn,
                """
                SELECT id, content_item_id, version_number, CAST(payload_json AS TEXT) AS payload_json,
                       schema_version, created_by, created_at
                FROM content_versions
                WHERE id = %s
                LIMIT 1
                """,
                (version_id,),
            )
            return self._map_content_version(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def create_change_request(
        self,
        *,
        content_item_id: int,
        base_version_id: int | None,
        candidate_version_id: int,
        status: str,
        proposed_by: int,
        comment: str,
    ) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                INSERT INTO change_requests (content_item_id, base_version_id, candidate_version_id, status, proposed_by, comment)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, content_item_id, base_version_id, candidate_version_id, status, proposed_by, comment, created_at, updated_at
                """,
                (content_item_id, base_version_id, candidate_version_id, status, proposed_by, comment),
            ).fetchone()
            conn.commit()
            return dict(row)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def get_change_request(self, *, change_request_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = self._fetchone(
                conn,
                """
                SELECT id, content_item_id, base_version_id, candidate_version_id, status, proposed_by, comment, created_at, updated_at
                FROM change_requests
                WHERE id = %s
                LIMIT 1
                """,
                (change_request_id,),
            )
            return dict(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def update_change_request_status(self, *, change_request_id: int, status: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                UPDATE change_requests
                SET status = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id, content_item_id, base_version_id, candidate_version_id, status, proposed_by, comment, created_at, updated_at
                """,
                (status, change_request_id),
            ).fetchone()
            conn.commit()
            return dict(row)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def list_change_requests(self, *, content_item_id: int) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = self._fetchall(
                conn,
                """
                SELECT id, content_item_id, base_version_id, candidate_version_id, status, proposed_by, comment, created_at, updated_at
                FROM change_requests
                WHERE content_item_id = %s
                ORDER BY created_at DESC, id DESC
                """,
                (content_item_id,),
            )
            return [dict(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def create_review(
        self,
        *,
        change_request_id: int,
        reviewer_user_id: int,
        decision: str,
        comment: str,
        diff_json: dict[str, Any],
    ) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                INSERT INTO reviews (change_request_id, reviewer_user_id, decision, comment, diff_json)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING id, change_request_id, reviewer_user_id, decision, comment,
                          CAST(diff_json AS TEXT) AS diff_json, created_at
                """,
                (change_request_id, reviewer_user_id, decision, comment, self._json_dump(diff_json)),
            ).fetchone()
            conn.commit()
            return self._map_review(row)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def list_reviews(self, *, change_request_id: int) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = self._fetchall(
                conn,
                """
                SELECT id, change_request_id, reviewer_user_id, decision, comment,
                       CAST(diff_json AS TEXT) AS diff_json, created_at
                FROM reviews
                WHERE change_request_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (change_request_id,),
            )
            return [self._map_review(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def create_publish_batch(
        self,
        *,
        server_scope: str,
        server_id: str | None,
        published_by: int,
        rollback_of_batch_id: int | None,
        summary_json: dict[str, Any],
    ) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                INSERT INTO publish_batches (server_scope, server_id, published_by, rollback_of_batch_id, summary_json)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING id, server_scope, server_id, published_by, rollback_of_batch_id,
                          CAST(summary_json AS TEXT) AS summary_json, created_at
                """,
                (server_scope, server_id, published_by, rollback_of_batch_id, self._json_dump(summary_json)),
            ).fetchone()
            conn.commit()
            return self._map_publish_batch(row)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def get_publish_batch(self, *, batch_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = self._fetchone(
                conn,
                """
                SELECT id, server_scope, server_id, published_by, rollback_of_batch_id,
                       CAST(summary_json AS TEXT) AS summary_json, created_at
                FROM publish_batches
                WHERE id = %s
                LIMIT 1
                """,
                (batch_id,),
            )
            return self._map_publish_batch(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def create_publish_batch_item(
        self,
        *,
        publish_batch_id: int,
        content_item_id: int,
        published_version_id: int,
        previous_published_version_id: int | None,
    ) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                INSERT INTO publish_batch_items (
                    publish_batch_id, content_item_id, published_version_id, previous_published_version_id
                )
                VALUES (%s, %s, %s, %s)
                RETURNING id, publish_batch_id, content_item_id, published_version_id, previous_published_version_id, created_at
                """,
                (publish_batch_id, content_item_id, published_version_id, previous_published_version_id),
            ).fetchone()
            conn.commit()
            return dict(row)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def list_publish_batch_items(self, *, publish_batch_id: int) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = self._fetchall(
                conn,
                """
                SELECT id, publish_batch_id, content_item_id, published_version_id, previous_published_version_id, created_at
                FROM publish_batch_items
                WHERE publish_batch_id = %s
                ORDER BY id ASC
                """,
                (publish_batch_id,),
            )
            return [dict(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def set_current_published_version(self, *, content_item_id: int, version_id: int | None, status: str = "published") -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                UPDATE content_items
                SET current_published_version_id = %s,
                    status = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, server_scope, server_id, content_type, content_key, title, status,
                          current_published_version_id, CAST(metadata_json AS TEXT) AS metadata_json,
                          created_at, updated_at
                """,
                (version_id, status, content_item_id),
            ).fetchone()
            conn.commit()
            return self._map_content_item(row)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def append_audit_log(
        self,
        *,
        server_id: str | None,
        actor_user_id: int | None,
        entity_type: str,
        entity_id: str,
        action: str,
        before_json: dict[str, Any] | None,
        after_json: dict[str, Any] | None,
        diff_json: dict[str, Any] | None,
        request_id: str,
        metadata_json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                INSERT INTO audit_logs (
                    server_id, actor_user_id, entity_type, entity_id, action,
                    before_json, after_json, diff_json, request_id, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb)
                RETURNING id, server_id, actor_user_id, entity_type, entity_id, action,
                          CAST(before_json AS TEXT) AS before_json,
                          CAST(after_json AS TEXT) AS after_json,
                          CAST(diff_json AS TEXT) AS diff_json,
                          request_id,
                          CAST(metadata_json AS TEXT) AS metadata_json,
                          created_at
                """,
                (
                    server_id,
                    actor_user_id,
                    entity_type,
                    entity_id,
                    action,
                    self._json_dump(before_json or {}),
                    self._json_dump(after_json or {}),
                    self._json_dump(diff_json or {}),
                    request_id,
                    self._json_dump(metadata_json or {}),
                ),
            ).fetchone()
            conn.commit()
            return self._map_audit_log(row)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    def list_audit_logs(
        self,
        *,
        server_id: str | None,
        entity_type: str = "",
        entity_id: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = self._fetchall(
                conn,
                """
                SELECT id, server_id, actor_user_id, entity_type, entity_id, action,
                       CAST(before_json AS TEXT) AS before_json,
                       CAST(after_json AS TEXT) AS after_json,
                       CAST(diff_json AS TEXT) AS diff_json,
                       request_id,
                       CAST(metadata_json AS TEXT) AS metadata_json,
                       created_at
                FROM audit_logs
                WHERE (((%s)::text IS NULL AND server_id IS NULL) OR server_id = (%s)::text)
                  AND (%s = '' OR entity_type = %s)
                  AND (%s = '' OR entity_id = %s)
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (server_id, server_id, entity_type, entity_type, entity_id, entity_id, max(1, int(limit or 100))),
            )
            return [self._map_audit_log(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc
        finally:
            conn.close()

    @staticmethod
    def _map_content_item(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **dict(row),
            "metadata_json": ContentWorkflowRepository._json_load(row.get("metadata_json")),
        }

    @staticmethod
    def _map_content_version(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **dict(row),
            "payload_json": ContentWorkflowRepository._json_load(row.get("payload_json")),
        }

    @staticmethod
    def _map_review(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **dict(row),
            "diff_json": ContentWorkflowRepository._json_load(row.get("diff_json")),
        }

    @staticmethod
    def _map_publish_batch(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **dict(row),
            "summary_json": ContentWorkflowRepository._json_load(row.get("summary_json")),
        }

    @staticmethod
    def _map_audit_log(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **dict(row),
            "before_json": ContentWorkflowRepository._json_load(row.get("before_json")),
            "after_json": ContentWorkflowRepository._json_load(row.get("after_json")),
            "diff_json": ContentWorkflowRepository._json_load(row.get("diff_json")),
            "metadata_json": ContentWorkflowRepository._json_load(row.get("metadata_json")),
        }
