from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.db.types import DatabaseBackend


@dataclass(frozen=True)
class CanonicalLawDocumentRecord:
    id: int
    canonical_identity_key: str
    identity_source: str
    display_title: str
    metadata_json: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CanonicalLawDocumentAliasRecord:
    id: int
    canonical_law_document_id: int
    normalized_url: str
    alias_kind: str
    is_active: bool
    metadata_json: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CanonicalLawDocumentAliasResolutionRecord:
    document_id: int
    canonical_identity_key: str
    identity_source: str
    display_title: str
    document_metadata_json: dict[str, Any]
    alias_id: int
    normalized_url: str
    alias_kind: str
    is_active: bool
    alias_metadata_json: dict[str, Any]


class CanonicalLawDocumentsStore:
    VALID_IDENTITY_SOURCES = {"url_seed", "parsed_metadata", "manual_remap"}
    VALID_ALIAS_KINDS = {"canonical", "redirect", "mirror", "legacy", "manual_remap"}

    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    @staticmethod
    def _normalize_text(value: str) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_identity_source(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "url_seed"
        if normalized not in cls.VALID_IDENTITY_SOURCES:
            raise ValueError("canonical_law_document_identity_source_invalid")
        return normalized

    @classmethod
    def _normalize_alias_kind(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "canonical"
        if normalized not in cls.VALID_ALIAS_KINDS:
            raise ValueError("canonical_law_document_alias_kind_invalid")
        return normalized

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
    def _document_from_row(row: dict[str, Any]) -> CanonicalLawDocumentRecord:
        return CanonicalLawDocumentRecord(
            id=int(row.get("id") or 0),
            canonical_identity_key=str(row.get("canonical_identity_key") or ""),
            identity_source=str(row.get("identity_source") or "url_seed"),
            display_title=str(row.get("display_title") or ""),
            metadata_json=dict(row.get("metadata_json") or {}),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )

    @staticmethod
    def _alias_from_row(row: dict[str, Any]) -> CanonicalLawDocumentAliasRecord:
        return CanonicalLawDocumentAliasRecord(
            id=int(row.get("id") or 0),
            canonical_law_document_id=int(row.get("canonical_law_document_id") or 0),
            normalized_url=str(row.get("normalized_url") or ""),
            alias_kind=str(row.get("alias_kind") or "canonical"),
            is_active=bool(row.get("is_active", True)),
            metadata_json=dict(row.get("metadata_json") or {}),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )

    @staticmethod
    def _resolution_from_row(row: dict[str, Any]) -> CanonicalLawDocumentAliasResolutionRecord:
        return CanonicalLawDocumentAliasResolutionRecord(
            document_id=int(row.get("document_id") or 0),
            canonical_identity_key=str(row.get("canonical_identity_key") or ""),
            identity_source=str(row.get("identity_source") or "url_seed"),
            display_title=str(row.get("display_title") or ""),
            document_metadata_json=dict(row.get("document_metadata_json") or {}),
            alias_id=int(row.get("alias_id") or 0),
            normalized_url=str(row.get("normalized_url") or ""),
            alias_kind=str(row.get("alias_kind") or "canonical"),
            is_active=bool(row.get("is_active", True)),
            alias_metadata_json=dict(row.get("alias_metadata_json") or {}),
        )

    def list_documents(self) -> list[CanonicalLawDocumentRecord]:
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT id, canonical_identity_key, identity_source, display_title,
                       metadata_json, created_at, updated_at
                FROM canonical_law_documents
                ORDER BY canonical_identity_key ASC
                """
            ).fetchall()
            return [self._document_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def get_document(self, *, canonical_identity_key: str) -> CanonicalLawDocumentRecord | None:
        normalized_key = self._normalize_text(canonical_identity_key)
        if not normalized_key:
            return None
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                SELECT id, canonical_identity_key, identity_source, display_title,
                       metadata_json, created_at, updated_at
                FROM canonical_law_documents
                WHERE canonical_identity_key = %s
                """,
                (normalized_key,),
            ).fetchone()
            if row is None:
                return None
            return self._document_from_row(dict(row))
        finally:
            conn.close()

    def create_document(
        self,
        *,
        canonical_identity_key: str,
        identity_source: str = "url_seed",
        display_title: str = "",
        metadata_json: dict[str, Any] | None = None,
    ) -> CanonicalLawDocumentRecord:
        normalized_key = self._normalize_text(canonical_identity_key)
        normalized_identity_source = self._normalize_identity_source(identity_source)
        normalized_title = self._normalize_text(display_title)
        normalized_metadata = self._normalize_json_object(metadata_json)
        if not normalized_key:
            raise ValueError("canonical_law_document_identity_key_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO canonical_law_documents (
                    canonical_identity_key, identity_source, display_title, metadata_json
                )
                VALUES (%s, %s, %s, %s::jsonb)
                RETURNING id, canonical_identity_key, identity_source, display_title,
                          metadata_json, created_at, updated_at
                """,
                (normalized_key, normalized_identity_source, normalized_title, normalized_metadata),
            ).fetchone()
            conn.commit()
            return self._document_from_row(dict(row))
        except Exception as exc:
            conn.rollback()
            if self._is_unique_violation(exc, "canonical_law_documents_canonical_identity_key_key"):
                raise ValueError("canonical_law_document_identity_key_already_exists") from exc
            raise
        finally:
            conn.close()

    def list_aliases(self, *, canonical_law_document_id: int) -> list[CanonicalLawDocumentAliasRecord]:
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT id, canonical_law_document_id, normalized_url, alias_kind,
                       is_active, metadata_json, created_at, updated_at
                FROM canonical_law_document_aliases
                WHERE canonical_law_document_id = %s
                ORDER BY normalized_url ASC, id ASC
                """,
                (int(canonical_law_document_id),),
            ).fetchall()
            return [self._alias_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def create_alias(
        self,
        *,
        canonical_law_document_id: int,
        normalized_url: str,
        alias_kind: str = "canonical",
        is_active: bool = True,
        metadata_json: dict[str, Any] | None = None,
    ) -> CanonicalLawDocumentAliasRecord:
        normalized_url_value = self._normalize_text(normalized_url)
        normalized_alias_kind = self._normalize_alias_kind(alias_kind)
        normalized_metadata = self._normalize_json_object(metadata_json)
        if not normalized_url_value:
            raise ValueError("canonical_law_document_alias_url_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO canonical_law_document_aliases (
                    canonical_law_document_id, normalized_url, alias_kind, is_active, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING id, canonical_law_document_id, normalized_url, alias_kind,
                          is_active, metadata_json, created_at, updated_at
                """,
                (int(canonical_law_document_id), normalized_url_value, normalized_alias_kind, bool(is_active), normalized_metadata),
            ).fetchone()
            conn.commit()
            return self._alias_from_row(dict(row))
        except Exception as exc:
            conn.rollback()
            if self._is_unique_violation(exc, "canonical_law_document_aliases_normalized_url_key"):
                raise ValueError("canonical_law_document_alias_already_exists") from exc
            raise
        finally:
            conn.close()

    def resolve_document_by_alias(self, *, normalized_url: str) -> CanonicalLawDocumentAliasResolutionRecord | None:
        normalized_url_value = self._normalize_text(normalized_url)
        if not normalized_url_value:
            return None
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                SELECT
                    d.id AS document_id,
                    d.canonical_identity_key,
                    d.identity_source,
                    d.display_title,
                    d.metadata_json AS document_metadata_json,
                    a.id AS alias_id,
                    a.normalized_url,
                    a.alias_kind,
                    a.is_active,
                    a.metadata_json AS alias_metadata_json
                FROM canonical_law_document_aliases AS a
                JOIN canonical_law_documents AS d ON d.id = a.canonical_law_document_id
                WHERE a.normalized_url = %s
                LIMIT 1
                """,
                (normalized_url_value,),
            ).fetchone()
            if row is None:
                return None
            return self._resolution_from_row(dict(row))
        finally:
            conn.close()
