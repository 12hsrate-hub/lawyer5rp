from __future__ import annotations

import json
from typing import Any

from ogp_web.db.types import DatabaseBackend


class ValidationRepository:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    def _connect(self):
        return self.backend.connect()

    def _fetchall(self, query: str, params: tuple[Any, ...]):
        try:
            return self._connect().execute(query, params).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc

    def _fetchone(self, query: str, params: tuple[Any, ...]):
        try:
            return self._connect().execute(query, params).fetchone()
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc

    def get_applicable_requirements(self, *, target_type: str, target_subtype: str, server_id: str):
        return self._fetchall(
            """
            SELECT id, server_scope, server_id, target_type, target_subtype, field_key,
                   CAST(rule_json AS TEXT) AS rule_json, is_required, is_active, created_at, updated_at
            FROM validation_requirements
            WHERE is_active = TRUE
              AND target_type = %s
              AND (target_subtype = '' OR target_subtype = %s)
              AND ((server_scope = 'global' AND server_id IS NULL) OR (server_scope = 'server' AND server_id = %s))
            ORDER BY CASE WHEN server_scope = 'server' THEN 0 ELSE 1 END, id ASC
            """,
            (target_type, target_subtype, server_id),
        )

    def get_applicable_readiness_gates(self, *, target_type: str, target_subtype: str, server_id: str):
        return self._fetchall(
            """
            SELECT id, server_scope, server_id, target_type, target_subtype, gate_code,
                   enforcement_mode, CAST(threshold_json AS TEXT) AS threshold_json,
                   is_active, created_at, updated_at
            FROM readiness_gates
            WHERE is_active = TRUE
              AND target_type = %s
              AND (target_subtype = '' OR target_subtype = %s)
              AND ((server_scope = 'global' AND server_id IS NULL) OR (server_scope = 'server' AND server_id = %s))
            ORDER BY CASE WHEN server_scope = 'server' THEN 0 ELSE 1 END, id ASC
            """,
            (target_type, target_subtype, server_id),
        )

    def get_document_version_target(self, *, version_id: int):
        return self._fetchone(
            """
            SELECT dv.id, dv.document_id, dv.version_number, CAST(dv.content_json AS TEXT) AS content_json,
                   cd.server_id, cd.document_type
            FROM document_versions dv
            JOIN case_documents cd ON cd.id = dv.document_id
            WHERE dv.id = %s
            LIMIT 1
            """,
            (version_id,),
        )

    def get_law_qa_run_target(self, *, run_id: int):
        return self._fetchone(
            """
            SELECT id, server_id, question, answer_text,
                   CAST(used_sources_json AS TEXT) AS used_sources_json,
                   CAST(selected_norms_json AS TEXT) AS selected_norms_json,
                   CAST(metadata_json AS TEXT) AS metadata_json
            FROM law_qa_runs
            WHERE id = %s
            LIMIT 1
            """,
            (run_id,),
        )

    def create_law_qa_run(
        self,
        *,
        server_id: str,
        user_id: int,
        question: str,
        answer_text: str,
        used_sources: list[str],
        selected_norms: list[dict[str, Any]],
        metadata: dict[str, Any],
    ):
        conn = self._connect()
        try:
            row = conn.execute(
                """
                INSERT INTO law_qa_runs (
                    server_id, user_id, question, answer_text,
                    used_sources_json, selected_norms_json, metadata_json
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                RETURNING id, server_id, question, answer_text, created_at
                """,
                (
                    server_id,
                    user_id,
                    question,
                    answer_text,
                    json.dumps(used_sources, ensure_ascii=False),
                    json.dumps(selected_norms, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                ),
            ).fetchone()
            conn.commit()
            return row
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc

    def create_validation_run(
        self,
        *,
        target_type: str,
        target_id: int,
        server_id: str,
        status: str,
        risk_score: float,
        coverage_score: float,
        readiness_status: str,
        summary_json: dict[str, Any],
        score_breakdown_json: dict[str, Any],
        gate_decisions_json: list[dict[str, Any]],
    ):
        conn = self._connect()
        try:
            row = conn.execute(
                """
                INSERT INTO validation_runs (
                    target_type, target_id, server_id, status, risk_score, coverage_score,
                    readiness_status, summary_json, score_breakdown_json, gate_decisions_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                RETURNING id, target_type, target_id, server_id, status, risk_score, coverage_score,
                          readiness_status, CAST(summary_json AS TEXT) AS summary_json,
                          CAST(score_breakdown_json AS TEXT) AS score_breakdown_json,
                          CAST(gate_decisions_json AS TEXT) AS gate_decisions_json, created_at
                """,
                (
                    target_type,
                    target_id,
                    server_id,
                    status,
                    risk_score,
                    coverage_score,
                    readiness_status,
                    json.dumps(summary_json, ensure_ascii=False),
                    json.dumps(score_breakdown_json, ensure_ascii=False),
                    json.dumps(gate_decisions_json, ensure_ascii=False),
                ),
            ).fetchone()
            conn.commit()
            return row
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc

    def create_validation_issues(self, *, validation_run_id: int, issues: list[dict[str, Any]]):
        if not issues:
            return []
        conn = self._connect()
        created = []
        try:
            for issue in issues:
                row = conn.execute(
                    """
                    INSERT INTO validation_issues (
                        validation_run_id, issue_code, severity, message, field_ref, details_json
                    ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    RETURNING id, validation_run_id, issue_code, severity, message, field_ref,
                              CAST(details_json AS TEXT) AS details_json, created_at
                    """,
                    (
                        validation_run_id,
                        issue["issue_code"],
                        issue["severity"],
                        issue["message"],
                        issue.get("field_ref") or "",
                        json.dumps(issue.get("details_json") or {}, ensure_ascii=False),
                    ),
                ).fetchone()
                created.append(row)
            conn.commit()
            return created
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc

    def get_validation_run(self, *, run_id: int):
        return self._fetchone(
            """
            SELECT id, target_type, target_id, server_id, status, risk_score, coverage_score,
                   readiness_status, CAST(summary_json AS TEXT) AS summary_json,
                   CAST(score_breakdown_json AS TEXT) AS score_breakdown_json,
                   CAST(gate_decisions_json AS TEXT) AS gate_decisions_json, created_at
            FROM validation_runs
            WHERE id = %s
            LIMIT 1
            """,
            (run_id,),
        )

    def get_latest_validation_run(self, *, target_type: str, target_id: int):
        return self._fetchone(
            """
            SELECT id, target_type, target_id, server_id, status, risk_score, coverage_score,
                   readiness_status, CAST(summary_json AS TEXT) AS summary_json,
                   CAST(score_breakdown_json AS TEXT) AS score_breakdown_json,
                   CAST(gate_decisions_json AS TEXT) AS gate_decisions_json, created_at
            FROM validation_runs
            WHERE target_type = %s AND target_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (target_type, target_id),
        )

    def list_validation_runs(self, *, target_type: str, target_id: int):
        return self._fetchall(
            """
            SELECT id, target_type, target_id, server_id, status, risk_score, coverage_score,
                   readiness_status, CAST(summary_json AS TEXT) AS summary_json,
                   CAST(score_breakdown_json AS TEXT) AS score_breakdown_json,
                   CAST(gate_decisions_json AS TEXT) AS gate_decisions_json, created_at
            FROM validation_runs
            WHERE target_type = %s AND target_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (target_type, target_id),
        )

    def list_validation_issues(self, *, validation_run_id: int):
        return self._fetchall(
            """
            SELECT id, validation_run_id, issue_code, severity, message, field_ref,
                   CAST(details_json AS TEXT) AS details_json, created_at
            FROM validation_issues
            WHERE validation_run_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (validation_run_id,),
        )
