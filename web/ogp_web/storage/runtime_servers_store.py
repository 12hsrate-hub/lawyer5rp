from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.db.types import DatabaseBackend


@dataclass(frozen=True)
class RuntimeServerRecord:
    code: str
    title: str
    is_active: bool
    created_at: str


class RuntimeServersStore:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    @staticmethod
    def _normalize_code(value: str) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _normalize_title(value: str) -> str:
        return str(value or "").strip()

    def list_servers(self) -> list[RuntimeServerRecord]:
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT code, title, is_active, created_at
                FROM servers
                ORDER BY code ASC
                """
            ).fetchall()
            return [
                RuntimeServerRecord(
                    code=str(row.get("code") or ""),
                    title=str(row.get("title") or ""),
                    is_active=bool(row.get("is_active", True)),
                    created_at=str(row.get("created_at") or ""),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def create_server(self, *, code: str, title: str) -> RuntimeServerRecord:
        normalized_code = self._normalize_code(code)
        normalized_title = self._normalize_title(title)
        if not normalized_code:
            raise ValueError("server_code_required")
        if not normalized_title:
            raise ValueError("server_title_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO servers (code, title, is_active)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (code) DO NOTHING
                RETURNING code, title, is_active, created_at
                """,
                (normalized_code, normalized_title),
            ).fetchone()
            if row is None:
                raise ValueError("server_code_already_exists")
            conn.commit()
            return RuntimeServerRecord(
                code=str(row.get("code") or ""),
                title=str(row.get("title") or ""),
                is_active=bool(row.get("is_active", True)),
                created_at=str(row.get("created_at") or ""),
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_server(self, *, code: str, title: str) -> RuntimeServerRecord:
        normalized_code = self._normalize_code(code)
        normalized_title = self._normalize_title(title)
        if not normalized_code:
            raise ValueError("server_code_required")
        if not normalized_title:
            raise ValueError("server_title_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                UPDATE servers
                SET title = %s
                WHERE code = %s
                RETURNING code, title, is_active, created_at
                """,
                (normalized_title, normalized_code),
            ).fetchone()
            if row is None:
                raise KeyError("server_not_found")
            conn.commit()
            return RuntimeServerRecord(
                code=str(row.get("code") or ""),
                title=str(row.get("title") or ""),
                is_active=bool(row.get("is_active", True)),
                created_at=str(row.get("created_at") or ""),
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def set_active(self, *, code: str, is_active: bool) -> RuntimeServerRecord:
        normalized_code = self._normalize_code(code)
        if not normalized_code:
            raise ValueError("server_code_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                UPDATE servers
                SET is_active = %s
                WHERE code = %s
                RETURNING code, title, is_active, created_at
                """,
                (bool(is_active), normalized_code),
            ).fetchone()
            if row is None:
                raise KeyError("server_not_found")
            conn.commit()
            return RuntimeServerRecord(
                code=str(row.get("code") or ""),
                title=str(row.get("title") or ""),
                is_active=bool(row.get("is_active", True)),
                created_at=str(row.get("created_at") or ""),
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def to_payload(record: RuntimeServerRecord) -> dict[str, Any]:
        return {
            "code": record.code,
            "title": record.title,
            "is_active": record.is_active,
            "created_at": record.created_at,
        }
