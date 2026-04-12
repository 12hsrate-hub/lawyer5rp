from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
WEB_DIR = ROOT_DIR / "web"

if str(ROOT_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT_DIR))
if str(WEB_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(WEB_DIR))

from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.db.factory import get_database_backend


def _run_query(conn, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _profile_postgres(conn, query: str, params: tuple[Any, ...], description: str) -> None:
    rows = _run_query(conn, f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {query}", params)
    print(f"\n-- {description}")
    for row in rows:
        plan = row.get("QUERY PLAN") or row.get("query_plan") or str(row)
        print(plan)


def profile(db_backend) -> None:
    admin_store = AdminMetricsStore(ROOT_DIR / "web" / "data" / "admin_metrics.db", backend=db_backend)
    exam_store = ExamAnswersStore(ROOT_DIR / "web" / "data" / "exam_answers.db", backend=db_backend)

    admin_conn = admin_store._connect()
    exam_conn = exam_store._connect()
    try:
        if not admin_store.is_postgres_backend:
            raise RuntimeError("perf_sql_profile.py supports PostgreSQL backend only.")

        _profile_postgres(
            admin_conn,
            "SELECT COUNT(*) FROM metric_events WHERE event_type = $1 AND created_at >= $2",
            ("api_request", "2000-01-01T00:00:00"),
            "metric_events api_request + created_at",
        )

        _profile_postgres(
            admin_conn,
            "SELECT path, COUNT(*) FROM metric_events WHERE event_type = $1 AND path IS NOT NULL GROUP BY path",
            ("api_request",),
            "metric_events top endpoints",
        )

        _profile_postgres(
            exam_conn,
            "SELECT source_row, submitted_at, full_name FROM exam_answers WHERE source_row > 0 AND (average_score IS NULL OR needs_rescore IS TRUE) ORDER BY source_row ASC LIMIT 500",
            (),
            "exam_answers pending score candidates",
        )

        _profile_postgres(
            exam_conn,
            "SELECT source_row, submitted_at, full_name FROM exam_answers WHERE source_row > 0 AND exam_scores_json IS NOT NULL AND exam_scores_json <> '' ORDER BY source_row ASC LIMIT 500",
            (),
            "exam_answers failed score payload scan",
        )
    finally:
        exam_conn.close()
        admin_conn.close()


def main() -> int:
    if not os.getenv("DATABASE_URL", "").strip():
        raise SystemExit("DATABASE_URL is required for perf_sql_profile.py.")
    parser = argparse.ArgumentParser(description="Profile key SQL plans for performance-sensitive paths.")
    parser.add_argument(
        "--backend",
        choices=["postgres"],
        default=None,
        help="Override database backend for this profile run.",
    )
    args = parser.parse_args()
    if args.backend:
        os.environ["OGP_DB_BACKEND"] = args.backend
    profile(get_database_backend())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
