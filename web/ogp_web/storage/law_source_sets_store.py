from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.db.types import DatabaseBackend


@dataclass(frozen=True)
class SourceSetRecord:
    source_set_key: str
    title: str
    description: str
    scope: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SourceSetRevisionRecord:
    id: int
    source_set_key: str
    revision: int
    status: str
    container_urls: tuple[str, ...]
    adapter_policy_json: dict[str, Any]
    metadata_json: dict[str, Any]
    created_at: str
    published_at: str | None


@dataclass(frozen=True)
class ServerSourceSetBindingRecord:
    id: int
    server_code: str
    source_set_key: str
    priority: int
    is_active: bool
    include_law_keys: tuple[str, ...]
    exclude_law_keys: tuple[str, ...]
    pin_policy_json: dict[str, Any]
    metadata_json: dict[str, Any]
    created_at: str
    updated_at: str


class LawSourceSetsStore:
    VALID_SOURCE_SET_SCOPES = {"global"}
    VALID_REVISION_STATUSES = {"draft", "published", "archived", "legacy_flat"}

    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    @staticmethod
    def _normalize_key(value: str) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _normalize_text(value: str) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_scope(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "global"
        if normalized not in cls.VALID_SOURCE_SET_SCOPES:
            raise ValueError("source_set_scope_invalid")
        return normalized

    @classmethod
    def _normalize_status(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "draft"
        if normalized not in cls.VALID_REVISION_STATUSES:
            raise ValueError("source_set_revision_status_invalid")
        return normalized

    @classmethod
    def _normalize_string_list(cls, values: list[str] | tuple[str, ...] | None, *, error_code: str) -> tuple[str, ...]:
        items: list[str] = []
        seen: set[str] = set()
        for raw in values or ():
            normalized = cls._normalize_text(raw)
            if not normalized:
                continue
            dedupe_key = normalized.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            items.append(normalized)
        if not items:
            raise ValueError(error_code)
        return tuple(items)

    @classmethod
    def _normalize_optional_string_list(cls, values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
        items: list[str] = []
        seen: set[str] = set()
        for raw in values or ():
            normalized = cls._normalize_text(raw)
            if not normalized:
                continue
            dedupe_key = normalized.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            items.append(normalized)
        return tuple(items)

    @staticmethod
    def _normalize_json_object(value: dict[str, Any] | None) -> dict[str, Any]:
        return dict(value or {})

    @staticmethod
    def _is_unique_violation(exc: Exception, *tokens: str) -> bool:
        text = str(exc or "").strip().lower()
        type_name = exc.__class__.__name__.lower()
        if "unique" not in text and "duplicate" not in text and type_name not in {"uniqueviolation", "integrityerror"}:
            return False
        return any(str(token or "").strip().lower() in text for token in tokens if str(token or "").strip())

    @staticmethod
    def _source_set_from_row(row: dict[str, Any]) -> SourceSetRecord:
        return SourceSetRecord(
            source_set_key=str(row.get("source_set_key") or ""),
            title=str(row.get("title") or ""),
            description=str(row.get("description") or ""),
            scope=str(row.get("scope") or "global"),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )

    @staticmethod
    def _revision_from_row(row: dict[str, Any]) -> SourceSetRevisionRecord:
        container_urls_raw = row.get("container_urls_json")
        adapter_policy_raw = row.get("adapter_policy_json")
        metadata_raw = row.get("metadata_json")
        container_urls = tuple(
            str(item).strip()
            for item in (container_urls_raw or [])
            if str(item).strip()
        )
        return SourceSetRevisionRecord(
            id=int(row.get("id") or 0),
            source_set_key=str(row.get("source_set_key") or ""),
            revision=int(row.get("revision") or 0),
            status=str(row.get("status") or "draft"),
            container_urls=container_urls,
            adapter_policy_json=dict(adapter_policy_raw or {}),
            metadata_json=dict(metadata_raw or {}),
            created_at=str(row.get("created_at") or ""),
            published_at=str(row.get("published_at") or "") or None,
        )

    @staticmethod
    def _binding_from_row(row: dict[str, Any]) -> ServerSourceSetBindingRecord:
        include_raw = row.get("include_law_keys_json")
        exclude_raw = row.get("exclude_law_keys_json")
        pin_policy_raw = row.get("pin_policy_json")
        metadata_raw = row.get("metadata_json")
        return ServerSourceSetBindingRecord(
            id=int(row.get("id") or 0),
            server_code=str(row.get("server_code") or ""),
            source_set_key=str(row.get("source_set_key") or ""),
            priority=int(row.get("priority") or 100),
            is_active=bool(row.get("is_active", True)),
            include_law_keys=tuple(str(item).strip() for item in (include_raw or []) if str(item).strip()),
            exclude_law_keys=tuple(str(item).strip() for item in (exclude_raw or []) if str(item).strip()),
            pin_policy_json=dict(pin_policy_raw or {}),
            metadata_json=dict(metadata_raw or {}),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )

    def list_source_sets(self) -> list[SourceSetRecord]:
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT source_set_key, title, description, scope, created_at, updated_at
                FROM source_sets
                ORDER BY source_set_key ASC
                """
            ).fetchall()
            return [self._source_set_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def get_source_set(self, *, source_set_key: str) -> SourceSetRecord | None:
        normalized_key = self._normalize_key(source_set_key)
        if not normalized_key:
            return None
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                SELECT source_set_key, title, description, scope, created_at, updated_at
                FROM source_sets
                WHERE source_set_key = %s
                """,
                (normalized_key,),
            ).fetchone()
            if row is None:
                return None
            return self._source_set_from_row(dict(row))
        finally:
            conn.close()

    def create_source_set(self, *, source_set_key: str, title: str, description: str = "", scope: str = "global") -> SourceSetRecord:
        normalized_key = self._normalize_key(source_set_key)
        normalized_title = self._normalize_text(title)
        normalized_description = self._normalize_text(description)
        normalized_scope = self._normalize_scope(scope)
        if not normalized_key:
            raise ValueError("source_set_key_required")
        if not normalized_title:
            raise ValueError("source_set_title_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO source_sets (source_set_key, title, description, scope)
                VALUES (%s, %s, %s, %s)
                RETURNING source_set_key, title, description, scope, created_at, updated_at
                """,
                (normalized_key, normalized_title, normalized_description, normalized_scope),
            ).fetchone()
            conn.commit()
            return self._source_set_from_row(dict(row))
        except Exception as exc:
            conn.rollback()
            if self._is_unique_violation(exc, "source_sets_pkey", "source_sets_source_set_key_key"):
                raise ValueError("source_set_key_already_exists") from exc
            raise
        finally:
            conn.close()

    def list_revisions(self, *, source_set_key: str) -> list[SourceSetRevisionRecord]:
        normalized_key = self._normalize_key(source_set_key)
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT id, source_set_key, revision, status, container_urls_json,
                       adapter_policy_json, metadata_json, created_at, published_at
                FROM source_set_revisions
                WHERE source_set_key = %s
                ORDER BY revision DESC
                """,
                (normalized_key,),
            ).fetchall()
            return [self._revision_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def get_revision(self, *, revision_id: int) -> SourceSetRevisionRecord | None:
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                SELECT id, source_set_key, revision, status, container_urls_json,
                       adapter_policy_json, metadata_json, created_at, published_at
                FROM source_set_revisions
                WHERE id = %s
                """,
                (int(revision_id),),
            ).fetchone()
            if row is None:
                return None
            return self._revision_from_row(dict(row))
        finally:
            conn.close()

    def create_revision(
        self,
        *,
        source_set_key: str,
        container_urls: list[str] | tuple[str, ...],
        adapter_policy_json: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
        status: str = "draft",
    ) -> SourceSetRevisionRecord:
        normalized_key = self._normalize_key(source_set_key)
        normalized_status = self._normalize_status(status)
        normalized_container_urls = self._normalize_string_list(container_urls, error_code="source_set_container_urls_required")
        normalized_adapter_policy = self._normalize_json_object(adapter_policy_json)
        normalized_metadata = self._normalize_json_object(metadata_json)
        if not normalized_key:
            raise ValueError("source_set_key_required")
        conn = self.backend.connect()
        try:
            source_row = conn.execute(
                "SELECT source_set_key FROM source_sets WHERE source_set_key = %s",
                (normalized_key,),
            ).fetchone()
            if source_row is None:
                raise KeyError("source_set_not_found")
            next_row = conn.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 AS next_revision FROM source_set_revisions WHERE source_set_key = %s",
                (normalized_key,),
            ).fetchone()
            next_revision = int((next_row or {}).get("next_revision") or 1)
            row = conn.execute(
                """
                INSERT INTO source_set_revisions (
                    source_set_key, revision, status, container_urls_json, adapter_policy_json, metadata_json, published_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s = 'published' THEN NOW() ELSE NULL END)
                RETURNING id, source_set_key, revision, status, container_urls_json,
                          adapter_policy_json, metadata_json, created_at, published_at
                """,
                (
                    normalized_key,
                    next_revision,
                    normalized_status,
                    list(normalized_container_urls),
                    normalized_adapter_policy,
                    normalized_metadata,
                    normalized_status,
                ),
            ).fetchone()
            conn.commit()
            return self._revision_from_row(dict(row))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_bindings(self, *, server_code: str) -> list[ServerSourceSetBindingRecord]:
        normalized_server = self._normalize_key(server_code)
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT id, server_code, source_set_key, priority, is_active,
                       include_law_keys_json, exclude_law_keys_json, pin_policy_json,
                       metadata_json, created_at, updated_at
                FROM server_source_set_bindings
                WHERE server_code = %s
                ORDER BY is_active DESC, priority ASC, id ASC
                """,
                (normalized_server,),
            ).fetchall()
            return [self._binding_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def create_binding(
        self,
        *,
        server_code: str,
        source_set_key: str,
        priority: int = 100,
        is_active: bool = True,
        include_law_keys: list[str] | tuple[str, ...] | None = None,
        exclude_law_keys: list[str] | tuple[str, ...] | None = None,
        pin_policy_json: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> ServerSourceSetBindingRecord:
        normalized_server = self._normalize_key(server_code)
        normalized_key = self._normalize_key(source_set_key)
        normalized_include = self._normalize_optional_string_list(include_law_keys)
        normalized_exclude = self._normalize_optional_string_list(exclude_law_keys)
        normalized_pin_policy = self._normalize_json_object(pin_policy_json)
        normalized_metadata = self._normalize_json_object(metadata_json)
        if not normalized_server:
            raise ValueError("server_code_required")
        if not normalized_key:
            raise ValueError("source_set_key_required")
        conn = self.backend.connect()
        try:
            server_row = conn.execute("SELECT code FROM servers WHERE code = %s", (normalized_server,)).fetchone()
            if server_row is None:
                raise KeyError("server_not_found")
            source_row = conn.execute(
                "SELECT source_set_key FROM source_sets WHERE source_set_key = %s",
                (normalized_key,),
            ).fetchone()
            if source_row is None:
                raise KeyError("source_set_not_found")
            row = conn.execute(
                """
                INSERT INTO server_source_set_bindings (
                    server_code, source_set_key, priority, is_active,
                    include_law_keys_json, exclude_law_keys_json, pin_policy_json, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, server_code, source_set_key, priority, is_active,
                          include_law_keys_json, exclude_law_keys_json, pin_policy_json,
                          metadata_json, created_at, updated_at
                """,
                (
                    normalized_server,
                    normalized_key,
                    int(priority),
                    bool(is_active),
                    list(normalized_include),
                    list(normalized_exclude),
                    normalized_pin_policy,
                    normalized_metadata,
                ),
            ).fetchone()
            conn.commit()
            return self._binding_from_row(dict(row))
        except Exception as exc:
            conn.rollback()
            if self._is_unique_violation(exc, "server_source_set_bindings_server_code_source_set_key_key"):
                raise ValueError("server_source_set_binding_already_exists") from exc
            raise
        finally:
            conn.close()
