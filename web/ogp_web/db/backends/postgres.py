from __future__ import annotations

from ogp_web.db.errors import DatabaseUnavailableError, IntegrityConflictError


class PostgresBackend:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _import_psycopg(self):
        try:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore
        except Exception as exc:
            raise DatabaseUnavailableError(
                "PostgreSQL backend requires psycopg to be installed."
            ) from exc
        return psycopg, dict_row

    def connect(self):
        psycopg, dict_row = self._import_psycopg()
        try:
            return psycopg.connect(self.database_url, row_factory=dict_row)
        except Exception as exc:
            raise DatabaseUnavailableError(str(exc)) from exc

    def healthcheck(self) -> dict[str, object]:
        details: dict[str, object] = {"backend": "postgres", "ok": False}
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
        name = exc.__class__.__name__
        if name in {"UniqueViolation", "ForeignKeyViolation", "NotNullViolation"}:
            return IntegrityConflictError(str(exc))
        return DatabaseUnavailableError(str(exc))
