from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ogp_web.db.config import load_database_config
from ogp_web.db.errors import DatabaseSchemaError, UnsupportedDatabaseBackendError
from ogp_web.db.factory import create_database_backend


MIGRATIONS_DIR = Path(__file__).resolve().parent / "versions"


@dataclass(frozen=True)
class MigrationRecord:
    version: str
    path: Path


def _migration_table_sql(backend: str) -> str:
    if backend == "postgres":
        return """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    raise UnsupportedDatabaseBackendError(f"Unsupported migration backend: {backend!r}")


def _list_version_files(backend: str) -> list[MigrationRecord]:
    backend_dir = MIGRATIONS_DIR / backend
    if not backend_dir.exists():
        return []
    return [
        MigrationRecord(version=path.stem, path=path)
        for path in sorted(backend_dir.glob("*.sql"))
    ]


def list_migrations(backend: str | None = None) -> list[MigrationRecord]:
    resolved_backend = backend or load_database_config().backend
    return _list_version_files(resolved_backend)


def _normalize_row_value(row: Any, key: str, index: int = 0) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except Exception:
        pass
    try:
        return row[index]
    except Exception:
        return None


def run_migrations(*, backend: str | None = None, dry_run: bool = False) -> list[str]:
    config = load_database_config()
    resolved_backend = backend or config.backend
    if resolved_backend != config.backend:
        raise UnsupportedDatabaseBackendError(
            f"Configured backend is {config.backend!r}, but migration runner was asked for {resolved_backend!r}."
        )
    if resolved_backend != "postgres":
        raise UnsupportedDatabaseBackendError(
            "Migration runner currently supports PostgreSQL migrations only."
        )

    migrations = _list_version_files(resolved_backend)
    if not migrations:
        return []

    backend_instance = create_database_backend()
    conn = backend_instance.connect()
    try:
        conn.execute(_migration_table_sql(resolved_backend))
        conn.commit()

        applied_rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC").fetchall()
        applied_versions = {
            str(version)
            for version in (
                _normalize_row_value(row, "version")
                for row in applied_rows
            )
            if version
        }

        pending = [migration for migration in migrations if migration.version not in applied_versions]
        if dry_run:
            return [migration.version for migration in pending]

        for migration in pending:
            sql = migration.path.read_text(encoding="utf-8").strip()
            if not sql:
                raise DatabaseSchemaError(f"Migration {migration.version!r} is empty.")
            try:
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (migration.version,),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return [migration.version for migration in pending]
    finally:
        conn.close()
