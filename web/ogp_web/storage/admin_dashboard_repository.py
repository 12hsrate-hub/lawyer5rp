from __future__ import annotations

import json
from typing import Any

from ogp_web.db.types import DatabaseBackend, DbConnectionLike


class AdminDashboardRepository:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    def _connect(self) -> DbConnectionLike:
        return self.backend.connect()

    @staticmethod
    def _json_load(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if value in (None, ""):
            return {}
        try:
            parsed = json.loads(str(value))
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def get_release_section(self, *, server_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            fallback = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM metric_events
                WHERE event_type = 'rollout_fallback_to_legacy'
                  AND COALESCE(server_code, '') IN ('', %s)
                """,
                (server_id,),
            ).fetchone()
            new_domain = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM metric_events
                WHERE event_type = 'rollout_new_domain_selected'
                  AND COALESCE(server_code, '') IN ('', %s)
                """,
                (server_id,),
            ).fetchone()
            rollback_rows = conn.execute(
                """
                SELECT id, rollback_of_batch_id, created_at
                FROM publish_batches
                WHERE server_scope = 'server'
                  AND server_id = %s
                  AND rollback_of_batch_id IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (server_id,),
            ).fetchall()
            warnings = conn.execute(
                """
                SELECT event_type, COUNT(*) AS total
                FROM metric_events
                WHERE event_type IN ('rollout_error_rate', 'rollout_generation_latency', 'rollout_validation_fail_rate', 'rollout_async_queue_lag')
                  AND COALESCE(server_code, '') IN ('', %s)
                GROUP BY event_type
                ORDER BY total DESC, event_type ASC
                """,
                (server_id,),
            ).fetchall()
            return {
                "feature_flags": {},
                "fallback_to_legacy_usage": int((fallback or {}).get("total") or 0),
                "new_domain_usage": int((new_domain or {}).get("total") or 0),
                "rollback_history": [dict(row) for row in rollback_rows],
                "warning_signals": [dict(row) for row in warnings],
            }
        finally:
            conn.close()

    def get_generation_law_qa_section(self, *, server_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            ai_rows = conn.execute(
                """
                SELECT meta_json, created_at
                FROM metric_events
                WHERE event_type = 'ai_generation'
                  AND COALESCE(server_code, '') IN ('', %s)
                ORDER BY id DESC
                LIMIT 500
                """,
                (server_id,),
            ).fetchall()
            law_qa_total = conn.execute(
                "SELECT COUNT(*) AS total FROM law_qa_runs WHERE server_id = %s",
                (server_id,),
            ).fetchone()
            validation = conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM validation_runs
                WHERE server_id = %s
                GROUP BY status
                ORDER BY status ASC
                """,
                (server_id,),
            ).fetchall()
            citations = 0
            snapshots = 0
            latencies: list[float] = []
            for row in ai_rows:
                meta = self._json_load(row.get("meta_json"))
                if bool(meta.get("citations_used") or meta.get("citations_count") or meta.get("citations")):
                    citations += 1
                if meta.get("snapshot_id") not in (None, ""):
                    snapshots += 1
                try:
                    lat = float(meta.get("latency_ms"))
                    if lat >= 0:
                        latencies.append(lat)
                except Exception:
                    pass
            total = len(ai_rows)
            return {
                "generation_totals": total,
                "latency_ms_avg": round(sum(latencies) / len(latencies), 2) if latencies else None,
                "citations_rate": round(citations / total, 4) if total else 0.0,
                "snapshot_rate": round(snapshots / total, 4) if total else 0.0,
                "law_qa_totals": int((law_qa_total or {}).get("total") or 0),
                "validation_breakdown": [dict(row) for row in validation],
            }
        finally:
            conn.close()

    def get_jobs_section(self, *, server_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            statuses = conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM async_jobs
                WHERE (server_scope = 'server' AND server_id = %s)
                   OR server_scope = 'global'
                GROUP BY status
                ORDER BY status ASC
                """,
                (server_id,),
            ).fetchall()
            breakdown = conn.execute(
                """
                SELECT job_type, COUNT(*) AS total
                FROM async_jobs
                WHERE (server_scope = 'server' AND server_id = %s)
                   OR server_scope = 'global'
                GROUP BY job_type
                ORDER BY total DESC, job_type ASC
                """,
                (server_id,),
            ).fetchall()
            lag_row = conn.execute(
                """
                SELECT COALESCE(MAX(EXTRACT(EPOCH FROM (NOW() - next_run_at))), 0) AS queue_lag_seconds
                FROM async_jobs
                WHERE status IN ('pending', 'queued')
                  AND ((server_scope = 'server' AND server_id = %s) OR server_scope = 'global')
                """,
                (server_id,),
            ).fetchone()
            retry_row = conn.execute(
                """
                SELECT COALESCE(SUM(attempt_count), 0) AS retry_count
                FROM async_jobs
                WHERE ((server_scope = 'server' AND server_id = %s) OR server_scope = 'global')
                """,
                (server_id,),
            ).fetchone()
            dlq_row = conn.execute(
                """
                SELECT COUNT(*) AS dlq_count
                FROM job_dead_letters jdl
                JOIN async_jobs j ON j.id = jdl.async_job_id
                WHERE ((j.server_scope = 'server' AND j.server_id = %s) OR j.server_scope = 'global')
                """,
                (server_id,),
            ).fetchone()
            return {
                "job_statuses": [dict(row) for row in statuses],
                "queue_lag_seconds": int(float((lag_row or {}).get("queue_lag_seconds") or 0)),
                "retry_count": int((retry_row or {}).get("retry_count") or 0),
                "dlq_count": int((dlq_row or {}).get("dlq_count") or 0),
                "by_job_type": [dict(row) for row in breakdown],
            }
        finally:
            conn.close()

    def get_validation_section(self, *, server_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            runs = conn.execute("SELECT COUNT(*) AS total FROM validation_runs WHERE server_id = %s", (server_id,)).fetchone()
            risk_cov = conn.execute(
                """
                SELECT
                    CASE
                        WHEN risk_score >= 0.7 THEN 'high_risk'
                        WHEN risk_score >= 0.3 THEN 'medium_risk'
                        ELSE 'low_risk'
                    END AS risk_band,
                    CASE
                        WHEN coverage_score >= 0.8 THEN 'high_coverage'
                        WHEN coverage_score >= 0.4 THEN 'medium_coverage'
                        ELSE 'low_coverage'
                    END AS coverage_band,
                    COUNT(*) AS total
                FROM validation_runs
                WHERE server_id = %s
                GROUP BY risk_band, coverage_band
                ORDER BY total DESC
                """,
                (server_id,),
            ).fetchall()
            readiness = conn.execute(
                "SELECT readiness_status, COUNT(*) AS total FROM validation_runs WHERE server_id = %s GROUP BY readiness_status",
                (server_id,),
            ).fetchall()
            issues = conn.execute(
                """
                SELECT vi.issue_code, COUNT(*) AS total
                FROM validation_issues vi
                JOIN validation_runs vr ON vr.id = vi.validation_run_id
                WHERE vr.server_id = %s
                GROUP BY vi.issue_code
                ORDER BY total DESC, vi.issue_code ASC
                LIMIT 10
                """,
                (server_id,),
            ).fetchall()
            blocked = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM validation_runs
                WHERE server_id = %s
                  AND readiness_status = 'blocked'
                """,
                (server_id,),
            ).fetchone()
            return {
                "validation_runs": int((runs or {}).get("total") or 0),
                "risk_coverage_distribution": [dict(row) for row in risk_cov],
                "readiness_breakdown": [dict(row) for row in readiness],
                "top_issues": [dict(row) for row in issues],
                "blocked_export_publish": int((blocked or {}).get("total") or 0),
            }
        finally:
            conn.close()

    def get_content_section(self, *, server_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            states = conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM content_items
                WHERE (server_scope = 'server' AND server_id = %s) OR server_scope = 'global'
                GROUP BY status
                ORDER BY status ASC
                """,
                (server_id,),
            ).fetchall()
            audit = conn.execute(
                """
                SELECT id, entity_type, entity_id, action, created_at
                FROM audit_logs
                WHERE COALESCE(server_id, %s) = %s
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (server_id, server_id),
            ).fetchall()
            batches = conn.execute(
                """
                SELECT id, rollback_of_batch_id, created_at
                FROM publish_batches
                WHERE (server_scope = 'server' AND server_id = %s) OR server_scope = 'global'
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (server_id,),
            ).fetchall()
            return {
                "workflow_breakdown": [dict(row) for row in states],
                "recent_audit_activity": [dict(row) for row in audit],
                "publish_batches": [dict(row) for row in batches],
            }
        finally:
            conn.close()

    def get_integrity_section(self, *, server_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            orphan = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM document_versions dv
                LEFT JOIN documents d ON d.id = dv.document_id
                WHERE d.id IS NULL
                """
            ).fetchone()
            no_snapshot = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM document_versions
                WHERE server_id = %s
                  AND generation_snapshot_id IS NULL
                """,
                (server_id,),
            ).fetchone()
            no_artifact = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM exports
                WHERE server_id = %s
                  AND COALESCE(storage_key, '') = ''
                """,
                (server_id,),
            ).fetchone()
            not_finalized = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM attachments
                WHERE server_id = %s
                  AND upload_status <> 'uploaded'
                """,
                (server_id,),
            ).fetchone()
            cross_alerts = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM metric_events
                WHERE event_type = 'cross_server_access_denied'
                  AND COALESCE(server_code, '') IN ('', %s)
                """,
                (server_id,),
            ).fetchone()
            return {
                "orphan_broken_entities": int((orphan or {}).get("total") or 0),
                "versions_without_snapshot_or_citations": int((no_snapshot or {}).get("total") or 0),
                "exports_without_artifact": int((no_artifact or {}).get("total") or 0),
                "attachments_not_finalized": int((not_finalized or {}).get("total") or 0),
                "cross_server_alerts": int((cross_alerts or {}).get("total") or 0),
            }
        finally:
            conn.close()

    def get_synthetic_section(self, *, server_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT created_at, event_type, status_code, CAST(meta_json AS TEXT) AS meta_json
                FROM metric_events
                WHERE event_type IN ('synthetic_smoke_run', 'synthetic_nightly_run', 'synthetic_scenario_failed')
                  AND COALESCE(server_code, '') IN ('', %s)
                ORDER BY id DESC
                LIMIT 200
                """,
                (server_id,),
            ).fetchall()
            smoke = next((dict(r) for r in rows if r.get("event_type") == "synthetic_smoke_run"), None)
            nightly = next((dict(r) for r in rows if r.get("event_type") == "synthetic_nightly_run"), None)
            failed: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["meta"] = self._json_load(item.pop("meta_json", None))
                if item.get("event_type") == "synthetic_scenario_failed":
                    failed.append(item)
            return {
                "last_smoke_run": smoke,
                "last_nightly_run": nightly,
                "failed_scenarios": failed[:20],
            }
        finally:
            conn.close()
