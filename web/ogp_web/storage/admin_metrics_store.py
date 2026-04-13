from __future__ import annotations

import csv
import json
import logging
from contextlib import closing
from io import StringIO
from datetime import datetime
from pathlib import Path
from typing import Any

from ogp_web.db.errors import DatabaseUnavailableError
from ogp_web.db.factory import get_database_backend
from ogp_web.db.types import DatabaseBackend

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "web" / "data"
DB_PATH = DATA_DIR / "admin_metrics.db"
logger = logging.getLogger(__name__)
USER_SORT_OPTIONS = {"complaints", "api_requests", "last_seen", "created_at", "username"}


class AdminMetricsStore:
    def __init__(self, db_path: Path, backend: DatabaseBackend | None = None):
        self.db_path = db_path
        self.backend = backend or get_database_backend()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self):
        return self.backend.connect()

    @property
    def is_postgres_backend(self) -> bool:
        return True

    def _placeholder(self) -> str:
        return "%s"

    def _decode_json_field(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if raw in (None, ""):
            return {}
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _percentile(values: list[int], quantile: float) -> int | None:
        if not values:
            return None
        if not 0 <= quantile <= 1:
            raise ValueError("quantile must be in [0, 1]")
        ordered = sorted(values)
        if len(ordered) == 1:
            return int(ordered[0])
        index = (len(ordered) - 1) * quantile
        lower = int(index)
        upper = lower + 1
        if upper >= len(ordered):
            return int(ordered[-1])
        weight = index - lower
        return int(round((1 - weight) * ordered[lower] + weight * ordered[upper]))

    @staticmethod
    def _safe_request_count(value: int | float | None) -> int:
        if value in (None, ""):
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_duration(value: Any) -> int | None:
        try:
            if value is None:
                return None
            value_int = int(value)
        except (TypeError, ValueError):
            return None
        return value_int if value_int >= 0 else None

    def count_user_api_requests_last_24h(self, username: str) -> int:
        normalized_username = str(username or "").strip().lower()
        if not normalized_username:
            return 0
        placeholder = self._placeholder()
        created_filter = "created_at >= NOW() - INTERVAL '1 day'"
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM metric_events
                WHERE event_type = 'api_request'
                  AND username = {placeholder}
                  AND {created_filter}
                """,
                (normalized_username,),
            ).fetchone()
        if row is None:
            return 0
        return int(row["total"] or 0)

    def get_performance_overview(
        self,
        *,
        window_minutes: int = 15,
        top_endpoints: int = 10,
    ) -> dict[str, Any]:
        window = max(1, int(window_minutes or 1))
        endpoint_limit = max(1, int(top_endpoints or 10))
        created_at_filter = "created_at >= NOW() - (%s::int * INTERVAL '1 minute')"
        created_at_param = window

        with closing(self._connect()) as conn:
            totals = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS request_count,
                    SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count,
                    COALESCE(SUM(CASE WHEN event_type = 'api_request' THEN 1 ELSE 0 END), 0) AS api_requests_total,
                    COALESCE(AVG(CASE WHEN event_type = 'api_request' AND duration_ms IS NOT NULL THEN duration_ms END), 0) AS avg_duration_ms,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms)
                        FILTER (WHERE event_type = 'api_request' AND duration_ms IS NOT NULL) AS p50_duration_ms,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)
                        FILTER (WHERE event_type = 'api_request' AND duration_ms IS NOT NULL) AS p95_duration_ms,
                    COALESCE(SUM(CASE WHEN event_type = 'api_request' THEN COALESCE(request_bytes, 0) ELSE 0 END), 0) AS request_bytes,
                    COALESCE(SUM(CASE WHEN event_type = 'api_request' THEN COALESCE(response_bytes, 0) ELSE 0 END), 0) AS response_bytes,
                    COALESCE(SUM(CASE WHEN event_type = 'api_request' THEN COALESCE(resource_units, 0) ELSE 0 END), 0) AS resource_units
                FROM metric_events
                WHERE event_type = 'api_request'
                  AND {created_at_filter}
                """,
                (created_at_param,),
            ).fetchone()

            endpoint_rows = conn.execute(
                f"""
                SELECT
                    path,
                    COUNT(*) AS count,
                    SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count,
                    COALESCE(AVG(duration_ms), 0) AS avg_ms,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms)
                        FILTER (WHERE duration_ms IS NOT NULL) AS p50_ms,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)
                        FILTER (WHERE duration_ms IS NOT NULL) AS p95_ms
                FROM metric_events
                WHERE event_type = 'api_request'
                  AND path IS NOT NULL
                  AND path <> ''
                  AND {created_at_filter}
                GROUP BY path
                ORDER BY count DESC, path ASC
                LIMIT {self._placeholder()}
                """,
                (created_at_param, endpoint_limit),
            ).fetchall()

        total_events = self._safe_request_count(totals["request_count"])
        top_endpoints_payload: list[dict[str, Any]] = []
        for row in endpoint_rows:
            path = str(row["path"] or "").strip()
            endpoint_errors = self._safe_request_count(row["error_count"])
            endpoint_count = self._safe_request_count(row["count"])
            top_endpoints_payload.append(
                {
                    "path": path,
                    "count": endpoint_count,
                    "error_count": endpoint_errors,
                    "error_rate": round(endpoint_errors / endpoint_count, 4) if endpoint_count else 0,
                    "p50_ms": self._safe_duration(row["p50_ms"]),
                    "p95_ms": self._safe_duration(row["p95_ms"]),
                    "avg_ms": round(float(row["avg_ms"] or 0), 2),
                }
            )

        error_count = self._safe_request_count(totals["error_count"])
        duration_avg = float(totals["avg_duration_ms"] or 0)
        throughput_window_seconds = max(1, window * 60)

        return {
            "window_minutes": window,
            "total_api_requests": total_events,
            "error_count": error_count,
            "error_rate": round(error_count / total_events, 4) if total_events else 0,
            "throughput_rps": round(total_events / throughput_window_seconds, 4),
            "p50_ms": self._safe_duration(totals["p50_duration_ms"]),
            "p95_ms": self._safe_duration(totals["p95_duration_ms"]),
            "avg_ms": round(duration_avg, 2),
            "endpoint_overview": top_endpoints_payload,
            "totals": {
                "api_requests_total": self._safe_request_count(totals["api_requests_total"]),
                "request_bytes_total": self._safe_request_count(totals["request_bytes"]),
                "response_bytes_total": self._safe_request_count(totals["response_bytes"]),
                "resource_units_total": self._safe_request_count(totals["resource_units"]),
            },
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "backend": "postgres",
        }

    def healthcheck(self) -> dict[str, object]:
        return self.backend.healthcheck()

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT to_regclass(%s) AS regclass",
                ("public.metric_events",),
            ).fetchone()
            if not row or not row["regclass"]:
                return
            conn.execute("ALTER TABLE metric_events ADD COLUMN IF NOT EXISTS server_code TEXT")
            conn.execute(
                "ALTER TABLE metric_events ADD COLUMN IF NOT EXISTS meta_json JSONB NOT NULL DEFAULT '{}'::jsonb"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metric_events_server_code ON metric_events(server_code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metric_events_event_type ON metric_events(event_type)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metric_events_event_type_created_at ON metric_events(event_type, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metric_events_path_created_at ON metric_events(path, created_at DESC) WHERE path IS NOT NULL"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metric_events_username_created_at ON metric_events(username, created_at DESC) WHERE username IS NOT NULL"
            )
            conn.commit()

    def log_event(
        self,
        *,
        event_type: str,
        username: str = "",
        server_code: str = "",
        path: str = "",
        method: str = "",
        status_code: int | None = None,
        duration_ms: int | None = None,
        request_bytes: int | None = None,
        response_bytes: int | None = None,
        resource_units: int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        placeholder = self._placeholder()
        meta_value = json.dumps(meta or {}, ensure_ascii=False)
        insert_sql = f"""
            INSERT INTO metric_events (
                username,
                server_code,
                event_type,
                path,
                method,
                status_code,
                duration_ms,
                request_bytes,
                response_bytes,
                resource_units,
                meta_json
            )
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}::jsonb)
        """
        try:
            with closing(self._connect()) as conn:
                conn.execute(
                    insert_sql,
                    (
                        username.strip().lower() or None,
                        server_code.strip().lower() or None,
                        event_type,
                        path or None,
                        method or None,
                        status_code,
                        duration_ms,
                        request_bytes,
                        response_bytes,
                        resource_units,
                        meta_value,
                    ),
                )
                conn.commit()
        except (DatabaseUnavailableError, Exception):
            logger.exception("Failed to write admin metric event: %s %s", event_type, path)
            return False
        return True

    def log_ai_generation(
        self,
        *,
        username: str,
        server_code: str,
        flow: str,
        generation_id: str,
        path: str,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        payload = {"flow": str(flow or "").strip().lower(), "generation_id": str(generation_id or "").strip()}
        payload.update(meta or {})
        return self.log_event(
            event_type="ai_generation",
            username=username,
            server_code=server_code,
            path=path,
            method="POST",
            status_code=200,
            meta=payload,
            resource_units=int(payload.get("total_tokens") or payload.get("output_chars") or 0),
        )

    def log_ai_feedback(
        self,
        *,
        username: str,
        server_code: str,
        generation_id: str,
        flow: str,
        normalized_issues: list[str] | tuple[str, ...],
        note: str = "",
        expected_reference: str = "",
        helpful: bool | None = None,
    ) -> bool:
        payload = {
            "flow": str(flow or "").strip().lower(),
            "generation_id": str(generation_id or "").strip(),
            "issues": list(normalized_issues or ()),
            "note": str(note or "").strip(),
            "expected_reference": str(expected_reference or "").strip(),
            "helpful": helpful,
        }
        return self.log_event(
            event_type="ai_feedback",
            username=username,
            server_code=server_code,
            path="/api/ai/feedback",
            method="POST",
            status_code=200,
            meta=payload,
        )

    def _build_event_filters(
        self,
        *,
        event_search: str = "",
        event_type: str = "",
        failed_events_only: bool = False,
    ) -> tuple[list[str], list[Any]]:
        placeholder = self._placeholder()
        where_clauses: list[str] = []
        params: list[Any] = []
        normalized_event_search = str(event_search or "").strip().lower()
        normalized_event_type = str(event_type or "").strip().lower()
        if normalized_event_search:
            where_clauses.append(
                f"(LOWER(COALESCE(username, '')) LIKE {placeholder} OR LOWER(COALESCE(path, '')) LIKE {placeholder})"
            )
            search_pattern = f"%{normalized_event_search}%"
            params.extend([search_pattern, search_pattern])
        if normalized_event_type:
            where_clauses.append(f"LOWER(event_type) = {placeholder}")
            params.append(normalized_event_type)
        if failed_events_only:
            where_clauses.append("status_code IS NOT NULL AND status_code >= 400")
        return where_clauses, params

    def _load_recent_events(
        self,
        conn,
        *,
        event_search: str = "",
        event_type: str = "",
        failed_events_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        where_clauses, params = self._build_event_filters(
            event_search=event_search,
            event_type=event_type,
            failed_events_only=failed_events_only,
        )
        query = """
            SELECT created_at, username, server_code, event_type, path, method, status_code, duration_ms, request_bytes, response_bytes, resource_units, meta_json
            FROM metric_events
        """
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += f" ORDER BY id DESC LIMIT {self._placeholder()}"
        rows = conn.execute(query, (*params, limit)).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["meta"] = self._decode_json_field(item.pop("meta_json", None))
            events.append(item)
        return events

    def _load_top_endpoints(self, conn) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT path, COUNT(*) AS count
                FROM metric_events
                WHERE event_type = 'api_request' AND path IS NOT NULL
                GROUP BY path
                ORDER BY count DESC, path ASC
                LIMIT 10
                """
            ).fetchall()
        ]

    def _load_user_metrics(self, conn) -> dict[str, dict[str, Any]]:
        api_requests_24h_sql = (
            "SUM(CASE WHEN event_type = 'api_request' AND created_at >= NOW() - INTERVAL '1 day' THEN 1 ELSE 0 END)"
        )
        return {
            str(row["username"] or ""): dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    username,
                    MAX(server_code) AS server_code,
                    SUM(CASE WHEN event_type = 'api_request' THEN 1 ELSE 0 END) AS api_requests,
                    SUM(CASE WHEN event_type = 'api_request' AND status_code >= 400 THEN 1 ELSE 0 END) AS failed_api_requests,
                    {api_requests_24h_sql} AS api_requests_24h,
                    SUM(CASE WHEN event_type = 'complaint_generated' THEN 1 ELSE 0 END) AS complaints,
                    SUM(CASE WHEN event_type = 'rehab_generated' THEN 1 ELSE 0 END) AS rehabs,
                    SUM(CASE WHEN event_type = 'ai_suggest' THEN 1 ELSE 0 END) AS ai_suggestions,
                    SUM(CASE WHEN event_type = 'ai_extract_principal' THEN 1 ELSE 0 END) AS ai_ocr_requests,
                    COALESCE(SUM(request_bytes), 0) AS request_bytes,
                    COALESCE(SUM(response_bytes), 0) AS response_bytes,
                    COALESCE(SUM(resource_units), 0) AS resource_units,
                    MAX(created_at) AS last_seen_at
                FROM metric_events
                WHERE username IS NOT NULL AND username <> ''
                GROUP BY username
                """
            ).fetchall()
        }

    def _load_ai_exam_stats(
        self,
        conn,
        *,
        window_hours: int = 24,
        row_limit: int = 5000,
    ) -> dict[str, object]:
        stats = {
            "ai_exam_scoring_total": 0,
            "ai_exam_scoring_rows": 0,
            "ai_exam_scoring_answers": 0,
            "ai_exam_heuristic_total": 0,
            "ai_exam_cache_total": 0,
            "ai_exam_llm_total": 0,
            "ai_exam_llm_calls_total": 0,
            "ai_exam_failure_total": 0,
            "ai_exam_invalid_batch_items_total": 0,
            "ai_exam_retry_batch_items_total": 0,
            "ai_exam_retry_batch_calls_total": 0,
            "ai_exam_retry_single_items_total": 0,
            "ai_exam_retry_single_calls_total": 0,
            "ai_exam_scoring_ms_p50": None,
            "ai_exam_scoring_ms_p95": None,
        }
        scoped_window_hours = max(1, int(window_hours or 24))
        scoped_row_limit = max(100, int(row_limit or 5000))

        row = conn.execute(
            """
            WITH scoped_events AS (
                SELECT event_type, meta_json
                FROM metric_events
                WHERE event_type IN ('ai_exam_scoring', 'exam_import_score_failures', 'exam_import_row_score_error')
                  AND created_at >= NOW() - (%s::int * INTERVAL '1 hour')
                ORDER BY created_at DESC
                LIMIT %s
            )
            SELECT
                SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN 1 ELSE 0 END) AS ai_exam_scoring_total,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'rows_scored', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_scoring_rows,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'answer_count', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_scoring_answers,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'heuristic_count', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_heuristic_total,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'cache_hit_count', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_cache_total,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'llm_count', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_llm_total,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'llm_calls', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_llm_calls_total,
                COALESCE(SUM(CASE WHEN event_type <> 'ai_exam_scoring' THEN 1 ELSE 0 END), 0) AS ai_exam_failure_total,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'invalid_batch_item_count', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_invalid_batch_items_total,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'retry_batch_items', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_retry_batch_items_total,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'retry_batch_calls', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_retry_batch_calls_total,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'retry_single_items', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_retry_single_items_total,
                COALESCE(SUM(CASE WHEN event_type = 'ai_exam_scoring' THEN COALESCE(NULLIF(meta_json->>'retry_single_calls', ''), '0')::bigint ELSE 0 END), 0) AS ai_exam_retry_single_calls_total,
                percentile_cont(0.5) WITHIN GROUP (
                    ORDER BY CASE
                        WHEN COALESCE(meta_json->>'scoring_ms', '') ~ '^[0-9]+(?:\\.[0-9]+)?$'
                            THEN (meta_json->>'scoring_ms')::numeric
                        ELSE NULL
                    END
                ) FILTER (
                    WHERE event_type = 'ai_exam_scoring'
                      AND COALESCE(meta_json->>'scoring_ms', '') ~ '^[0-9]+(?:\\.[0-9]+)?$'
                ) AS ai_exam_scoring_ms_p50,
                percentile_cont(0.95) WITHIN GROUP (
                    ORDER BY CASE
                        WHEN COALESCE(meta_json->>'scoring_ms', '') ~ '^[0-9]+(?:\\.[0-9]+)?$'
                            THEN (meta_json->>'scoring_ms')::numeric
                        ELSE NULL
                    END
                ) FILTER (
                    WHERE event_type = 'ai_exam_scoring'
                      AND COALESCE(meta_json->>'scoring_ms', '') ~ '^[0-9]+(?:\\.[0-9]+)?$'
                ) AS ai_exam_scoring_ms_p95
            FROM scoped_events
            """,
            (scoped_window_hours, scoped_row_limit),
        ).fetchone()
        if row:
            for key in (
                "ai_exam_scoring_total",
                "ai_exam_scoring_rows",
                "ai_exam_scoring_answers",
                "ai_exam_heuristic_total",
                "ai_exam_cache_total",
                "ai_exam_llm_total",
                "ai_exam_llm_calls_total",
                "ai_exam_failure_total",
                "ai_exam_invalid_batch_items_total",
                "ai_exam_retry_batch_items_total",
                "ai_exam_retry_batch_calls_total",
                "ai_exam_retry_single_items_total",
                "ai_exam_retry_single_calls_total",
            ):
                stats[key] = self._safe_request_count(row[key])
            stats["ai_exam_scoring_ms_p50"] = self._safe_duration(row["ai_exam_scoring_ms_p50"])
            stats["ai_exam_scoring_ms_p95"] = self._safe_duration(row["ai_exam_scoring_ms_p95"])
        return stats

    def refresh_dashboard_materialized_views(self) -> None:
        """Best-effort refresh of optional dashboard materialized views.

        Dashboards are read-heavy, so environments can provision pre-aggregated
        materialized views and call this from a periodic job.
        """
        with closing(self._connect()) as conn:
            for view_name in ("admin_dashboard_overview_mv", "admin_dashboard_endpoint_mv"):
                row = conn.execute("SELECT to_regclass(%s) AS regclass", (f"public.{view_name}",)).fetchone()
                if row and row["regclass"]:
                    conn.execute(f"REFRESH MATERIALIZED VIEW {view_name}")
            conn.commit()

    def _load_latest_event(self, conn, event_types: tuple[str, ...]) -> dict[str, Any] | None:
        placeholders = ", ".join(self._placeholder() for _ in event_types)
        row = conn.execute(
            f"""
            SELECT created_at, username, server_code, event_type, path, status_code, meta_json
            FROM metric_events
            WHERE event_type IN ({placeholders})
            ORDER BY id DESC
            LIMIT 1
            """,
            event_types,
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["meta"] = self._decode_json_field(item.pop("meta_json", None))
        return item

    def get_exam_import_summary(self, *, pending_scores: int = 0) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            last_sync = self._load_latest_event(conn, ("api_request", "exam_import_sync_error"))
            if last_sync and last_sync.get("path") != "/api/exam-import/sync":
                last_sync = None
            last_score = self._load_latest_event(
                conn,
                ("ai_exam_scoring", "exam_import_score_failures", "exam_import_row_score_error"),
            )
            recent_failures = self._load_recent_events(
                conn,
                event_type="exam_import_score_failures",
                failed_events_only=False,
                limit=5,
            )
            row_failures = self._load_recent_events(
                conn,
                event_type="exam_import_row_score_error",
                failed_events_only=False,
                limit=5,
            )
        return {
            "pending_scores": int(pending_scores or 0),
            "last_sync": last_sync,
            "last_score": last_score,
            "recent_failures": recent_failures,
            "recent_row_failures": row_failures,
        }

    def _build_users_with_metrics(self, users: list[dict[str, Any]], user_metrics: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        users_with_metrics: list[dict[str, Any]] = []
        for user in users:
            username = str(user.get("username", "")).strip().lower()
            metrics = user_metrics.get(username, {})
            users_with_metrics.append(
                {
                    **user,
                    "email_verified": bool(user.get("email_verified_at")),
                    "access_blocked": bool(user.get("access_blocked_at")),
                    "is_tester": bool(int(user.get("is_tester") or 0)),
                    "is_gka": bool(int(user.get("is_gka") or 0)),
                    "api_requests": int(metrics.get("api_requests") or 0),
                    "failed_api_requests": int(metrics.get("failed_api_requests") or 0),
                    "api_requests_24h": int(metrics.get("api_requests_24h") or 0),
                    "complaints": int(metrics.get("complaints") or 0),
                    "rehabs": int(metrics.get("rehabs") or 0),
                    "ai_suggestions": int(metrics.get("ai_suggestions") or 0),
                    "ai_ocr_requests": int(metrics.get("ai_ocr_requests") or 0),
                    "request_bytes": int(metrics.get("request_bytes") or 0),
                    "response_bytes": int(metrics.get("response_bytes") or 0),
                    "resource_units": int(metrics.get("resource_units") or 0),
                    "last_seen_at": metrics.get("last_seen_at") or "",
                }
            )
        return users_with_metrics

    def _attach_risk_flags(self, users_with_metrics: list[dict[str, Any]]) -> None:
        for item in users_with_metrics:
            api_requests = int(item.get("api_requests") or 0)
            failed_api_requests = int(item.get("failed_api_requests") or 0)
            api_requests_24h = int(item.get("api_requests_24h") or 0)
            failure_rate = (failed_api_requests / api_requests) if api_requests else 0.0
            flags: list[str] = []
            score = 0
            if api_requests_24h >= 400:
                flags.append("burst_24h")
                score += 2
            if failure_rate >= 0.2 and api_requests >= 20:
                flags.append("high_error_rate")
                score += 2
            if api_requests >= 1500:
                flags.append("heavy_usage")
                score += 1
            item["risk_flags"] = flags
            item["risk_score"] = score

    def _filter_users(
        self,
        users_with_metrics: list[dict[str, Any]],
        *,
        search: str = "",
        blocked_only: bool = False,
        tester_only: bool = False,
        gka_only: bool = False,
        unverified_only: bool = False,
    ) -> list[dict[str, Any]]:
        normalized_search = str(search or "").strip().lower()
        filtered = list(users_with_metrics)
        if normalized_search:
            filtered = [
                item
                for item in filtered
                if normalized_search in str(item.get("username", "")).lower()
                or normalized_search in str(item.get("email", "")).lower()
            ]
        if blocked_only:
            filtered = [item for item in filtered if item.get("access_blocked")]
        if tester_only:
            filtered = [item for item in filtered if item.get("is_tester")]
        if gka_only:
            filtered = [item for item in filtered if item.get("is_gka")]
        if unverified_only:
            filtered = [item for item in filtered if not item.get("email_verified")]
        return filtered

    def _load_recent_ai_events(
        self,
        *,
        event_type: str,
        flow: str = "",
        issue_type: str = "",
        retrieval_context_mode: str = "",
        guard_warning: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            events = self._load_recent_events(conn, event_type=event_type, limit=max(1, int(limit or 50)))
        normalized_flow = str(flow or "").strip().lower()
        normalized_issue_type = str(issue_type or "").strip().lower()
        normalized_context_mode = str(retrieval_context_mode or "").strip().lower()
        normalized_guard_warning = str(guard_warning or "").strip().lower()
        filtered: list[dict[str, Any]] = []
        for item in events:
            meta = item.get("meta") or {}
            meta_flow = str(meta.get("flow") or "").strip().lower()
            if normalized_flow and meta_flow != normalized_flow:
                continue
            if normalized_context_mode:
                meta_context_mode = str(meta.get("retrieval_context_mode") or "").strip().lower()
                if meta_context_mode != normalized_context_mode:
                    continue
            if normalized_guard_warning:
                warnings = [str(value or "").strip().lower() for value in meta.get("guard_warnings") or []]
                if normalized_guard_warning not in warnings:
                    continue
            if normalized_issue_type:
                issues = [str(value or "").strip().lower() for value in meta.get("issues") or []]
                if normalized_issue_type not in issues:
                    continue
            filtered.append(item)
        return filtered

    def list_ai_generation_logs(
        self,
        *,
        flow: str = "",
        retrieval_context_mode: str = "",
        guard_warning: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self._load_recent_ai_events(
            event_type="ai_generation",
            flow=flow,
            retrieval_context_mode=retrieval_context_mode,
            guard_warning=guard_warning,
            limit=limit,
        )

    def list_ai_feedback(self, *, flow: str = "", issue_type: str = "", limit: int = 50) -> list[dict[str, Any]]:
        return self._load_recent_ai_events(
            event_type="ai_feedback",
            flow=flow,
            issue_type=issue_type,
            limit=limit,
        )

    def summarize_ai_generation_logs(
        self,
        *,
        flow: str = "",
        retrieval_context_mode: str = "",
        guard_warning: str = "",
        limit: int = 200,
    ) -> dict[str, Any]:
        rows = self.list_ai_generation_logs(
            flow=flow,
            retrieval_context_mode=retrieval_context_mode,
            guard_warning=guard_warning,
            limit=limit,
        )
        input_tokens: list[int] = []
        output_tokens: list[int] = []
        total_tokens: list[int] = []
        latency_values: list[int] = []
        retrieval_values: list[int] = []
        openai_values: list[int] = []
        total_suggest_values: list[int] = []
        estimated_cost_total = 0.0
        estimated_cost_count = 0
        budget_warning_count = 0
        models: dict[str, int] = {}
        retrieval_context_mode_counts: dict[str, int] = {}

        for row in rows:
            meta = row.get("meta") or {}
            model = str(meta.get("model") or "").strip()
            if model:
                models[model] = models.get(model, 0) + 1
            context_mode = str(meta.get("retrieval_context_mode") or "").strip().lower()
            if context_mode:
                retrieval_context_mode_counts[context_mode] = retrieval_context_mode_counts.get(context_mode, 0) + 1
            input_value = self._safe_request_count(meta.get("input_tokens"))
            output_value = self._safe_request_count(meta.get("output_tokens"))
            total_value = self._safe_request_count(meta.get("total_tokens"))
            latency_value = self._safe_duration(meta.get("latency_ms"))
            retrieval_value = self._safe_duration(meta.get("retrieval_ms"))
            openai_value = self._safe_duration(meta.get("openai_ms"))
            total_suggest_value = self._safe_duration(meta.get("total_suggest_ms"))
            if input_value:
                input_tokens.append(input_value)
            if output_value:
                output_tokens.append(output_value)
            if total_value:
                total_tokens.append(total_value)
            if latency_value is not None:
                latency_values.append(latency_value)
            if retrieval_value is not None:
                retrieval_values.append(retrieval_value)
            if openai_value is not None:
                openai_values.append(openai_value)
            if total_suggest_value is not None:
                total_suggest_values.append(total_suggest_value)
            cost_value = meta.get("estimated_cost_usd")
            try:
                if cost_value not in (None, ""):
                    estimated_cost_total += float(cost_value)
                    estimated_cost_count += 1
            except (TypeError, ValueError):
                pass
            warnings = meta.get("budget_warnings") or ()
            if isinstance(warnings, list) and warnings:
                budget_warning_count += 1

        return {
            "total_generations": len(rows),
            "models": models,
            "retrieval_context_mode_counts": retrieval_context_mode_counts,
            "input_tokens_total": sum(input_tokens),
            "output_tokens_total": sum(output_tokens),
            "total_tokens_total": sum(total_tokens),
            "input_tokens_p50": self._percentile(input_tokens, 0.5),
            "total_tokens_p95": self._percentile(total_tokens, 0.95),
            "latency_ms_p50": self._percentile(latency_values, 0.5),
            "latency_ms_p95": self._percentile(latency_values, 0.95),
            "retrieval_ms_p50": self._percentile(retrieval_values, 0.5),
            "retrieval_ms_p95": self._percentile(retrieval_values, 0.95),
            "openai_ms_p50": self._percentile(openai_values, 0.5),
            "openai_ms_p95": self._percentile(openai_values, 0.95),
            "total_suggest_ms_p50": self._percentile(total_suggest_values, 0.5),
            "total_suggest_ms_p95": self._percentile(total_suggest_values, 0.95),
            "estimated_cost_total_usd": round(estimated_cost_total, 6),
            "estimated_cost_samples": estimated_cost_count,
            "budget_warning_count": budget_warning_count,
        }

    def _sort_users(self, users_with_metrics: list[dict[str, Any]], *, user_sort: str = "complaints") -> None:
        normalized_sort = str(user_sort or "complaints").strip().lower()
        if normalized_sort not in USER_SORT_OPTIONS:
            normalized_sort = "complaints"

        if normalized_sort == "username":
            users_with_metrics.sort(key=lambda item: str(item.get("username") or "").lower())
            return
        if normalized_sort == "created_at":
            users_with_metrics.sort(
                key=lambda item: (
                    str(item.get("created_at") or "") == "",
                    str(item.get("created_at") or ""),
                    str(item.get("username") or "").lower(),
                ),
                reverse=True,
            )
            return
        if normalized_sort == "last_seen":
            users_with_metrics.sort(
                key=lambda item: (
                    str(item.get("last_seen_at") or "") == "",
                    str(item.get("last_seen_at") or ""),
                    str(item.get("username") or "").lower(),
                ),
                reverse=True,
            )
            return

        users_with_metrics.sort(
            key=lambda item: (
                -int(item.get(normalized_sort) or 0),
                -int(item.get("complaints") or 0),
                -int(item.get("api_requests") or 0),
                str(item.get("username") or "").lower(),
            )
        )

    def get_overview(
        self,
        *,
        users: list[dict[str, Any]],
        search: str = "",
        blocked_only: bool = False,
        tester_only: bool = False,
        gka_only: bool = False,
        unverified_only: bool = False,
        event_search: str = "",
        event_type: str = "",
        failed_events_only: bool = False,
        user_sort: str = "complaints",
    ) -> dict[str, Any]:
        events_last_24h_sql = "COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '1 day' THEN 1 ELSE 0 END), 0)"
        with closing(self._connect()) as conn:
            totals = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total_events,
                    SUM(CASE WHEN event_type = 'api_request' THEN 1 ELSE 0 END) AS api_requests_total,
                    SUM(CASE WHEN event_type = 'complaint_generated' THEN 1 ELSE 0 END) AS complaints_total,
                    SUM(CASE WHEN event_type = 'rehab_generated' THEN 1 ELSE 0 END) AS rehab_total,
                    SUM(CASE WHEN event_type = 'ai_suggest' THEN 1 ELSE 0 END) AS ai_suggest_total,
                    SUM(CASE WHEN event_type = 'ai_extract_principal' THEN 1 ELSE 0 END) AS ai_ocr_total,
                    COALESCE(SUM(request_bytes), 0) AS request_bytes_total,
                    COALESCE(SUM(response_bytes), 0) AS response_bytes_total,
                    COALESCE(SUM(resource_units), 0) AS resource_units_total,
                    COALESCE(AVG(CASE WHEN event_type = 'api_request' THEN duration_ms END), 0) AS avg_api_duration_ms,
                    {events_last_24h_sql} AS events_last_24h
                FROM metric_events
                """
            ).fetchone()
            top_endpoints = self._load_top_endpoints(conn)
            recent_events = self._load_recent_events(
                conn,
                event_search=event_search,
                event_type=event_type,
                failed_events_only=failed_events_only,
            )
            user_metrics = self._load_user_metrics(conn)
            ai_exam_stats = self._load_ai_exam_stats(conn)

        users_with_metrics = self._build_users_with_metrics(users, user_metrics)
        users_with_metrics = self._filter_users(
            users_with_metrics,
            search=search,
            blocked_only=blocked_only,
            tester_only=tester_only,
            gka_only=gka_only,
            unverified_only=unverified_only,
        )
        self._attach_risk_flags(users_with_metrics)
        self._sort_users(users_with_metrics, user_sort=user_sort)

        return {
            "totals": {
                "users_total": len(users),
                "events_total": int(totals["total_events"] or 0),
                "api_requests_total": int(totals["api_requests_total"] or 0),
                "complaints_total": int(totals["complaints_total"] or 0),
                "rehabs_total": int(totals["rehab_total"] or 0),
                "ai_suggest_total": int(totals["ai_suggest_total"] or 0),
                "ai_ocr_total": int(totals["ai_ocr_total"] or 0),
                "request_bytes_total": int(totals["request_bytes_total"] or 0),
                "response_bytes_total": int(totals["response_bytes_total"] or 0),
                "resource_units_total": int(totals["resource_units_total"] or 0),
                "avg_api_duration_ms": round(float(totals["avg_api_duration_ms"] or 0), 1),
                "events_last_24h": int(totals["events_last_24h"] or 0),
                **ai_exam_stats,
            },
            "users": users_with_metrics,
            "users_filtered_total": len(users_with_metrics),
            "top_endpoints": top_endpoints,
            "recent_events": recent_events,
            "recent_events_filtered_total": len(recent_events),
            "filters": {"user_sort": user_sort if user_sort in USER_SORT_OPTIONS else "complaints"},
        }

    def export_users_csv(
        self,
        *,
        users: list[dict[str, Any]],
        search: str = "",
        blocked_only: bool = False,
        tester_only: bool = False,
        gka_only: bool = False,
        unverified_only: bool = False,
        user_sort: str = "complaints",
    ) -> str:
        with closing(self._connect()) as conn:
            user_metrics = self._load_user_metrics(conn)
        users_with_metrics = self._build_users_with_metrics(users, user_metrics)
        users_with_metrics = self._filter_users(
            users_with_metrics,
            search=search,
            blocked_only=blocked_only,
            tester_only=tester_only,
            gka_only=gka_only,
            unverified_only=unverified_only,
        )
        self._sort_users(users_with_metrics, user_sort=user_sort)

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "username",
                "email",
                "created_at",
                "email_verified",
                "access_blocked",
                "access_blocked_reason",
                "is_tester",
                "is_gka",
                "complaints",
                "rehabs",
                "api_requests",
                "ai_suggestions",
                "ai_ocr_requests",
                "resource_units",
                "last_seen_at",
            ]
        )
        for item in users_with_metrics:
            writer.writerow(
                [
                    item.get("username", ""),
                    item.get("email", ""),
                    item.get("created_at", ""),
                    "yes" if item.get("email_verified") else "no",
                    "yes" if item.get("access_blocked") else "no",
                    item.get("access_blocked_reason", ""),
                    "yes" if item.get("is_tester") else "no",
                    "yes" if item.get("is_gka") else "no",
                    int(item.get("complaints") or 0),
                    int(item.get("rehabs") or 0),
                    int(item.get("api_requests") or 0),
                    int(item.get("ai_suggestions") or 0),
                    int(item.get("ai_ocr_requests") or 0),
                    int(item.get("resource_units") or 0),
                    item.get("last_seen_at", ""),
                ]
            )
        return output.getvalue()

    def export_events_csv(
        self,
        *,
        event_search: str = "",
        event_type: str = "",
        failed_events_only: bool = False,
        limit: int = 500,
    ) -> str:
        with closing(self._connect()) as conn:
            events = self._load_recent_events(
                conn,
                event_search=event_search,
                event_type=event_type,
                failed_events_only=failed_events_only,
                limit=limit,
            )
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "created_at",
                "username",
                "event_type",
                "path",
                "method",
                "status_code",
                "duration_ms",
                "request_bytes",
                "response_bytes",
                "resource_units",
                "meta_json",
            ]
        )
        for item in events:
            writer.writerow(
                [
                    item.get("created_at", ""),
                    item.get("username", ""),
                    item.get("event_type", ""),
                    item.get("path", ""),
                    item.get("method", ""),
                    item.get("status_code", ""),
                    item.get("duration_ms", ""),
                    item.get("request_bytes", ""),
                    item.get("response_bytes", ""),
                    item.get("resource_units", ""),
                    json.dumps(item.get("meta") or {}, ensure_ascii=False),
                ]
            )
        return output.getvalue()

    def list_error_events(
        self,
        *,
        event_search: str = "",
        event_type: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            return self._load_recent_events(
                conn,
                event_search=event_search,
                event_type=event_type,
                failed_events_only=True,
                limit=max(1, int(limit or 100)),
            )


_DEFAULT_ADMIN_METRICS_STORE: AdminMetricsStore | None = None


def get_default_admin_metrics_store() -> AdminMetricsStore:
    global _DEFAULT_ADMIN_METRICS_STORE
    if _DEFAULT_ADMIN_METRICS_STORE is None:
        _DEFAULT_ADMIN_METRICS_STORE = AdminMetricsStore(DB_PATH, backend=get_database_backend())
    return _DEFAULT_ADMIN_METRICS_STORE
