from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.db.sqlite_to_postgres import migrate_sqlite_to_postgres
from tests.temp_helpers import make_temporary_directory


class FakeMigrationTarget:
    def __init__(self) -> None:
        self.servers: dict[str, str] = {}
        self.users: dict[str, tuple[object, ...]] = {}
        self.roles: dict[tuple[str, str], tuple[bool, bool, bool]] = {}
        self.drafts: dict[tuple[str, str], tuple[str, str | None]] = {}
        self.metric_signatures: set[tuple[object, ...]] = set()
        self.answers: dict[int, tuple[object, ...]] = {}
        self.tasks: dict[str, tuple[object, ...]] = {}

    def ensure_servers(self, servers: dict[str, str], *, dry_run: bool = False) -> None:
        if not dry_run:
            self.servers.update(servers)

    def fetch_existing_users(self) -> dict[str, tuple[object, ...]]:
        return dict(self.users)

    def upsert_user(self, payload: dict[str, object], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.users[str(payload["username"])] = (
            payload["email"],
            payload["salt"],
            payload["password_hash"],
            payload["created_at"],
            payload["email_verified_at"],
            payload["email_verification_token_hash"],
            payload["email_verification_sent_at"],
            payload["password_reset_token_hash"],
            payload["password_reset_sent_at"],
            payload["access_blocked_at"],
            payload["access_blocked_reason"],
            payload["representative_profile_json"],
        )

    def fetch_existing_roles(self) -> dict[tuple[str, str], tuple[bool, bool, bool]]:
        return dict(self.roles)

    def upsert_role(self, payload: dict[str, object], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.roles[(str(payload["username"]), str(payload["server_code"]))] = (
            bool(payload["is_tester"]),
            bool(payload["is_gka"]),
            bool(payload["is_active"]),
        )

    def fetch_existing_drafts(self) -> dict[tuple[str, str], tuple[str, str | None]]:
        return dict(self.drafts)

    def upsert_draft(self, payload: dict[str, object], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.drafts[(str(payload["username"]), str(payload["server_code"]))] = (
            str(payload["draft_json"]),
            payload["updated_at"] if payload["updated_at"] is None else str(payload["updated_at"]),
        )

    def fetch_existing_metric_signatures(self) -> set[tuple[object, ...]]:
        return set(self.metric_signatures)

    def insert_metric_event(self, payload: dict[str, object], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.metric_signatures.add(
            (
                payload["created_at"],
                payload["username"],
                payload["server_code"],
                payload["event_type"],
                payload["path"],
                payload["method"],
                payload["status_code"],
                payload["duration_ms"],
                payload["request_bytes"],
                payload["response_bytes"],
                payload["resource_units"],
                payload["meta_json"],
            )
        )

    def fetch_existing_exam_answers(self) -> dict[int, tuple[object, ...]]:
        return dict(self.answers)

    def upsert_exam_answer(self, payload: dict[str, object], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.answers[int(payload["source_row"])] = (
            payload["submitted_at"],
            payload["full_name"],
            payload["discord_tag"],
            payload["passport"],
            payload["exam_format"],
            payload["payload_json"],
            payload["answer_count"],
            payload["imported_at"],
            payload["updated_at"],
            payload["question_g_score"],
            payload["question_g_rationale"],
            payload["question_g_scored_at"],
            payload["exam_scores_json"],
            payload["exam_scores_scored_at"],
            payload["average_score"],
            payload["average_score_answer_count"],
            payload["average_score_scored_at"],
            payload["needs_rescore"],
            payload["import_key"],
        )

    def fetch_existing_exam_import_tasks(self) -> dict[str, tuple[object, ...]]:
        return dict(self.tasks)

    def upsert_exam_import_task(self, payload: dict[str, object], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.tasks[str(payload["id"])] = (
            payload["task_type"],
            payload["source_row"],
            payload["status"],
            payload["created_at"],
            payload["started_at"],
            payload["finished_at"],
            payload["error"],
            payload["progress_json"],
            payload["result_json"],
        )


class SQLiteToPostgresMigrationTests(unittest.TestCase):
    def _create_source_dbs(self, root: Path) -> None:
        app_db = root / "app.db"
        conn = sqlite3.connect(str(app_db))
        try:
            conn.execute(
                """
                CREATE TABLE users (
                    username TEXT PRIMARY KEY,
                    email TEXT,
                    salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    email_verified_at TEXT,
                    email_verification_token_hash TEXT,
                    email_verification_sent_at TEXT,
                    password_reset_token_hash TEXT,
                    password_reset_sent_at TEXT,
                    access_blocked_at TEXT,
                    access_blocked_reason TEXT,
                    server_code TEXT NOT NULL DEFAULT 'blackberry',
                    is_tester INTEGER NOT NULL DEFAULT 0,
                    is_gka INTEGER NOT NULL DEFAULT 0,
                    representative_profile TEXT NOT NULL,
                    complaint_draft_json TEXT,
                    complaint_draft_updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO users (
                    username, email, salt, password_hash, created_at, email_verified_at,
                    server_code, is_tester, is_gka, representative_profile,
                    complaint_draft_json, complaint_draft_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "alpha",
                    "alpha@example.com",
                    "salt-a",
                    "hash-a",
                    "2026-04-10T10:00:00+00:00",
                    "2026-04-10T10:05:00+00:00",
                    "blackberry",
                    1,
                    0,
                    '{"name":"Alpha"}',
                    '{"subject":"draft"}',
                    "2026-04-10T10:06:00+00:00",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        metrics_db = root / "admin_metrics.db"
        conn = sqlite3.connect(str(metrics_db))
        try:
            conn.execute(
                """
                CREATE TABLE metric_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    username TEXT,
                    server_code TEXT,
                    event_type TEXT NOT NULL,
                    path TEXT,
                    method TEXT,
                    status_code INTEGER,
                    duration_ms INTEGER,
                    request_bytes INTEGER,
                    response_bytes INTEGER,
                    resource_units INTEGER,
                    meta_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO metric_events (
                    created_at, username, server_code, event_type, path, method,
                    status_code, duration_ms, request_bytes, response_bytes, resource_units, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-04-10T11:00:00+00:00",
                    "alpha",
                    "blackberry",
                    "api_request",
                    "/api/demo",
                    "GET",
                    200,
                    45,
                    12,
                    34,
                    1,
                    '{"ok": true}',
                ),
            )
            conn.commit()
        finally:
            conn.close()

        answers_db = root / "exam_answers.db"
        conn = sqlite3.connect(str(answers_db))
        try:
            conn.execute(
                """
                CREATE TABLE exam_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_row INTEGER NOT NULL UNIQUE,
                    submitted_at TEXT,
                    full_name TEXT,
                    discord_tag TEXT,
                    passport TEXT,
                    exam_format TEXT,
                    payload_json TEXT NOT NULL,
                    answer_count INTEGER NOT NULL,
                    imported_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    question_g_score INTEGER,
                    question_g_rationale TEXT,
                    question_g_scored_at TEXT,
                    exam_scores_json TEXT,
                    exam_scores_scored_at TEXT,
                    average_score REAL,
                    average_score_answer_count INTEGER,
                    average_score_scored_at TEXT,
                    needs_rescore INTEGER NOT NULL,
                    import_key TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO exam_answers (
                    source_row, submitted_at, full_name, discord_tag, passport, exam_format,
                    payload_json, answer_count, imported_at, updated_at, question_g_score,
                    question_g_rationale, question_g_scored_at, exam_scores_json,
                    exam_scores_scored_at, average_score, average_score_answer_count,
                    average_score_scored_at, needs_rescore, import_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    5,
                    "2026-04-10 12:00",
                    "Alpha User",
                    "@alpha",
                    "AA123",
                    "base",
                    '{"answers":["A"]}',
                    1,
                    "2026-04-10T12:01:00+00:00",
                    "2026-04-10T12:02:00+00:00",
                    5,
                    "ok",
                    "2026-04-10T12:03:00+00:00",
                    '[{"score":5}]',
                    "2026-04-10T12:04:00+00:00",
                    5.0,
                    1,
                    "2026-04-10T12:05:00+00:00",
                    0,
                    "k1",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        tasks_db = root / "exam_import_tasks.db"
        conn = sqlite3.connect(str(tasks_db))
        try:
            conn.execute(
                """
                CREATE TABLE exam_import_tasks (
                    id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    source_row INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    progress_json TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                INSERT INTO exam_import_tasks (
                    id, task_type, source_row, status, created_at, started_at, finished_at,
                    error, progress_json, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "task-1",
                    "sync",
                    5,
                    "completed",
                    "2026-04-10T13:00:00+00:00",
                    "2026-04-10T13:00:01+00:00",
                    "2026-04-10T13:00:02+00:00",
                    "",
                    '{"step":1}',
                    '{"ok":true}',
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def test_migration_is_idempotent_for_repeated_runs(self):
        with make_temporary_directory() as tmp:
            source_dir = Path(tmp)
            self._create_source_dbs(source_dir)
            target = FakeMigrationTarget()

            first = migrate_sqlite_to_postgres(source_dir=source_dir, target=target, dry_run=False)
            second = migrate_sqlite_to_postgres(source_dir=source_dir, target=target, dry_run=False)

            self.assertEqual(first["tables"]["users"]["inserted"], 1)
            self.assertEqual(first["tables"]["user_server_roles"]["inserted"], 1)
            self.assertEqual(first["tables"]["complaint_drafts"]["inserted"], 1)
            self.assertEqual(first["tables"]["metric_events"]["inserted"], 1)
            self.assertEqual(first["tables"]["exam_answers"]["inserted"], 1)
            self.assertEqual(first["tables"]["exam_import_tasks"]["inserted"], 1)

            self.assertEqual(second["tables"]["users"]["skipped"], 1)
            self.assertEqual(second["tables"]["user_server_roles"]["skipped"], 1)
            self.assertEqual(second["tables"]["complaint_drafts"]["skipped"], 1)
            self.assertEqual(second["tables"]["metric_events"]["skipped"], 1)
            self.assertEqual(second["tables"]["exam_answers"]["skipped"], 1)
            self.assertEqual(second["tables"]["exam_import_tasks"]["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
