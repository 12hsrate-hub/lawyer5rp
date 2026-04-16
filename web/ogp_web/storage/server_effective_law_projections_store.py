from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ogp_web.db.types import DatabaseBackend


@dataclass(frozen=True)
class ServerEffectiveLawProjectionRunRecord:
    id: int
    server_code: str
    trigger_mode: str
    status: str
    summary_json: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class ServerEffectiveLawProjectionItemRecord:
    id: int
    projection_run_id: int
    canonical_law_document_id: int
    canonical_identity_key: str
    normalized_url: str
    selected_document_version_id: int
    selected_source_set_key: str
    selected_revision: int
    precedence_rank: int
    contributor_count: int
    status: str
    provenance_json: dict[str, Any]
    created_at: str


class ServerEffectiveLawProjectionsStore:
    VALID_TRIGGER_MODES = {"manual", "replay"}
    VALID_RUN_STATUSES = {"preview", "approved", "held"}
    VALID_ITEM_STATUSES = {"candidate", "stale", "quarantined"}

    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    @staticmethod
    def _normalize_text(value: str) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_trigger_mode(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "manual"
        if normalized not in cls.VALID_TRIGGER_MODES:
            raise ValueError("server_effective_law_projection_trigger_mode_invalid")
        return normalized

    @classmethod
    def _normalize_run_status(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "preview"
        if normalized not in cls.VALID_RUN_STATUSES:
            raise ValueError("server_effective_law_projection_status_invalid")
        return normalized

    @classmethod
    def _normalize_item_status(cls, value: str) -> str:
        normalized = cls._normalize_text(value).lower() or "candidate"
        if normalized not in cls.VALID_ITEM_STATUSES:
            raise ValueError("server_effective_law_projection_item_status_invalid")
        return normalized

    @staticmethod
    def _normalize_json_object(value: dict[str, Any] | None) -> dict[str, Any]:
        return dict(value or {})

    @staticmethod
    def _serialize_json_value(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _run_from_row(row: dict[str, Any]) -> ServerEffectiveLawProjectionRunRecord:
        return ServerEffectiveLawProjectionRunRecord(
            id=int(row.get("id") or 0),
            server_code=str(row.get("server_code") or ""),
            trigger_mode=str(row.get("trigger_mode") or "manual"),
            status=str(row.get("status") or "preview"),
            summary_json=dict(row.get("summary_json") or {}),
            created_at=str(row.get("created_at") or ""),
        )

    @staticmethod
    def _item_from_row(row: dict[str, Any]) -> ServerEffectiveLawProjectionItemRecord:
        return ServerEffectiveLawProjectionItemRecord(
            id=int(row.get("id") or 0),
            projection_run_id=int(row.get("projection_run_id") or 0),
            canonical_law_document_id=int(row.get("canonical_law_document_id") or 0),
            canonical_identity_key=str(row.get("canonical_identity_key") or ""),
            normalized_url=str(row.get("normalized_url") or ""),
            selected_document_version_id=int(row.get("selected_document_version_id") or 0),
            selected_source_set_key=str(row.get("selected_source_set_key") or ""),
            selected_revision=int(row.get("selected_revision") or 0),
            precedence_rank=int(row.get("precedence_rank") or 0),
            contributor_count=int(row.get("contributor_count") or 0),
            status=str(row.get("status") or "candidate"),
            provenance_json=dict(row.get("provenance_json") or {}),
            created_at=str(row.get("created_at") or ""),
        )

    def list_runs(self, *, server_code: str) -> list[ServerEffectiveLawProjectionRunRecord]:
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT id, server_code, trigger_mode, status, summary_json, created_at
                FROM server_effective_law_projection_runs
                WHERE server_code = %s
                ORDER BY created_at DESC, id DESC
                """,
                (self._normalize_text(server_code).lower(),),
            ).fetchall()
            return [self._run_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def get_run(self, *, run_id: int) -> ServerEffectiveLawProjectionRunRecord | None:
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                SELECT id, server_code, trigger_mode, status, summary_json, created_at
                FROM server_effective_law_projection_runs
                WHERE id = %s
                """,
                (int(run_id),),
            ).fetchone()
            if row is None:
                return None
            return self._run_from_row(dict(row))
        finally:
            conn.close()

    def list_items(self, *, projection_run_id: int) -> list[ServerEffectiveLawProjectionItemRecord]:
        conn = self.backend.connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    id,
                    projection_run_id,
                    canonical_law_document_id,
                    canonical_identity_key,
                    normalized_url,
                    selected_document_version_id,
                    selected_source_set_key,
                    selected_revision,
                    precedence_rank,
                    contributor_count,
                    status,
                    provenance_json,
                    created_at
                FROM server_effective_law_projection_items
                WHERE projection_run_id = %s
                ORDER BY precedence_rank ASC, canonical_identity_key ASC, id ASC
                """,
                (int(projection_run_id),),
            ).fetchall()
            return [self._item_from_row(dict(row)) for row in rows]
        finally:
            conn.close()

    def create_projection_run(
        self,
        *,
        server_code: str,
        trigger_mode: str = "manual",
        status: str = "preview",
        summary_json: dict[str, Any] | None = None,
    ) -> ServerEffectiveLawProjectionRunRecord:
        normalized_server = self._normalize_text(server_code).lower()
        normalized_trigger = self._normalize_trigger_mode(trigger_mode)
        normalized_status = self._normalize_run_status(status)
        normalized_summary = self._normalize_json_object(summary_json)
        if not normalized_server:
            raise ValueError("server_code_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO server_effective_law_projection_runs (
                    server_code, trigger_mode, status, summary_json
                )
                VALUES (%s, %s, %s, %s::jsonb)
                RETURNING id, server_code, trigger_mode, status, summary_json, created_at
                """,
                (
                    normalized_server,
                    normalized_trigger,
                    normalized_status,
                    self._serialize_json_value(normalized_summary),
                ),
            ).fetchone()
            conn.commit()
            return self._run_from_row(dict(row))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_projection_item(
        self,
        *,
        projection_run_id: int,
        canonical_law_document_id: int,
        canonical_identity_key: str,
        normalized_url: str,
        selected_document_version_id: int,
        selected_source_set_key: str,
        selected_revision: int,
        precedence_rank: int,
        contributor_count: int,
        status: str = "candidate",
        provenance_json: dict[str, Any] | None = None,
    ) -> ServerEffectiveLawProjectionItemRecord:
        normalized_identity_key = self._normalize_text(canonical_identity_key)
        normalized_url = self._normalize_text(normalized_url)
        normalized_source_set_key = self._normalize_text(selected_source_set_key).lower()
        normalized_status = self._normalize_item_status(status)
        normalized_provenance = self._normalize_json_object(provenance_json)
        if not normalized_identity_key:
            raise ValueError("canonical_law_document_identity_key_required")
        if not normalized_url:
            raise ValueError("canonical_law_document_alias_url_required")
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                INSERT INTO server_effective_law_projection_items (
                    projection_run_id,
                    canonical_law_document_id,
                    canonical_identity_key,
                    normalized_url,
                    selected_document_version_id,
                    selected_source_set_key,
                    selected_revision,
                    precedence_rank,
                    contributor_count,
                    status,
                    provenance_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING
                    id,
                    projection_run_id,
                    canonical_law_document_id,
                    canonical_identity_key,
                    normalized_url,
                    selected_document_version_id,
                    selected_source_set_key,
                    selected_revision,
                    precedence_rank,
                    contributor_count,
                    status,
                    provenance_json,
                    created_at
                """,
                (
                    int(projection_run_id),
                    int(canonical_law_document_id),
                    normalized_identity_key,
                    normalized_url,
                    int(selected_document_version_id),
                    normalized_source_set_key,
                    int(selected_revision),
                    int(precedence_rank),
                    int(contributor_count),
                    normalized_status,
                    self._serialize_json_value(normalized_provenance),
                ),
            ).fetchone()
            conn.commit()
            return self._item_from_row(dict(row))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_run_status(
        self,
        *,
        run_id: int,
        status: str,
        summary_json: dict[str, Any] | None = None,
    ) -> ServerEffectiveLawProjectionRunRecord:
        normalized_status = self._normalize_run_status(status)
        normalized_summary = self._normalize_json_object(summary_json)
        conn = self.backend.connect()
        try:
            row = conn.execute(
                """
                UPDATE server_effective_law_projection_runs
                SET status = %s, summary_json = %s::jsonb
                WHERE id = %s
                RETURNING id, server_code, trigger_mode, status, summary_json, created_at
                """,
                (normalized_status, self._serialize_json_value(normalized_summary), int(run_id)),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise KeyError("server_effective_law_projection_run_not_found")
            conn.commit()
            return self._run_from_row(dict(row))
        finally:
            conn.close()
