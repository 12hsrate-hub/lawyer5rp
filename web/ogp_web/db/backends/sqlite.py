from __future__ import annotations

import sqlite3
from pathlib import Path

from ogp_web.db.errors import DatabaseUnavailableError, IntegrityConflictError


class SQLiteBackend:
    def __init__(self, db_path: Path, *, busy_timeout_ms: int = 5000):
        self.db_path = Path(db_path)
        self.busy_timeout_ms = max(0, int(busy_timeout_ms))

    def connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            if self.busy_timeout_ms:
                conn.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
            return conn
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError(str(exc)) from exc

    def healthcheck(self) -> dict[str, object]:
        details: dict[str, object] = {"backend": "sqlite", "path": str(self.db_path), "ok": False}
        if not self.db_path.exists():
            details["error"] = "missing"
            return details
        try:
            conn = self.connect()
            try:
                conn.execute("SELECT 1").fetchone()
            finally:
                conn.close()
        except Exception as exc:
            details["error"] = str(exc)
            return details
        details["ok"] = True
        return details

    def map_exception(self, exc: Exception) -> Exception:
        if isinstance(exc, sqlite3.IntegrityError):
            return IntegrityConflictError(str(exc))
        if isinstance(exc, sqlite3.Error):
            return DatabaseUnavailableError(str(exc))
        return exc
