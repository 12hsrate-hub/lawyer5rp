from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.db.types import DatabaseBackend


@dataclass(frozen=True)
class CanonicalLawDocumentVersionRecord:
    id: int
    canonical_law_document_id: int
    canonical_identity_key: str
    display_title: str
    source_discovery_run_id: int
    discovered_law_link_id: int
    source_set_key: str
    source_set_revision_id: int
    revision: int
    normalized_url: str
    source_container_url: str
    fetch_status: str
    parse_status: str
    content_checksum: str
    raw_title: str
    parsed_title: str
    body_text: str
    metadata_json: dict[str, Any]
    created_at: str
    updated_at: str


class CanonicalLawDocumentVersionsStore:
    VALID_FETCH_STATUSES = {"pending", "seeded", "fetched", "failed"}
    VALID_PARSE_STATUSES = {"pending", "parsed", "failed", "skipped"}

    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    @staticmethod
    def _normalize_text(value: str) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_fetch_status(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "seeded"
        if normalized not in cls.VALID_FETCH_STATUSES:
            raise ValueError("canonical_law_document_version_fetch_status_invalid")
        return normalized

    @classmethod
    def _normalize_parse_status(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "pending"
        if normalized not in cls.VALID_PARSE_STATUSES:
            raise ValueError("canonical_law_document_version_parse_status_invalid")
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
    def _record_from_row(row: dict[str, Any]) -> CanonicalLawDocumentVersionRecord:
        return CanonicalLawDocumentVersionRecord(
            id=int(row.get("id") or 0),
            canonical_law_document_id=int(row.get("canonical_law_document_id") or 0),
            canonical_identity_key=str(row.get("canonical_identity_key") or ""),
            display_title=str(row.get("display_title") or ""),
            source_discovery_run_id=int(row.get("source_discovery_run_id") or 0),
            discovered_law_link_id=int(row.get("discovered_law_link_id") or 0),
            source_set_key=str(row.get("source_set_key") or ""),
            source_set_revision_id=int(row.get("source_set_revision_id") or 0),
            revision=int(row.get("revision") or 0),
            normalized_url=str(row.get("normalized_url") or ""),
            source_container_url=str(row.get("source_container_url") or ""),
            fetch_status=str(row.get("fetch_status") or "seeded"),
            parse_status=str(row.get("parse_status") or "pending"),
            content_checksum=str(row.get("content_checksum") or ""),
            raw_title=str(row.get("raw_title") or ""),
            parsed_title=str(row.get("parsed_title") or ""),
            body_text=str(row.get("body_text") or ""),
            metadata_json=dict(row.get("metadata_json") or {}),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )

    def _fetch_records(self, query: str, params: tuple[Any, ...]) -> list[CanonicalLawDocumentVersionRecord]:
        conn = self.backend.connect()
        try:
            rows = conn.execute(query, params).fetchall()
            return [self._record_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def list_versions_for_run(self, *, source_discovery_run_id: int) -> list[CanonicalLawDocumentVersionRecord]:
        return self._fetch_records(
            """
            SELECT
                v.id,
                v.canonical_law_document_id,
                d.canonical_identity_key,
                d.display_title,
                v.source_discovery_run_id,
                v.discovered_law_link_id,
                rev.source_set_key,
                l.source_set_revision_id,
                rev.revision,
                l.normalized_url,
                l.source_container_url,
                v.fetch_status,
                v.parse_status,
                v.content_checksum,
                v.raw_title,
                v.parsed_title,
                v.body_text,
                v.metadata_json,
                v.created_at,
                v.updated_at
            FROM canonical_law_document_versions AS v
            JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id
            JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id
            JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id
            WHERE v.source_discovery_run_id = %s
            ORDER BY v.created_at DESC, v.id DESC
            """,
            (int(source_discovery_run_id),),
        )

    def list_versions_for_document(self, *, canonical_law_document_id: int) -> list[CanonicalLawDocumentVersionRecord]:
        return self._fetch_records(
            """
            SELECT
                v.id,
                v.canonical_law_document_id,
                d.canonical_identity_key,
                d.display_title,
                v.source_discovery_run_id,
                v.discovered_law_link_id,
                rev.source_set_key,
                l.source_set_revision_id,
                rev.revision,
                l.normalized_url,
                l.source_container_url,
                v.fetch_status,
                v.parse_status,
                v.content_checksum,
                v.raw_title,
                v.parsed_title,
                v.body_text,
                v.metadata_json,
                v.created_at,
                v.updated_at
            FROM canonical_law_document_versions AS v
            JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id
            JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id
            JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id
            WHERE v.canonical_law_document_id = %s
            ORDER BY v.created_at DESC, v.id DESC
            """,
            (int(canonical_law_document_id),),
        )

    def get_version_by_discovered_link(self, *, discovered_law_link_id: int) -> CanonicalLawDocumentVersionRecord | None:
        records = self._fetch_records(
            """
            SELECT
                v.id,
                v.canonical_law_document_id,
                d.canonical_identity_key,
                d.display_title,
                v.source_discovery_run_id,
                v.discovered_law_link_id,
                rev.source_set_key,
                l.source_set_revision_id,
                rev.revision,
                l.normalized_url,
                l.source_container_url,
                v.fetch_status,
                v.parse_status,
                v.content_checksum,
                v.raw_title,
                v.parsed_title,
                v.body_text,
                v.metadata_json,
                v.created_at,
                v.updated_at
            FROM canonical_law_document_versions AS v
            JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id
            JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id
            JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id
            WHERE v.discovered_law_link_id = %s
            LIMIT 1
            """,
            (int(discovered_law_link_id),),
        )
        return records[0] if records else None

    def get_version(self, *, version_id: int) -> CanonicalLawDocumentVersionRecord | None:
        records = self._fetch_records(
            """
            SELECT
                v.id,
                v.canonical_law_document_id,
                d.canonical_identity_key,
                d.display_title,
                v.source_discovery_run_id,
                v.discovered_law_link_id,
                rev.source_set_key,
                l.source_set_revision_id,
                rev.revision,
                l.normalized_url,
                l.source_container_url,
                v.fetch_status,
                v.parse_status,
                v.content_checksum,
                v.raw_title,
                v.parsed_title,
                v.body_text,
                v.metadata_json,
                v.created_at,
                v.updated_at
            FROM canonical_law_document_versions AS v
            JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id
            JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id
            JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id
            WHERE v.id = %s
            LIMIT 1
            """,
            (int(version_id),),
        )
        return records[0] if records else None

    def create_version(
        self,
        *,
        canonical_law_document_id: int,
        source_discovery_run_id: int,
        discovered_law_link_id: int,
        fetch_status: str = "seeded",
        parse_status: str = "pending",
        content_checksum: str = "",
        raw_title: str = "",
        parsed_title: str = "",
        body_text: str = "",
        metadata_json: dict[str, Any] | None = None,
    ) -> CanonicalLawDocumentVersionRecord:
        normalized_fetch_status = self._normalize_fetch_status(fetch_status)
        normalized_parse_status = self._normalize_parse_status(parse_status)
        normalized_checksum = self._normalize_text(content_checksum)
        normalized_raw_title = self._normalize_text(raw_title)
        normalized_parsed_title = self._normalize_text(parsed_title)
        normalized_body_text = self._normalize_text(body_text)
        normalized_metadata = self._normalize_json_object(metadata_json)
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO canonical_law_document_versions (
                    canonical_law_document_id,
                    source_discovery_run_id,
                    discovered_law_link_id,
                    fetch_status,
                    parse_status,
                    content_checksum,
                    raw_title,
                    parsed_title,
                    body_text,
                    metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    int(canonical_law_document_id),
                    int(source_discovery_run_id),
                    int(discovered_law_link_id),
                    normalized_fetch_status,
                    normalized_parse_status,
                    normalized_checksum,
                    normalized_raw_title,
                    normalized_parsed_title,
                    normalized_body_text,
                    normalized_metadata,
                ),
            ).fetchone()
            version_id = int(dict(row)["id"])
            joined = conn.execute(
                """
                SELECT
                    v.id,
                    v.canonical_law_document_id,
                    d.canonical_identity_key,
                    d.display_title,
                    v.source_discovery_run_id,
                    v.discovered_law_link_id,
                    rev.source_set_key,
                    l.source_set_revision_id,
                    rev.revision,
                    l.normalized_url,
                    l.source_container_url,
                    v.fetch_status,
                    v.parse_status,
                    v.content_checksum,
                    v.raw_title,
                    v.parsed_title,
                    v.body_text,
                    v.metadata_json,
                    v.created_at,
                    v.updated_at
                FROM canonical_law_document_versions AS v
                JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id
                JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id
                JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id
                WHERE v.id = %s
                """,
                (version_id,),
            ).fetchone()
            conn.commit()
            return self._record_from_row(dict(joined))
        except Exception as exc:
            conn.rollback()
            if self._is_unique_violation(exc, "canonical_law_document_versions_discovered_law_link_id_key"):
                raise ValueError("canonical_law_document_version_already_exists") from exc
            raise
        finally:
            conn.close()

    def update_fetch_result(
        self,
        *,
        version_id: int,
        fetch_status: str,
        content_checksum: str = "",
        raw_title: str = "",
        body_text: str = "",
        metadata_json: dict[str, Any] | None = None,
    ) -> CanonicalLawDocumentVersionRecord:
        normalized_fetch_status = self._normalize_fetch_status(fetch_status)
        normalized_checksum = self._normalize_text(content_checksum)
        normalized_raw_title = self._normalize_text(raw_title)
        normalized_body_text = str(body_text or "").strip()
        normalized_metadata = self._normalize_json_object(metadata_json)
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                UPDATE canonical_law_document_versions
                SET
                    fetch_status = %s,
                    content_checksum = %s,
                    raw_title = %s,
                    body_text = %s,
                    metadata_json = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (
                    normalized_fetch_status,
                    normalized_checksum,
                    normalized_raw_title,
                    normalized_body_text,
                    normalized_metadata,
                    int(version_id),
                ),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise KeyError("canonical_law_document_version_not_found")
            joined = conn.execute(
                """
                SELECT
                    v.id,
                    v.canonical_law_document_id,
                    d.canonical_identity_key,
                    d.display_title,
                    v.source_discovery_run_id,
                    v.discovered_law_link_id,
                    rev.source_set_key,
                    l.source_set_revision_id,
                    rev.revision,
                    l.normalized_url,
                    l.source_container_url,
                    v.fetch_status,
                    v.parse_status,
                    v.content_checksum,
                    v.raw_title,
                    v.parsed_title,
                    v.body_text,
                    v.metadata_json,
                    v.created_at,
                    v.updated_at
                FROM canonical_law_document_versions AS v
                JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id
                JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id
                JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id
                WHERE v.id = %s
                """,
                (int(version_id),),
            ).fetchone()
            conn.commit()
            return self._record_from_row(dict(joined))
        finally:
            conn.close()

    def update_parse_result(
        self,
        *,
        version_id: int,
        parse_status: str,
        parsed_title: str = "",
        body_text: str = "",
        metadata_json: dict[str, Any] | None = None,
    ) -> CanonicalLawDocumentVersionRecord:
        normalized_parse_status = self._normalize_parse_status(parse_status)
        normalized_parsed_title = self._normalize_text(parsed_title)
        normalized_body_text = str(body_text or "").strip()
        normalized_metadata = self._normalize_json_object(metadata_json)
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                UPDATE canonical_law_document_versions
                SET
                    parse_status = %s,
                    parsed_title = %s,
                    body_text = %s,
                    metadata_json = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (
                    normalized_parse_status,
                    normalized_parsed_title,
                    normalized_body_text,
                    normalized_metadata,
                    int(version_id),
                ),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise KeyError("canonical_law_document_version_not_found")
            joined = conn.execute(
                """
                SELECT
                    v.id,
                    v.canonical_law_document_id,
                    d.canonical_identity_key,
                    d.display_title,
                    v.source_discovery_run_id,
                    v.discovered_law_link_id,
                    rev.source_set_key,
                    l.source_set_revision_id,
                    rev.revision,
                    l.normalized_url,
                    l.source_container_url,
                    v.fetch_status,
                    v.parse_status,
                    v.content_checksum,
                    v.raw_title,
                    v.parsed_title,
                    v.body_text,
                    v.metadata_json,
                    v.created_at,
                    v.updated_at
                FROM canonical_law_document_versions AS v
                JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id
                JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id
                JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id
                WHERE v.id = %s
                """,
                (int(version_id),),
            ).fetchone()
            conn.commit()
            return self._record_from_row(dict(joined))
        finally:
            conn.close()
