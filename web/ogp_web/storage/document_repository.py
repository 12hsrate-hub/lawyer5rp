from __future__ import annotations

import json
from typing import Any

from ogp_web.db.types import DatabaseBackend


class DocumentRepository:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    def _connect(self):
        return self.backend.connect()

    def _fetchone(self, query: str, params: tuple[Any, ...]):
        try:
            return self._connect().execute(query, params).fetchone()
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc

    def _fetchall(self, query: str, params: tuple[Any, ...]):
        try:
            return self._connect().execute(query, params).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc

    def _execute(self, query: str, params: tuple[Any, ...], *, commit: bool = True):
        conn = self._connect()
        try:
            cursor = conn.execute(query, params)
            if commit:
                conn.commit()
            return cursor
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc

    def create_case_document(self, *, case_id: int, server_id: str, document_type: str, created_by: int):
        cursor = self._execute(
            """
            INSERT INTO case_documents (case_id, server_id, document_type, status, created_by, metadata_json)
            VALUES (%s, %s, %s, 'draft', %s, '{}'::jsonb)
            RETURNING id, case_id, server_id, document_type, status, created_by, latest_version_id, CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at
            """,
            (case_id, server_id, document_type, created_by),
        )
        return cursor.fetchone()

    def list_case_documents(self, *, case_id: int):
        return self._fetchall(
            """
            SELECT id, case_id, server_id, document_type, status, created_by, latest_version_id, CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at
            FROM case_documents
            WHERE case_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (case_id,),
        )

    def get_case_document(self, *, document_id: int):
        return self._fetchone(
            """
            SELECT id, case_id, server_id, document_type, status, created_by, latest_version_id, CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at
            FROM case_documents
            WHERE id = %s
            LIMIT 1
            """,
            (document_id,),
        )

    def list_document_versions(self, *, document_id: int):
        return self._fetchall(
            """
            SELECT id, document_id, version_number, CAST(content_json AS TEXT) AS content_json, created_by, generation_snapshot_id, created_at
            FROM document_versions
            WHERE document_id = %s
            ORDER BY version_number ASC
            """,
            (document_id,),
        )

    def create_document_version(self, *, document_id: int, content_json: Any, created_by: int, generation_snapshot_id: int | None = None):
        conn = self._connect()
        try:
            last = conn.execute(
                """
                SELECT version_number
                FROM document_versions
                WHERE document_id = %s
                ORDER BY version_number DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
            next_version = int(last["version_number"]) + 1 if last else 1
            row = conn.execute(
                """
                INSERT INTO document_versions (document_id, version_number, content_json, created_by, generation_snapshot_id)
                VALUES (%s, %s, %s::jsonb, %s, %s)
                RETURNING id, document_id, version_number, CAST(content_json AS TEXT) AS content_json, created_by, generation_snapshot_id, created_at
                """,
                (document_id, next_version, json.dumps(content_json, ensure_ascii=False), created_by, generation_snapshot_id),
            ).fetchone()
            conn.execute(
                """
                UPDATE case_documents
                SET latest_version_id = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (int(row["id"]), document_id),
            )
            conn.commit()
            return row
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc

    def transition_case_document_status(self, *, document_id: int, next_status: str, actor_user_id: int):
        cursor = self._execute(
            """
            UPDATE case_documents
            SET status = %s,
                updated_at = NOW(),
                metadata_json = jsonb_set(
                    COALESCE(metadata_json, '{}'::jsonb),
                    '{status_actor_user_id}',
                    to_jsonb(%s::bigint),
                    true
                )
            WHERE id = %s
            RETURNING id, case_id, server_id, document_type, status, created_by, latest_version_id, CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at
            """,
            (next_status, actor_user_id, document_id),
        )
        return cursor.fetchone()
