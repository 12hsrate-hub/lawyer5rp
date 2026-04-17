from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from ogp_web.db.types import DatabaseBackend


@dataclass(frozen=True)
class RuntimeServerPackRecord:
    id: int
    server_code: str
    version: int
    status: str
    metadata_json: dict[str, Any]
    created_at: str
    published_at: str


class RuntimeServerPacksStore:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    @staticmethod
    def _normalize_code(value: str) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _row_to_record(row: dict[str, Any] | None) -> RuntimeServerPackRecord | None:
        if row is None:
            return None
        return RuntimeServerPackRecord(
            id=int(row.get("id") or 0),
            server_code=str(row.get("server_code") or "").strip().lower(),
            version=int(row.get("version") or 0),
            status=str(row.get("status") or "draft"),
            metadata_json=dict(row.get("metadata_json") or {}),
            created_at=str(row.get("created_at") or ""),
            published_at=str(row.get("published_at") or ""),
        )

    def get_latest_published_pack(self, *, server_code: str) -> RuntimeServerPackRecord | None:
        normalized_code = self._normalize_code(server_code)
        if not normalized_code:
            return None
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                SELECT id, server_code, version, status, metadata_json, created_at, published_at
                FROM server_packs
                WHERE server_code = %s AND status = 'published'
                ORDER BY published_at DESC NULLS LAST, version DESC, id DESC
                LIMIT 1
                """,
                (normalized_code,),
            ).fetchone()
            return self._row_to_record(row)
        finally:
            conn.close()

    def get_published_pack_by_version(self, *, server_code: str, version: int) -> RuntimeServerPackRecord | None:
        normalized_code = self._normalize_code(server_code)
        normalized_version = int(version or 0)
        if not normalized_code or normalized_version <= 0:
            return None
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                SELECT id, server_code, version, status, metadata_json, created_at, published_at
                FROM server_packs
                WHERE server_code = %s AND status = 'published' AND version = %s
                LIMIT 1
                """,
                (normalized_code, normalized_version),
            ).fetchone()
            return self._row_to_record(row)
        finally:
            conn.close()

    def get_previous_published_pack(self, *, server_code: str) -> RuntimeServerPackRecord | None:
        normalized_code = self._normalize_code(server_code)
        if not normalized_code:
            return None
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                SELECT id, server_code, version, status, metadata_json, created_at, published_at
                FROM server_packs
                WHERE server_code = %s AND status = 'published'
                ORDER BY published_at DESC NULLS LAST, version DESC, id DESC
                OFFSET 1
                LIMIT 1
                """,
                (normalized_code,),
            ).fetchone()
            return self._row_to_record(row)
        finally:
            conn.close()

    def get_latest_draft_pack(self, *, server_code: str) -> RuntimeServerPackRecord | None:
        normalized_code = self._normalize_code(server_code)
        if not normalized_code:
            return None
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                SELECT id, server_code, version, status, metadata_json, created_at, published_at
                FROM server_packs
                WHERE server_code = %s AND status = 'draft'
                ORDER BY version DESC, id DESC
                LIMIT 1
                """,
                (normalized_code,),
            ).fetchone()
            return self._row_to_record(row)
        finally:
            conn.close()

    def save_draft_pack(self, *, server_code: str, metadata_json: dict[str, Any]) -> RuntimeServerPackRecord:
        normalized_code = self._normalize_code(server_code)
        if not normalized_code:
            raise ValueError("server_code_required")
        normalized_metadata = json.loads(json.dumps(dict(metadata_json or {}), ensure_ascii=False))
        conn = self.backend.connect()
        try:
            draft_row = conn.execute(
                """
                SELECT id, server_code, version, status, metadata_json, created_at, published_at
                FROM server_packs
                WHERE server_code = %s AND status = 'draft'
                ORDER BY version DESC, id DESC
                LIMIT 1
                """,
                (normalized_code,),
            ).fetchone()
            if draft_row is not None:
                row = conn.execute(
                    """
                    UPDATE server_packs
                    SET metadata_json = %s::jsonb
                    WHERE id = %s
                    RETURNING id, server_code, version, status, metadata_json, created_at, published_at
                    """,
                    (json.dumps(normalized_metadata, ensure_ascii=False), int(draft_row.get("id") or 0)),
                ).fetchone()
            else:
                latest_published = conn.execute(
                    """
                    SELECT version
                    FROM server_packs
                    WHERE server_code = %s AND status = 'published'
                    ORDER BY published_at DESC NULLS LAST, version DESC, id DESC
                    LIMIT 1
                    """,
                    (normalized_code,),
                ).fetchone()
                next_version = int((latest_published or {}).get("version") or 0) + 1
                row = conn.execute(
                    """
                    INSERT INTO server_packs (server_code, version, status, metadata_json)
                    VALUES (%s, %s, 'draft', %s::jsonb)
                    RETURNING id, server_code, version, status, metadata_json, created_at, published_at
                    """,
                    (normalized_code, next_version, json.dumps(normalized_metadata, ensure_ascii=False)),
                ).fetchone()
            conn.commit()
            if row is None:
                raise RuntimeError("server_pack_draft_save_failed")
            return self._row_to_record(row)  # type: ignore[return-value]
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def publish_latest_draft_pack(self, *, server_code: str) -> RuntimeServerPackRecord:
        normalized_code = self._normalize_code(server_code)
        if not normalized_code:
            raise ValueError("server_code_required")
        conn = self.backend.connect()
        try:
            draft_row = conn.execute(
                """
                SELECT id
                FROM server_packs
                WHERE server_code = %s AND status = 'draft'
                ORDER BY version DESC, id DESC
                LIMIT 1
                """,
                (normalized_code,),
            ).fetchone()
            if draft_row is None:
                raise KeyError("server_pack_draft_not_found")
            row = conn.execute(
                """
                UPDATE server_packs
                SET status = 'published', published_at = NOW()
                WHERE id = %s
                RETURNING id, server_code, version, status, metadata_json, created_at, published_at
                """,
                (int(draft_row.get("id") or 0),),
            ).fetchone()
            conn.commit()
            if row is None:
                raise RuntimeError("server_pack_publish_failed")
            return self._row_to_record(row)  # type: ignore[return-value]
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def rollback_to_published_pack(self, *, server_code: str, target_version: int | None = None) -> RuntimeServerPackRecord:
        normalized_code = self._normalize_code(server_code)
        normalized_target_version = int(target_version or 0) or None
        if not normalized_code:
            raise ValueError("server_code_required")
        conn = self.backend.connect()
        try:
            current_row = conn.execute(
                """
                SELECT id, server_code, version, status, metadata_json, created_at, published_at
                FROM server_packs
                WHERE server_code = %s AND status = 'published'
                ORDER BY published_at DESC NULLS LAST, version DESC, id DESC
                LIMIT 1
                """,
                (normalized_code,),
            ).fetchone()
            if current_row is None:
                raise KeyError("server_pack_published_not_found")
            if normalized_target_version is None:
                target_row = conn.execute(
                    """
                    SELECT id, server_code, version, status, metadata_json, created_at, published_at
                    FROM server_packs
                    WHERE server_code = %s AND status = 'published'
                    ORDER BY published_at DESC NULLS LAST, version DESC, id DESC
                    OFFSET 1
                    LIMIT 1
                    """,
                    (normalized_code,),
                ).fetchone()
            else:
                target_row = conn.execute(
                    """
                    SELECT id, server_code, version, status, metadata_json, created_at, published_at
                    FROM server_packs
                    WHERE server_code = %s AND status = 'published' AND version = %s
                    LIMIT 1
                    """,
                    (normalized_code, normalized_target_version),
                ).fetchone()
            if target_row is None:
                raise KeyError("server_pack_rollback_target_not_found")
            if int(target_row.get("id") or 0) == int(current_row.get("id") or 0):
                raise ValueError("server_pack_rollback_target_is_current")
            next_version = int(current_row.get("version") or 0) + 1
            row = conn.execute(
                """
                INSERT INTO server_packs (server_code, version, status, metadata_json, published_at)
                VALUES (%s, %s, 'published', %s::jsonb, NOW())
                RETURNING id, server_code, version, status, metadata_json, created_at, published_at
                """,
                (normalized_code, next_version, json.dumps(dict(target_row.get("metadata_json") or {}), ensure_ascii=False)),
            ).fetchone()
            conn.commit()
            if row is None:
                raise RuntimeError("server_pack_rollback_failed")
            return self._row_to_record(row)  # type: ignore[return-value]
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def to_payload(record: RuntimeServerPackRecord | None) -> dict[str, Any] | None:
        if record is None:
            return None
        return {
            "id": record.id,
            "server_code": record.server_code,
            "version": record.version,
            "status": record.status,
            "metadata": dict(record.metadata_json or {}),
            "created_at": record.created_at,
            "published_at": record.published_at or None,
        }
