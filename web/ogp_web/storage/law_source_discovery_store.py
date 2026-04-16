from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.db.types import DatabaseBackend


@dataclass(frozen=True)
class SourceDiscoveryRunRecord:
    id: int
    source_set_revision_id: int
    source_set_key: str
    revision: int
    trigger_mode: str
    status: str
    summary_json: dict[str, Any]
    error_summary: str
    created_at: str
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class DiscoveredLawLinkRecord:
    id: int
    source_discovery_run_id: int
    source_set_revision_id: int
    normalized_url: str
    source_container_url: str
    discovery_status: str
    alias_hints_json: dict[str, Any]
    metadata_json: dict[str, Any]
    first_seen_at: str
    last_seen_at: str
    created_at: str
    updated_at: str


class LawSourceDiscoveryStore:
    VALID_TRIGGER_MODES = {"manual", "scheduled", "backfill", "replay"}
    VALID_RUN_STATUSES = {"pending", "running", "partial_success", "succeeded", "failed"}
    VALID_LINK_STATUSES = {"discovered", "broken", "filtered", "duplicate"}

    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    @staticmethod
    def _normalize_text(value: str) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_trigger_mode(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "manual"
        if normalized not in cls.VALID_TRIGGER_MODES:
            raise ValueError("source_discovery_trigger_mode_invalid")
        return normalized

    @classmethod
    def _normalize_run_status(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "pending"
        if normalized not in cls.VALID_RUN_STATUSES:
            raise ValueError("source_discovery_run_status_invalid")
        return normalized

    @classmethod
    def _normalize_link_status(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "discovered"
        if normalized not in cls.VALID_LINK_STATUSES:
            raise ValueError("discovered_law_link_status_invalid")
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
    def _run_from_row(row: dict[str, Any]) -> SourceDiscoveryRunRecord:
        return SourceDiscoveryRunRecord(
            id=int(row.get("id") or 0),
            source_set_revision_id=int(row.get("source_set_revision_id") or 0),
            source_set_key=str(row.get("source_set_key") or ""),
            revision=int(row.get("revision") or 0),
            trigger_mode=str(row.get("trigger_mode") or "manual"),
            status=str(row.get("status") or "pending"),
            summary_json=dict(row.get("summary_json") or {}),
            error_summary=str(row.get("error_summary") or ""),
            created_at=str(row.get("created_at") or ""),
            started_at=str(row.get("started_at") or "") or None,
            finished_at=str(row.get("finished_at") or "") or None,
        )

    @staticmethod
    def _link_from_row(row: dict[str, Any]) -> DiscoveredLawLinkRecord:
        return DiscoveredLawLinkRecord(
            id=int(row.get("id") or 0),
            source_discovery_run_id=int(row.get("source_discovery_run_id") or 0),
            source_set_revision_id=int(row.get("source_set_revision_id") or 0),
            normalized_url=str(row.get("normalized_url") or ""),
            source_container_url=str(row.get("source_container_url") or ""),
            discovery_status=str(row.get("discovery_status") or "discovered"),
            alias_hints_json=dict(row.get("alias_hints_json") or {}),
            metadata_json=dict(row.get("metadata_json") or {}),
            first_seen_at=str(row.get("first_seen_at") or ""),
            last_seen_at=str(row.get("last_seen_at") or ""),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )

    def list_runs(self, *, source_set_key: str) -> list[SourceDiscoveryRunRecord]:
        normalized_key = self._normalize_text(source_set_key).lower()
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT r.id, r.source_set_revision_id, rev.source_set_key, rev.revision,
                       r.trigger_mode, r.status, r.summary_json, r.error_summary,
                       r.created_at, r.started_at, r.finished_at
                FROM source_discovery_runs AS r
                JOIN source_set_revisions AS rev ON rev.id = r.source_set_revision_id
                WHERE rev.source_set_key = %s
                ORDER BY r.created_at DESC, r.id DESC
                """,
                (normalized_key,),
            ).fetchall()
            return [self._run_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def list_runs_for_revision(self, *, source_set_revision_id: int) -> list[SourceDiscoveryRunRecord]:
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT r.id, r.source_set_revision_id, rev.source_set_key, rev.revision,
                       r.trigger_mode, r.status, r.summary_json, r.error_summary,
                       r.created_at, r.started_at, r.finished_at
                FROM source_discovery_runs AS r
                JOIN source_set_revisions AS rev ON rev.id = r.source_set_revision_id
                WHERE r.source_set_revision_id = %s
                ORDER BY r.created_at DESC, r.id DESC
                """,
                (int(source_set_revision_id),),
            ).fetchall()
            return [self._run_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def get_run(self, *, run_id: int) -> SourceDiscoveryRunRecord | None:
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                SELECT r.id, r.source_set_revision_id, rev.source_set_key, rev.revision,
                       r.trigger_mode, r.status, r.summary_json, r.error_summary,
                       r.created_at, r.started_at, r.finished_at
                FROM source_discovery_runs AS r
                JOIN source_set_revisions AS rev ON rev.id = r.source_set_revision_id
                WHERE r.id = %s
                """,
                (int(run_id),),
            ).fetchone()
            if row is None:
                return None
            return self._run_from_row(dict(row))
        finally:
            conn.close()

    def create_run(
        self,
        *,
        source_set_revision_id: int,
        trigger_mode: str = "manual",
        status: str = "pending",
        summary_json: dict[str, Any] | None = None,
        error_summary: str = "",
    ) -> SourceDiscoveryRunRecord:
        normalized_trigger = self._normalize_trigger_mode(trigger_mode)
        normalized_status = self._normalize_run_status(status)
        normalized_summary = self._normalize_json_object(summary_json)
        normalized_error = self._normalize_text(error_summary)
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO source_discovery_runs (
                    source_set_revision_id, trigger_mode, status, summary_json, error_summary
                )
                VALUES (%s, %s, %s, %s::jsonb, %s)
                RETURNING id, source_set_revision_id, trigger_mode, status, summary_json,
                          error_summary, created_at, started_at, finished_at
                """,
                (int(source_set_revision_id), normalized_trigger, normalized_status, normalized_summary, normalized_error),
            ).fetchone()
            joined = conn.execute(
                """
                SELECT r.id, r.source_set_revision_id, rev.source_set_key, rev.revision,
                       r.trigger_mode, r.status, r.summary_json, r.error_summary,
                       r.created_at, r.started_at, r.finished_at
                FROM source_discovery_runs AS r
                JOIN source_set_revisions AS rev ON rev.id = r.source_set_revision_id
                WHERE r.id = %s
                """,
                (int(dict(row)["id"]),),
            ).fetchone()
            conn.commit()
            return self._run_from_row(dict(joined))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_links(self, *, source_discovery_run_id: int) -> list[DiscoveredLawLinkRecord]:
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT id, source_discovery_run_id, source_set_revision_id, normalized_url,
                       source_container_url, discovery_status, alias_hints_json, metadata_json,
                       first_seen_at, last_seen_at, created_at, updated_at
                FROM discovered_law_links
                WHERE source_discovery_run_id = %s
                ORDER BY normalized_url ASC, id ASC
                """,
                (int(source_discovery_run_id),),
            ).fetchall()
            return [self._link_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def create_link(
        self,
        *,
        source_discovery_run_id: int,
        source_set_revision_id: int,
        normalized_url: str,
        source_container_url: str = "",
        discovery_status: str = "discovered",
        alias_hints_json: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> DiscoveredLawLinkRecord:
        normalized_url_value = self._normalize_text(normalized_url)
        if not normalized_url_value:
            raise ValueError("discovered_law_link_url_required")
        normalized_container_url = self._normalize_text(source_container_url)
        normalized_status = self._normalize_link_status(discovery_status)
        normalized_alias_hints = self._normalize_json_object(alias_hints_json)
        normalized_metadata = self._normalize_json_object(metadata_json)
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO discovered_law_links (
                    source_discovery_run_id, source_set_revision_id, normalized_url,
                    source_container_url, discovery_status, alias_hints_json, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                RETURNING id, source_discovery_run_id, source_set_revision_id, normalized_url,
                          source_container_url, discovery_status, alias_hints_json, metadata_json,
                          first_seen_at, last_seen_at, created_at, updated_at
                """,
                (
                    int(source_discovery_run_id),
                    int(source_set_revision_id),
                    normalized_url_value,
                    normalized_container_url,
                    normalized_status,
                    normalized_alias_hints,
                    normalized_metadata,
                ),
            ).fetchone()
            conn.commit()
            return self._link_from_row(dict(row))
        except Exception as exc:
            conn.rollback()
            if self._is_unique_violation(exc, "discovered_law_links_source_discovery_run_id_normalized_url_key"):
                raise ValueError("discovered_law_link_already_exists") from exc
            raise
        finally:
            conn.close()
