from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.db.types import DatabaseBackend


@dataclass(frozen=True)
class LawSourceRecord:
    id: int
    name: str
    kind: str
    url: str
    is_active: bool


@dataclass(frozen=True)
class LawSetRecord:
    id: int
    server_code: str
    name: str
    is_active: bool
    is_published: bool


class RuntimeLawSetsStore:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    @staticmethod
    def _normalize_server_code(value: str) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _normalize_text(value: str) -> str:
        return str(value or "").strip()

    @staticmethod
    def _normalize_kind(value: str) -> str:
        normalized = str(value or "").strip().lower() or "url"
        if normalized not in {"url", "registry", "api"}:
            raise ValueError("law_source_kind_invalid")
        return normalized

    def list_sources(self) -> list[LawSourceRecord]:
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT id, name, kind, url, is_active
                FROM law_source_registry
                ORDER BY is_active DESC, id DESC
                """
            ).fetchall()
            return [
                LawSourceRecord(
                    id=int(row.get("id") or 0),
                    name=str(row.get("name") or ""),
                    kind=str(row.get("kind") or "url"),
                    url=str(row.get("url") or ""),
                    is_active=bool(row.get("is_active", True)),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def create_source(self, *, name: str, kind: str, url: str) -> LawSourceRecord:
        normalized_name = self._normalize_text(name)
        normalized_kind = self._normalize_kind(kind)
        normalized_url = self._normalize_text(url)
        if not normalized_name:
            raise ValueError("law_source_name_required")
        if not normalized_url:
            raise ValueError("law_source_url_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO law_source_registry (name, kind, url, is_active)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id, name, kind, url, is_active
                """,
                (normalized_name, normalized_kind, normalized_url),
            ).fetchone()
            conn.commit()
            return LawSourceRecord(
                id=int(row.get("id") or 0),
                name=str(row.get("name") or ""),
                kind=str(row.get("kind") or "url"),
                url=str(row.get("url") or ""),
                is_active=bool(row.get("is_active", True)),
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_source(self, *, source_id: int, name: str, kind: str, url: str, is_active: bool) -> LawSourceRecord:
        normalized_name = self._normalize_text(name)
        normalized_kind = self._normalize_kind(kind)
        normalized_url = self._normalize_text(url)
        if not normalized_name:
            raise ValueError("law_source_name_required")
        if not normalized_url:
            raise ValueError("law_source_url_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                UPDATE law_source_registry
                SET name = %s, kind = %s, url = %s, is_active = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id, name, kind, url, is_active
                """,
                (normalized_name, normalized_kind, normalized_url, bool(is_active), int(source_id)),
            ).fetchone()
            if row is None:
                raise KeyError("law_source_not_found")
            conn.commit()
            return LawSourceRecord(
                id=int(row.get("id") or 0),
                name=str(row.get("name") or ""),
                kind=str(row.get("kind") or "url"),
                url=str(row.get("url") or ""),
                is_active=bool(row.get("is_active", True)),
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_law_sets(self, *, server_code: str) -> list[dict[str, Any]]:
        normalized_server = self._normalize_server_code(server_code)
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT ls.id, ls.server_code, ls.name, ls.is_active, ls.is_published,
                       COUNT(lsi.id)::int AS item_count
                FROM law_sets ls
                LEFT JOIN law_set_items lsi ON lsi.law_set_id = ls.id
                WHERE ls.server_code = %s
                GROUP BY ls.id
                ORDER BY ls.is_published DESC, ls.id DESC
                """,
                (normalized_server,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def create_law_set(self, *, server_code: str, name: str) -> dict[str, Any]:
        normalized_server = self._normalize_server_code(server_code)
        normalized_name = self._normalize_text(name)
        if not normalized_server:
            raise ValueError("server_code_required")
        if not normalized_name:
            raise ValueError("law_set_name_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO law_sets (server_code, name, is_active, is_published)
                VALUES (%s, %s, TRUE, FALSE)
                RETURNING id, server_code, name, is_active, is_published
                """,
                (normalized_server, normalized_name),
            ).fetchone()
            conn.commit()
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_law_set(self, *, law_set_id: int, name: str, is_active: bool) -> dict[str, Any]:
        normalized_name = self._normalize_text(name)
        if not normalized_name:
            raise ValueError("law_set_name_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                UPDATE law_sets
                SET name = %s, is_active = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id, server_code, name, is_active, is_published
                """,
                (normalized_name, bool(is_active), int(law_set_id)),
            ).fetchone()
            if row is None:
                raise KeyError("law_set_not_found")
            conn.commit()
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def replace_law_set_items(self, *, law_set_id: int, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        conn = self.backend.connect()
        try:
            exists = conn.execute("SELECT 1 FROM law_sets WHERE id = %s", (int(law_set_id),)).fetchone()
            if exists is None:
                raise KeyError("law_set_not_found")
            conn.execute("DELETE FROM law_set_items WHERE law_set_id = %s", (int(law_set_id),))
            for item in items:
                law_code = self._normalize_text(item.get("law_code", ""))
                if not law_code:
                    continue
                source_id = item.get("source_id")
                effective_from = self._normalize_text(item.get("effective_from", ""))
                priority = int(item.get("priority") or 100)
                conn.execute(
                    """
                    INSERT INTO law_set_items (law_set_id, law_code, effective_from, priority, source_id)
                    VALUES (%s, %s, NULLIF(%s, '')::date, %s, %s)
                    """,
                    (int(law_set_id), law_code, effective_from, priority, source_id),
                )
            conn.commit()
            rows = conn.execute(
                """
                SELECT id, law_set_id, law_code, effective_from, priority, source_id
                FROM law_set_items
                WHERE law_set_id = %s
                ORDER BY priority ASC, id ASC
                """,
                (int(law_set_id),),
            ).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_law_set_detail(self, *, law_set_id: int) -> dict[str, Any]:
        conn = self.backend.connect()
        try:
            law_set_row = conn.execute(
                """
                SELECT id, server_code, name, is_active, is_published
                FROM law_sets
                WHERE id = %s
                """,
                (int(law_set_id),),
            ).fetchone()
            if law_set_row is None:
                raise KeyError("law_set_not_found")
            item_rows = conn.execute(
                """
                SELECT lsi.id, lsi.law_set_id, lsi.law_code, lsi.effective_from, lsi.priority, lsi.source_id,
                       lsr.name AS source_name, lsr.url AS source_url
                FROM law_set_items lsi
                LEFT JOIN law_source_registry lsr ON lsr.id = lsi.source_id
                WHERE lsi.law_set_id = %s
                ORDER BY lsi.priority ASC, lsi.id ASC
                """,
                (int(law_set_id),),
            ).fetchall()
            return {"law_set": dict(law_set_row), "items": [dict(row) for row in item_rows]}
        finally:
            conn.close()

    def publish_law_set(self, *, law_set_id: int) -> dict[str, Any]:
        conn = self.backend.connect()
        try:
            row = conn.execute(
                "SELECT id, server_code FROM law_sets WHERE id = %s",
                (int(law_set_id),),
            ).fetchone()
            if row is None:
                raise KeyError("law_set_not_found")
            server_code = str(row.get("server_code") or "")
            conn.execute(
                "UPDATE law_sets SET is_published = FALSE, updated_at = NOW() WHERE server_code = %s",
                (server_code,),
            )
            result = conn.execute(
                """
                UPDATE law_sets
                SET is_published = TRUE, is_active = TRUE, updated_at = NOW()
                WHERE id = %s
                RETURNING id, server_code, name, is_active, is_published
                """,
                (int(law_set_id),),
            ).fetchone()
            conn.execute(
                "UPDATE servers SET default_law_set_id = %s WHERE code = %s",
                (int(law_set_id), server_code),
            )
            conn.commit()
            return dict(result)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_source_urls_for_law_set(self, *, law_set_id: int) -> tuple[str, list[str]]:
        conn = self.backend.connect()
        try:
            row = conn.execute(
                "SELECT id, server_code FROM law_sets WHERE id = %s",
                (int(law_set_id),),
            ).fetchone()
            if row is None:
                raise KeyError("law_set_not_found")
            urls = conn.execute(
                """
                SELECT DISTINCT lsr.url
                FROM law_set_items lsi
                JOIN law_source_registry lsr ON lsr.id = lsi.source_id
                WHERE lsi.law_set_id = %s
                  AND lsr.is_active = TRUE
                ORDER BY lsr.url ASC
                """,
                (int(law_set_id),),
            ).fetchall()
            return str(row.get("server_code") or ""), [str(item.get("url") or "") for item in urls if str(item.get("url") or "").strip()]
        finally:
            conn.close()
