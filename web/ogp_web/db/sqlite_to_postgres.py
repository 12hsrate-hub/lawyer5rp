from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ogp_web.storage.profile_codec import dump_profile_json, load_profile_json


APP_DB_NAME = "app.db"
ADMIN_METRICS_DB_NAME = "admin_metrics.db"
EXAM_ANSWERS_DB_NAME = "exam_answers.db"
EXAM_IMPORT_TASKS_DB_NAME = "exam_import_tasks.db"
DEFAULT_SERVER_CODE = "blackberry"
REPRESENTATIVE_PROFILE_DEFAULTS = {
    "name": "",
    "passport": "",
    "address": "",
    "phone": "",
    "discord": "",
    "passport_scan_url": "",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _normalize_optional_text(value: Any) -> str | None:
    text = _normalize_text(value)
    return text or None


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "0", 0):
        return False
    if value in ("1", 1):
        return True
    return bool(value)


def _normalize_json_text(value: Any, *, default: Any) -> str:
    if isinstance(value, (dict, list)):
        parsed = value
    else:
        raw = _normalize_text(value)
        if not raw:
            parsed = default
        else:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = default
    if isinstance(default, dict) and not isinstance(parsed, dict):
        parsed = default
    if isinstance(default, list) and not isinstance(parsed, list):
        parsed = default
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True)


def _server_title(server_code: str) -> str:
    normalized = _normalize_text(server_code, default=DEFAULT_SERVER_CODE).lower() or DEFAULT_SERVER_CODE
    if normalized == DEFAULT_SERVER_CODE:
        return "BlackBerry"
    return normalized.replace("_", " ").replace("-", " ").title()


def _read_sqlite_rows(db_path: Path, table: str) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if table_exists is None:
            return []
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
    finally:
        conn.close()


@dataclass
class TableReport:
    source: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "source": self.source,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
        }


class MigrationTarget(Protocol):
    def ensure_servers(self, servers: dict[str, str], *, dry_run: bool = False) -> None: ...

    def fetch_existing_users(self) -> dict[str, tuple[Any, ...]]: ...

    def upsert_user(self, payload: dict[str, Any], *, dry_run: bool = False) -> None: ...

    def fetch_existing_roles(self) -> dict[tuple[str, str], tuple[bool, bool, bool]]: ...

    def upsert_role(self, payload: dict[str, Any], *, dry_run: bool = False) -> None: ...

    def fetch_existing_drafts(self) -> dict[tuple[str, str], tuple[str, str | None]]: ...

    def upsert_draft(self, payload: dict[str, Any], *, dry_run: bool = False) -> None: ...

    def fetch_existing_metric_signatures(self) -> set[tuple[Any, ...]]: ...

    def insert_metric_event(self, payload: dict[str, Any], *, dry_run: bool = False) -> None: ...

    def fetch_existing_exam_answers(self) -> dict[int, tuple[Any, ...]]: ...

    def upsert_exam_answer(self, payload: dict[str, Any], *, dry_run: bool = False) -> None: ...

    def fetch_existing_exam_import_tasks(self) -> dict[str, tuple[Any, ...]]: ...

    def upsert_exam_import_task(self, payload: dict[str, Any], *, dry_run: bool = False) -> None: ...


class PostgresMigrationTarget:
    def __init__(self, conn) -> None:
        self.conn = conn

    def ensure_servers(self, servers: dict[str, str], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        for code, title in servers.items():
            self.conn.execute(
                """
                INSERT INTO servers (code, title)
                VALUES (%s, %s)
                ON CONFLICT (code) DO NOTHING
                """,
                (code, title),
            )

    def fetch_existing_users(self) -> dict[str, tuple[Any, ...]]:
        rows = self.conn.execute(
            """
            SELECT
                username,
                email,
                salt,
                password_hash,
                created_at,
                email_verified_at,
                email_verification_token_hash,
                email_verification_sent_at,
                password_reset_token_hash,
                password_reset_sent_at,
                access_blocked_at,
                access_blocked_reason,
                CAST(representative_profile AS TEXT) AS representative_profile_json
            FROM users
            """
        ).fetchall()
        return {
            str(row["username"]): (
                row["email"],
                row["salt"],
                row["password_hash"],
                str(row["created_at"] or ""),
                row["email_verified_at"],
                row["email_verification_token_hash"],
                row["email_verification_sent_at"],
                row["password_reset_token_hash"],
                row["password_reset_sent_at"],
                row["access_blocked_at"],
                row["access_blocked_reason"],
                _normalize_json_text(row["representative_profile_json"], default={}),
            )
            for row in rows
        }

    def upsert_user(self, payload: dict[str, Any], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.conn.execute(
            """
            INSERT INTO users (
                username,
                email,
                salt,
                password_hash,
                created_at,
                email_verified_at,
                email_verification_token_hash,
                email_verification_sent_at,
                password_reset_token_hash,
                password_reset_sent_at,
                access_blocked_at,
                access_blocked_reason,
                representative_profile
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (username)
            DO UPDATE SET
                email = EXCLUDED.email,
                salt = EXCLUDED.salt,
                password_hash = EXCLUDED.password_hash,
                created_at = EXCLUDED.created_at,
                email_verified_at = EXCLUDED.email_verified_at,
                email_verification_token_hash = EXCLUDED.email_verification_token_hash,
                email_verification_sent_at = EXCLUDED.email_verification_sent_at,
                password_reset_token_hash = EXCLUDED.password_reset_token_hash,
                password_reset_sent_at = EXCLUDED.password_reset_sent_at,
                access_blocked_at = EXCLUDED.access_blocked_at,
                access_blocked_reason = EXCLUDED.access_blocked_reason,
                representative_profile = EXCLUDED.representative_profile
            """,
            (
                payload["username"],
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
            ),
        )

    def fetch_existing_roles(self) -> dict[tuple[str, str], tuple[bool, bool, bool]]:
        rows = self.conn.execute(
            """
            SELECT u.username, usr.server_code, usr.is_tester, usr.is_gka, usr.is_active
            FROM user_server_roles usr
            JOIN users u ON u.id = usr.user_id
            """
        ).fetchall()
        return {
            (str(row["username"]), str(row["server_code"])): (
                bool(row["is_tester"]),
                bool(row["is_gka"]),
                bool(row["is_active"]),
            )
            for row in rows
        }

    def upsert_role(self, payload: dict[str, Any], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.conn.execute(
            """
            INSERT INTO user_server_roles (user_id, server_code, is_tester, is_gka, is_active)
            SELECT id, %s, %s, %s, %s
            FROM users
            WHERE username = %s
            ON CONFLICT (user_id, server_code)
            DO UPDATE SET
                is_tester = EXCLUDED.is_tester,
                is_gka = EXCLUDED.is_gka,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
            """,
            (
                payload["server_code"],
                payload["is_tester"],
                payload["is_gka"],
                payload["is_active"],
                payload["username"],
            ),
        )

    def fetch_existing_drafts(self) -> dict[tuple[str, str], tuple[str, str | None]]:
        rows = self.conn.execute(
            """
            SELECT u.username, cd.server_code, CAST(cd.draft_json AS TEXT) AS draft_json, cd.updated_at
            FROM complaint_drafts cd
            JOIN users u ON u.id = cd.user_id
            """
        ).fetchall()
        return {
            (str(row["username"]), str(row["server_code"])): (
                _normalize_json_text(row["draft_json"], default={}),
                _normalize_optional_text(row["updated_at"]),
            )
            for row in rows
        }

    def upsert_draft(self, payload: dict[str, Any], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.conn.execute(
            """
            INSERT INTO complaint_drafts (user_id, server_code, draft_json, updated_at)
            SELECT id, %s, %s::jsonb, COALESCE(%s, NOW())
            FROM users
            WHERE username = %s
            ON CONFLICT (user_id, server_code)
            DO UPDATE SET
                draft_json = EXCLUDED.draft_json,
                updated_at = EXCLUDED.updated_at
            """,
            (
                payload["server_code"],
                payload["draft_json"],
                payload["updated_at"],
                payload["username"],
            ),
        )

    def fetch_existing_metric_signatures(self) -> set[tuple[Any, ...]]:
        rows = self.conn.execute(
            """
            SELECT created_at, username, server_code, event_type, path, method, status_code,
                   duration_ms, request_bytes, response_bytes, resource_units,
                   CAST(meta_json AS TEXT) AS meta_json
            FROM metric_events
            """
        ).fetchall()
        return {
            _metric_signature(
                {
                    "created_at": _normalize_optional_text(row["created_at"]),
                    "username": _normalize_optional_text(row["username"]),
                    "server_code": _normalize_optional_text(row["server_code"]),
                    "event_type": _normalize_text(row["event_type"]),
                    "path": _normalize_optional_text(row["path"]),
                    "method": _normalize_optional_text(row["method"]),
                    "status_code": row["status_code"],
                    "duration_ms": row["duration_ms"],
                    "request_bytes": row["request_bytes"],
                    "response_bytes": row["response_bytes"],
                    "resource_units": row["resource_units"],
                    "meta_json": _normalize_json_text(row["meta_json"], default={}),
                }
            )
            for row in rows
        }

    def insert_metric_event(self, payload: dict[str, Any], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.conn.execute(
            """
            INSERT INTO metric_events (
                created_at,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
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
            ),
        )

    def fetch_existing_exam_answers(self) -> dict[int, tuple[Any, ...]]:
        rows = self.conn.execute(
            """
            SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format,
                   CAST(payload_json AS TEXT) AS payload_json, answer_count, imported_at, updated_at,
                   question_g_score, question_g_rationale, question_g_scored_at,
                   CAST(exam_scores_json AS TEXT) AS exam_scores_json, exam_scores_scored_at,
                   average_score, average_score_answer_count, average_score_scored_at,
                   needs_rescore, import_key
            FROM exam_answers
            """
        ).fetchall()
        return {
            int(row["source_row"]): _answer_signature(
                {
                    "source_row": int(row["source_row"]),
                    "submitted_at": _normalize_optional_text(row["submitted_at"]),
                    "full_name": _normalize_optional_text(row["full_name"]),
                    "discord_tag": _normalize_optional_text(row["discord_tag"]),
                    "passport": _normalize_optional_text(row["passport"]),
                    "exam_format": _normalize_optional_text(row["exam_format"]),
                    "payload_json": _normalize_json_text(row["payload_json"], default={}),
                    "answer_count": int(row["answer_count"] or 0),
                    "imported_at": _normalize_text(row["imported_at"]),
                    "updated_at": _normalize_text(row["updated_at"]),
                    "question_g_score": row["question_g_score"],
                    "question_g_rationale": _normalize_optional_text(row["question_g_rationale"]),
                    "question_g_scored_at": _normalize_optional_text(row["question_g_scored_at"]),
                    "exam_scores_json": _normalize_optional_text(row["exam_scores_json"]),
                    "exam_scores_scored_at": _normalize_optional_text(row["exam_scores_scored_at"]),
                    "average_score": row["average_score"],
                    "average_score_answer_count": row["average_score_answer_count"],
                    "average_score_scored_at": _normalize_optional_text(row["average_score_scored_at"]),
                    "needs_rescore": bool(row["needs_rescore"]),
                    "import_key": _normalize_optional_text(row["import_key"]),
                }
            )
            for row in rows
        }

    def upsert_exam_answer(self, payload: dict[str, Any], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.conn.execute(
            """
            INSERT INTO exam_answers (
                source_row,
                submitted_at,
                full_name,
                discord_tag,
                passport,
                exam_format,
                payload_json,
                answer_count,
                imported_at,
                updated_at,
                question_g_score,
                question_g_rationale,
                question_g_scored_at,
                exam_scores_json,
                exam_scores_scored_at,
                average_score,
                average_score_answer_count,
                average_score_scored_at,
                needs_rescore,
                import_key
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_row)
            DO UPDATE SET
                submitted_at = EXCLUDED.submitted_at,
                full_name = EXCLUDED.full_name,
                discord_tag = EXCLUDED.discord_tag,
                passport = EXCLUDED.passport,
                exam_format = EXCLUDED.exam_format,
                payload_json = EXCLUDED.payload_json,
                answer_count = EXCLUDED.answer_count,
                imported_at = EXCLUDED.imported_at,
                updated_at = EXCLUDED.updated_at,
                question_g_score = EXCLUDED.question_g_score,
                question_g_rationale = EXCLUDED.question_g_rationale,
                question_g_scored_at = EXCLUDED.question_g_scored_at,
                exam_scores_json = EXCLUDED.exam_scores_json,
                exam_scores_scored_at = EXCLUDED.exam_scores_scored_at,
                average_score = EXCLUDED.average_score,
                average_score_answer_count = EXCLUDED.average_score_answer_count,
                average_score_scored_at = EXCLUDED.average_score_scored_at,
                needs_rescore = EXCLUDED.needs_rescore,
                import_key = EXCLUDED.import_key
            """,
            (
                payload["source_row"],
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
            ),
        )

    def fetch_existing_exam_import_tasks(self) -> dict[str, tuple[Any, ...]]:
        rows = self.conn.execute(
            """
            SELECT id, task_type, source_row, status, created_at, started_at, finished_at,
                   error, CAST(progress_json AS TEXT) AS progress_json, CAST(result_json AS TEXT) AS result_json
            FROM exam_import_tasks
            """
        ).fetchall()
        return {
            str(row["id"]): _task_signature(
                {
                    "id": str(row["id"]),
                    "task_type": _normalize_text(row["task_type"]),
                    "source_row": row["source_row"],
                    "status": _normalize_text(row["status"]),
                    "created_at": _normalize_text(row["created_at"]),
                    "started_at": _normalize_optional_text(row["started_at"]),
                    "finished_at": _normalize_optional_text(row["finished_at"]),
                    "error": _normalize_text(row["error"]),
                    "progress_json": _normalize_json_text(row["progress_json"], default={}),
                    "result_json": _normalize_json_text(row["result_json"], default={}),
                }
            )
            for row in rows
        }

    def upsert_exam_import_task(self, payload: dict[str, Any], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.conn.execute(
            """
            INSERT INTO exam_import_tasks (
                id,
                task_type,
                source_row,
                status,
                created_at,
                started_at,
                finished_at,
                error,
                progress_json,
                result_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            ON CONFLICT (id)
            DO UPDATE SET
                task_type = EXCLUDED.task_type,
                source_row = EXCLUDED.source_row,
                status = EXCLUDED.status,
                created_at = EXCLUDED.created_at,
                started_at = EXCLUDED.started_at,
                finished_at = EXCLUDED.finished_at,
                error = EXCLUDED.error,
                progress_json = EXCLUDED.progress_json,
                result_json = EXCLUDED.result_json
            """,
            (
                payload["id"],
                payload["task_type"],
                payload["source_row"],
                payload["status"],
                payload["created_at"],
                payload["started_at"],
                payload["finished_at"],
                payload["error"],
                payload["progress_json"],
                payload["result_json"],
            ),
        )


def _build_user_payload(row: dict[str, Any]) -> dict[str, Any]:
    profile = load_profile_json(
        _normalize_text(row.get("representative_profile")),
        REPRESENTATIVE_PROFILE_DEFAULTS,
    )
    profile_json = dump_profile_json(profile, REPRESENTATIVE_PROFILE_DEFAULTS)
    return {
        "username": _normalize_text(row.get("username")).lower(),
        "email": _normalize_optional_text(row.get("email")),
        "salt": _normalize_text(row.get("salt")),
        "password_hash": _normalize_text(row.get("password_hash")),
        "created_at": _normalize_text(row.get("created_at"), default=_utc_now_iso()),
        "email_verified_at": _normalize_optional_text(row.get("email_verified_at")),
        "email_verification_token_hash": _normalize_optional_text(row.get("email_verification_token_hash")),
        "email_verification_sent_at": _normalize_optional_text(row.get("email_verification_sent_at")),
        "password_reset_token_hash": _normalize_optional_text(row.get("password_reset_token_hash")),
        "password_reset_sent_at": _normalize_optional_text(row.get("password_reset_sent_at")),
        "access_blocked_at": _normalize_optional_text(row.get("access_blocked_at")),
        "access_blocked_reason": _normalize_optional_text(row.get("access_blocked_reason")),
        "representative_profile_json": profile_json,
    }


def _build_role_payload(row: dict[str, Any]) -> dict[str, Any]:
    server_code = _normalize_text(row.get("server_code"), default=DEFAULT_SERVER_CODE).lower() or DEFAULT_SERVER_CODE
    return {
        "username": _normalize_text(row.get("username")).lower(),
        "server_code": server_code,
        "is_tester": _normalize_bool(row.get("is_tester")),
        "is_gka": _normalize_bool(row.get("is_gka")),
        "is_active": True,
    }


def _build_draft_payload(row: dict[str, Any]) -> dict[str, Any]:
    server_code = _normalize_text(row.get("server_code"), default=DEFAULT_SERVER_CODE).lower() or DEFAULT_SERVER_CODE
    return {
        "username": _normalize_text(row.get("username")).lower(),
        "server_code": server_code,
        "draft_json": _normalize_json_text(row.get("complaint_draft_json"), default={}),
        "updated_at": _normalize_optional_text(row.get("complaint_draft_updated_at")),
    }


def _build_metric_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": _normalize_text(row.get("created_at"), default=_utc_now_iso()),
        "username": _normalize_optional_text(row.get("username")),
        "server_code": _normalize_optional_text(row.get("server_code")),
        "event_type": _normalize_text(row.get("event_type")),
        "path": _normalize_optional_text(row.get("path")),
        "method": _normalize_optional_text(row.get("method")),
        "status_code": row.get("status_code"),
        "duration_ms": row.get("duration_ms"),
        "request_bytes": row.get("request_bytes"),
        "response_bytes": row.get("response_bytes"),
        "resource_units": row.get("resource_units"),
        "meta_json": _normalize_json_text(row.get("meta_json"), default={}),
    }


def _build_exam_answer_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_row": int(row.get("source_row") or 0),
        "submitted_at": _normalize_optional_text(row.get("submitted_at")),
        "full_name": _normalize_optional_text(row.get("full_name")),
        "discord_tag": _normalize_optional_text(row.get("discord_tag")),
        "passport": _normalize_optional_text(row.get("passport")),
        "exam_format": _normalize_optional_text(row.get("exam_format")),
        "payload_json": _normalize_json_text(row.get("payload_json"), default={}),
        "answer_count": int(row.get("answer_count") or 0),
        "imported_at": _normalize_text(row.get("imported_at"), default=_utc_now_iso()),
        "updated_at": _normalize_text(row.get("updated_at"), default=_utc_now_iso()),
        "question_g_score": row.get("question_g_score"),
        "question_g_rationale": _normalize_optional_text(row.get("question_g_rationale")),
        "question_g_scored_at": _normalize_optional_text(row.get("question_g_scored_at")),
        "exam_scores_json": _normalize_optional_text(
            _normalize_json_text(row.get("exam_scores_json"), default=[])
        )
        if row.get("exam_scores_json") not in (None, "")
        else None,
        "exam_scores_scored_at": _normalize_optional_text(row.get("exam_scores_scored_at")),
        "average_score": row.get("average_score"),
        "average_score_answer_count": row.get("average_score_answer_count"),
        "average_score_scored_at": _normalize_optional_text(row.get("average_score_scored_at")),
        "needs_rescore": _normalize_bool(row.get("needs_rescore")),
        "import_key": _normalize_optional_text(row.get("import_key")),
    }


def _build_exam_task_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _normalize_text(row.get("id")),
        "task_type": _normalize_text(row.get("task_type")),
        "source_row": row.get("source_row"),
        "status": _normalize_text(row.get("status")),
        "created_at": _normalize_text(row.get("created_at"), default=_utc_now_iso()),
        "started_at": _normalize_optional_text(row.get("started_at")),
        "finished_at": _normalize_optional_text(row.get("finished_at")),
        "error": _normalize_text(row.get("error")),
        "progress_json": _normalize_json_text(row.get("progress_json"), default={}),
        "result_json": _normalize_json_text(row.get("result_json"), default={}),
    }


def _metric_signature(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (
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


def _answer_signature(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (
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


def _task_signature(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (
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


def migrate_sqlite_to_postgres(
    *,
    source_dir: Path,
    target: MigrationTarget,
    dry_run: bool = False,
) -> dict[str, Any]:
    source_dir = Path(source_dir)
    user_rows = _read_sqlite_rows(source_dir / APP_DB_NAME, "users")
    metric_rows = _read_sqlite_rows(source_dir / ADMIN_METRICS_DB_NAME, "metric_events")
    exam_answer_rows = _read_sqlite_rows(source_dir / EXAM_ANSWERS_DB_NAME, "exam_answers")
    exam_task_rows = _read_sqlite_rows(source_dir / EXAM_IMPORT_TASKS_DB_NAME, "exam_import_tasks")

    servers: dict[str, str] = {DEFAULT_SERVER_CODE: _server_title(DEFAULT_SERVER_CODE)}
    for row in user_rows:
        code = _normalize_text(row.get("server_code"), default=DEFAULT_SERVER_CODE).lower() or DEFAULT_SERVER_CODE
        servers.setdefault(code, _server_title(code))
    for row in metric_rows:
        code = _normalize_text(row.get("server_code")).lower()
        if code:
            servers.setdefault(code, _server_title(code))

    target.ensure_servers(servers, dry_run=dry_run)

    reports = {
        "users": TableReport(source=len(user_rows)),
        "user_server_roles": TableReport(source=len(user_rows)),
        "complaint_drafts": TableReport(source=len(user_rows)),
        "metric_events": TableReport(source=len(metric_rows)),
        "exam_answers": TableReport(source=len(exam_answer_rows)),
        "exam_import_tasks": TableReport(source=len(exam_task_rows)),
    }

    existing_users = target.fetch_existing_users()
    for row in user_rows:
        payload = _build_user_payload(row)
        signature = (
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
        existing = existing_users.get(payload["username"])
        if existing is None:
            reports["users"].inserted += 1
        elif existing == signature:
            reports["users"].skipped += 1
            continue
        else:
            reports["users"].updated += 1
        target.upsert_user(payload, dry_run=dry_run)
        existing_users[payload["username"]] = signature

    existing_roles = target.fetch_existing_roles()
    existing_drafts = target.fetch_existing_drafts()
    for row in user_rows:
        role_payload = _build_role_payload(row)
        role_key = (role_payload["username"], role_payload["server_code"])
        role_signature = (role_payload["is_tester"], role_payload["is_gka"], role_payload["is_active"])
        existing_role = existing_roles.get(role_key)
        if existing_role is None:
            reports["user_server_roles"].inserted += 1
            target.upsert_role(role_payload, dry_run=dry_run)
            existing_roles[role_key] = role_signature
        elif existing_role == role_signature:
            reports["user_server_roles"].skipped += 1
        else:
            reports["user_server_roles"].updated += 1
            target.upsert_role(role_payload, dry_run=dry_run)
            existing_roles[role_key] = role_signature

        draft_payload = _build_draft_payload(row)
        draft_key = (draft_payload["username"], draft_payload["server_code"])
        draft_signature = (draft_payload["draft_json"], draft_payload["updated_at"])
        existing_draft = existing_drafts.get(draft_key)
        if existing_draft is None:
            reports["complaint_drafts"].inserted += 1
            target.upsert_draft(draft_payload, dry_run=dry_run)
            existing_drafts[draft_key] = draft_signature
        elif existing_draft == draft_signature:
            reports["complaint_drafts"].skipped += 1
        else:
            reports["complaint_drafts"].updated += 1
            target.upsert_draft(draft_payload, dry_run=dry_run)
            existing_drafts[draft_key] = draft_signature

    existing_metric_signatures = target.fetch_existing_metric_signatures()
    for row in metric_rows:
        payload = _build_metric_payload(row)
        signature = _metric_signature(payload)
        if signature in existing_metric_signatures:
            reports["metric_events"].skipped += 1
            continue
        reports["metric_events"].inserted += 1
        target.insert_metric_event(payload, dry_run=dry_run)
        existing_metric_signatures.add(signature)

    existing_answers = target.fetch_existing_exam_answers()
    for row in exam_answer_rows:
        payload = _build_exam_answer_payload(row)
        signature = _answer_signature(payload)
        existing = existing_answers.get(payload["source_row"])
        if existing is None:
            reports["exam_answers"].inserted += 1
        elif existing == signature:
            reports["exam_answers"].skipped += 1
            continue
        else:
            reports["exam_answers"].updated += 1
        target.upsert_exam_answer(payload, dry_run=dry_run)
        existing_answers[payload["source_row"]] = signature

    existing_tasks = target.fetch_existing_exam_import_tasks()
    for row in exam_task_rows:
        payload = _build_exam_task_payload(row)
        signature = _task_signature(payload)
        existing = existing_tasks.get(payload["id"])
        if existing is None:
            reports["exam_import_tasks"].inserted += 1
        elif existing == signature:
            reports["exam_import_tasks"].skipped += 1
            continue
        else:
            reports["exam_import_tasks"].updated += 1
        target.upsert_exam_import_task(payload, dry_run=dry_run)
        existing_tasks[payload["id"]] = signature

    return {
        "dry_run": dry_run,
        "source_dir": str(source_dir),
        "servers": servers,
        "tables": {name: report.to_dict() for name, report in reports.items()},
    }
