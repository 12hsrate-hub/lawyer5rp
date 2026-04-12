from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ogp_web.db.factory import get_database_backend
from ogp_web.db.types import DatabaseBackend

MAX_CONCURRENT_TASKS_ENV_VAR = "OGP_EXAM_IMPORT_MAX_CONCURRENT_TASKS"
ALLOW_QUEUED_TASKS_OVER_LIMIT_ENV_VAR = "OGP_EXAM_IMPORT_ALLOW_QUEUED_OVER_LIMIT"


def _parse_positive_int(value: str | None, *, default: int, max_value: int = 1000) -> int:
    try:
        parsed = int((value or "").strip())
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(parsed, max_value)


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "on", "yes", "y", "t"}:
        return True
    if normalized in {"0", "false", "off", "no", "n", "f"}:
        return False
    return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExamTaskRecord:
    id: str
    task_type: str
    source_row: int | None = None
    status: str = "queued"
    created_at: str = field(default_factory=_utc_now)
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    progress: dict[str, Any] | None = None
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.id,
            "task_type": self.task_type,
            "source_row": self.source_row,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "progress": self.progress,
            "result": self.result,
        }


class ExamImportTaskCapacityError(RuntimeError):
    """Raised when exam-import background task concurrency limit is exceeded."""


class ExamImportTaskRegistry:
    INTERRUPTION_ERROR = "Сервис был перезапущен до завершения задачи."
    _ALLOWED_COLUMNS = frozenset({"status", "started_at", "finished_at", "error", "progress_json", "result_json"})

    def __init__(self, db_path: Path, backend: DatabaseBackend | None = None) -> None:
        self.db_path = Path(db_path)
        self.backend = backend or get_database_backend()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.max_concurrent_tasks = _parse_positive_int(
            os.getenv(MAX_CONCURRENT_TASKS_ENV_VAR),
            default=2,
            max_value=20,
        )
        self._allow_over_limit = _parse_bool(
            os.getenv(ALLOW_QUEUED_TASKS_OVER_LIMIT_ENV_VAR),
            default=False,
        )
        self._ensure_schema()
        self._mark_interrupted_tasks()

    def _connect(self):
        return self.backend.connect()

    @property
    def is_postgres_backend(self) -> bool:
        name = self.backend.__class__.__name__
        return name == "PostgresBackend" or name.endswith("PostgresBackend")

    def _placeholder(self) -> str:
        return "%s" if self.is_postgres_backend else "?"

    def _cast_json_value(self, placeholder: str) -> str:
        return f"{placeholder}::jsonb" if self.is_postgres_backend else placeholder

    @staticmethod
    def _decode_json_field(raw: Any) -> dict[str, Any] | None:
        if raw in (None, ""):
            return None
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def healthcheck(self) -> dict[str, object]:
        return self.backend.healthcheck()

    def _ensure_schema(self) -> None:
        if self.is_postgres_backend:
            return
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exam_import_tasks (
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
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(exam_import_tasks)").fetchall()
            }
            if "progress_json" not in columns:
                conn.execute("ALTER TABLE exam_import_tasks ADD COLUMN progress_json TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_exam_import_tasks_created_at ON exam_import_tasks(created_at DESC)"
            )
            conn.commit()

    def _mark_interrupted_tasks(self) -> None:
        placeholder = self._placeholder()
        with closing(self._connect()) as conn:
            conn.execute(
                f"""
                UPDATE exam_import_tasks
                SET status = 'failed',
                    finished_at = {placeholder},
                    error = CASE
                        WHEN COALESCE(error, '') = '' THEN '{self.INTERRUPTION_ERROR}'
                        ELSE error
                    END
                WHERE status IN ('queued', 'running')
                """,
                (_utc_now(),),
            )
            conn.commit()

    def _count_running_tasks(self, conn) -> int:
        placeholder = self._placeholder()
        row = conn.execute(
            f"SELECT COUNT(*) AS active_count FROM exam_import_tasks WHERE status = {placeholder}",
            ("running",),
        ).fetchone()
        if row is None:
            return 0
        return int(row["active_count"] or 0)

    def _raise_if_capacity_exceeded(self, conn) -> None:
        if self._allow_over_limit:
            return
        running_count = self._count_running_tasks(conn)
        if running_count >= self.max_concurrent_tasks:
            raise ExamImportTaskCapacityError(
                "Превышен лимит одновременных фоновых задач проверки экзамена. "
                f"Текущий лимит: {self.max_concurrent_tasks}."
            )

    def create_task(
        self,
        *,
        task_type: str,
        runner: Callable[[Callable[[dict[str, Any]], None]], dict[str, Any]],
        source_row: int | None = None,
    ) -> ExamTaskRecord:
        record = ExamTaskRecord(id=uuid.uuid4().hex, task_type=task_type, source_row=source_row)
        placeholder = self._placeholder()
        empty_json = "{}" if self.is_postgres_backend else ""
        started_at_value = None if self.is_postgres_backend else record.started_at
        finished_at_value = None if self.is_postgres_backend else record.finished_at
        with self._lock, closing(self._connect()) as conn:
            self._raise_if_capacity_exceeded(conn)
            conn.execute(
                f"""
                INSERT INTO exam_import_tasks (
                    id, task_type, source_row, status, created_at, started_at, finished_at, error, progress_json, result_json
                )
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {self._cast_json_value(placeholder)}, {self._cast_json_value(placeholder)})
                """,
                (
                    record.id,
                    record.task_type,
                    record.source_row,
                    record.status,
                    record.created_at,
                    started_at_value,
                    finished_at_value,
                    record.error,
                    empty_json,
                    empty_json,
                ),
            )
            conn.commit()
        try:
            worker = threading.Thread(target=self._run, args=(record.id, runner), daemon=True)
            worker.start()
        except Exception as exc:
            self._update(record.id, status="failed", finished_at=_utc_now(), error=str(exc) or exc.__class__.__name__)
        return record

    def _run(self, task_id: str, runner: Callable[[Callable[[dict[str, Any]], None]], dict[str, Any]]) -> None:
        self._update(task_id, status="running", started_at=_utc_now())
        try:
            progress_callback = lambda progress: self._update(task_id, progress=progress)
            try:
                result = runner(progress_callback)
            except TypeError:
                result = runner()
        except Exception as exc:
            self._update(
                task_id,
                status="failed",
                finished_at=_utc_now(),
                error=str(exc).strip() or exc.__class__.__name__,
            )
            return
        self._update(task_id, status="completed", finished_at=_utc_now(), result=result, error="")

    def get_task(self, task_id: str) -> ExamTaskRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"""
                SELECT id, task_type, source_row, status, created_at, started_at, finished_at, error, progress_json, result_json
                FROM exam_import_tasks
                WHERE id = {self._placeholder()}
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return ExamTaskRecord(
            id=str(row["id"]),
            task_type=str(row["task_type"]),
            source_row=row["source_row"],
            status=str(row["status"]),
            created_at=str(row["created_at"] or ""),
            started_at=str(row["started_at"] or ""),
            finished_at=str(row["finished_at"] or ""),
            error=str(row["error"] or ""),
            progress=self._decode_json_field(row["progress_json"]),
            result=self._decode_json_field(row["result_json"]),
        )

    def _update(self, task_id: str, **changes: Any) -> None:
        assignments: list[str] = []
        values: list[Any] = []
        placeholder = self._placeholder()
        for key, value in changes.items():
            if key == "result":
                column = "result_json"
            elif key == "progress":
                column = "progress_json"
            else:
                column = key
            if column not in self._ALLOWED_COLUMNS:
                raise ValueError(f"Недопустимое поле для обновления задачи: {column!r}")
            if key in {"result", "progress"}:
                assignments.append(f"{column} = {self._cast_json_value(placeholder)}")
                values.append(json.dumps(value or {}, ensure_ascii=False))
            else:
                assignments.append(f"{column} = {placeholder}")
                values.append(value)
        if not assignments:
            return
        values.append(task_id)
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                f"UPDATE exam_import_tasks SET {', '.join(assignments)} WHERE id = {placeholder}",
                values,
            )
            conn.commit()
