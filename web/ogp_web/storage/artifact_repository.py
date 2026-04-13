from __future__ import annotations

import json
from typing import Any

from ogp_web.db.types import DatabaseBackend


class ArtifactRepository:
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

    def get_user_id_by_username(self, username: str) -> int | None:
        row = self._fetchone("SELECT id FROM users WHERE username = %s", (username,))
        return int(row["id"]) if row else None

    def get_document_version(self, *, version_id: int):
        return self._fetchone(
            """
            SELECT dv.id, dv.document_id, dv.version_number, CAST(dv.content_json AS TEXT) AS content_json,
                   d.server_id, d.case_id
            FROM document_versions dv
            JOIN case_documents d ON d.id = dv.document_id
            WHERE dv.id = %s
            LIMIT 1
            """,
            (version_id,),
        )

    def create_attachment(
        self,
        *,
        server_id: str,
        uploaded_by: int,
        storage_key: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        checksum: str,
        upload_status: str,
        metadata_json: dict[str, Any],
    ):
        return self._execute(
            """
            INSERT INTO attachments (
                server_id, uploaded_by, storage_key, filename, mime_type, size_bytes,
                checksum, upload_status, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id, server_id, uploaded_by, storage_key, filename, mime_type,
                      size_bytes, checksum, upload_status, CAST(metadata_json AS TEXT) AS metadata_json, created_at
            """,
            (
                server_id,
                uploaded_by,
                storage_key,
                filename,
                mime_type,
                int(size_bytes),
                checksum,
                upload_status,
                json.dumps(metadata_json, ensure_ascii=False),
            ),
        ).fetchone()

    def create_document_version_attachment_link(
        self,
        *,
        document_version_id: int,
        attachment_id: int,
        link_type: str,
        created_by: int,
    ):
        return self._execute(
            """
            INSERT INTO document_version_attachment_links (document_version_id, attachment_id, link_type, created_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (document_version_id, attachment_id) DO NOTHING
            RETURNING id, document_version_id, attachment_id, link_type, created_by, created_at
            """,
            (document_version_id, attachment_id, link_type, created_by),
        ).fetchone()

    def get_attachment(self, *, attachment_id: int):
        return self._fetchone(
            """
            SELECT id, server_id, uploaded_by, storage_key, filename, mime_type,
                   size_bytes, checksum, upload_status, CAST(metadata_json AS TEXT) AS metadata_json, created_at
            FROM attachments
            WHERE id = %s
            LIMIT 1
            """,
            (attachment_id,),
        )

    def get_attachment_with_version(self, *, attachment_id: int):
        return self._fetchone(
            """
            SELECT a.id, a.server_id, a.uploaded_by, a.storage_key, a.filename, a.mime_type,
                   a.size_bytes, a.checksum, a.upload_status, CAST(a.metadata_json AS TEXT) AS metadata_json,
                   l.document_version_id, d.server_id AS document_server_id
            FROM attachments a
            JOIN document_version_attachment_links l ON l.attachment_id = a.id
            JOIN document_versions dv ON dv.id = l.document_version_id
            JOIN case_documents d ON d.id = dv.document_id
            WHERE a.id = %s
            ORDER BY l.id ASC
            LIMIT 1
            """,
            (attachment_id,),
        )

    def list_attachments_for_document_version(self, *, document_version_id: int):
        return self._fetchall(
            """
            SELECT a.id, a.server_id, a.uploaded_by, a.storage_key, a.filename, a.mime_type,
                   a.size_bytes, a.checksum, a.upload_status, CAST(a.metadata_json AS TEXT) AS metadata_json,
                   a.created_at, l.link_type, l.created_by, l.created_at AS linked_at
            FROM document_version_attachment_links l
            JOIN attachments a ON a.id = l.attachment_id
            WHERE l.document_version_id = %s
            ORDER BY l.created_at DESC, l.id DESC
            """,
            (document_version_id,),
        )

    def delete_attachment_link(self, *, document_version_id: int, attachment_id: int) -> int:
        return int(
            self._execute(
                """
                DELETE FROM document_version_attachment_links
                WHERE document_version_id = %s AND attachment_id = %s
                """,
                (document_version_id, attachment_id),
            ).rowcount
            or 0
        )

    def update_attachment_upload_status(
        self,
        *,
        attachment_id: int,
        upload_status: str,
        mime_type: str,
        size_bytes: int,
        checksum: str,
        metadata_json: dict[str, Any],
    ):
        return self._execute(
            """
            UPDATE attachments
            SET upload_status = %s,
                mime_type = %s,
                size_bytes = %s,
                checksum = %s,
                metadata_json = %s::jsonb
            WHERE id = %s
            RETURNING id, server_id, uploaded_by, storage_key, filename, mime_type,
                      size_bytes, checksum, upload_status, CAST(metadata_json AS TEXT) AS metadata_json, created_at
            """,
            (
                upload_status,
                mime_type,
                int(size_bytes),
                checksum,
                json.dumps(metadata_json, ensure_ascii=False),
                attachment_id,
            ),
        ).fetchone()

    def create_export(
        self,
        *,
        document_version_id: int,
        server_id: str,
        export_format: str,
        status: str,
        storage_key: str,
        mime_type: str,
        size_bytes: int,
        checksum: str,
        created_by: int,
        job_run_id: str | None,
        metadata_json: dict[str, Any],
    ):
        return self._execute(
            """
            INSERT INTO exports (
                document_version_id, server_id, format, status, storage_key, mime_type,
                size_bytes, checksum, created_by, job_run_id, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id, document_version_id, server_id, format, status, storage_key,
                      mime_type, size_bytes, checksum, created_by, job_run_id,
                      CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at
            """,
            (
                document_version_id,
                server_id,
                export_format,
                status,
                storage_key,
                mime_type,
                int(size_bytes),
                checksum,
                created_by,
                job_run_id,
                json.dumps(metadata_json, ensure_ascii=False),
            ),
        ).fetchone()

    def update_export(
        self,
        *,
        export_id: int,
        status: str,
        storage_key: str,
        mime_type: str,
        size_bytes: int,
        checksum: str,
        job_run_id: str | None,
        metadata_json: dict[str, Any],
    ):
        return self._execute(
            """
            UPDATE exports
            SET status = %s,
                storage_key = %s,
                mime_type = %s,
                size_bytes = %s,
                checksum = %s,
                job_run_id = %s,
                metadata_json = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, document_version_id, server_id, format, status, storage_key,
                      mime_type, size_bytes, checksum, created_by, job_run_id,
                      CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at
            """,
            (
                status,
                storage_key,
                mime_type,
                int(size_bytes),
                checksum,
                job_run_id,
                json.dumps(metadata_json, ensure_ascii=False),
                export_id,
            ),
        ).fetchone()

    def get_export(self, *, export_id: int):
        return self._fetchone(
            """
            SELECT e.id, e.document_version_id, e.server_id, e.format, e.status, e.storage_key,
                   e.mime_type, e.size_bytes, e.checksum, e.created_by, e.job_run_id,
                   CAST(e.metadata_json AS TEXT) AS metadata_json, e.created_at, e.updated_at,
                   d.server_id AS document_server_id
            FROM exports e
            JOIN document_versions dv ON dv.id = e.document_version_id
            JOIN case_documents d ON d.id = dv.document_id
            WHERE e.id = %s
            LIMIT 1
            """,
            (export_id,),
        )

    def list_exports_for_document_version(self, *, document_version_id: int):
        return self._fetchall(
            """
            SELECT id, document_version_id, server_id, format, status, storage_key,
                   mime_type, size_bytes, checksum, created_by, job_run_id,
                   CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at
            FROM exports
            WHERE document_version_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (document_version_id,),
        )
