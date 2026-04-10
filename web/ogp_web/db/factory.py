from __future__ import annotations

from ogp_web.db.backends import PostgresBackend, SQLiteBackend
from ogp_web.db.config import load_database_config
from ogp_web.db.errors import UnsupportedDatabaseBackendError


_DATABASE_BACKEND = None


def create_database_backend():
    config = load_database_config()
    if config.backend == "sqlite":
        if config.sqlite_path is None:
            raise UnsupportedDatabaseBackendError("SQLite backend requires a sqlite path.")
        return SQLiteBackend(config.sqlite_path)
    if config.backend == "postgres":
        return PostgresBackend(config.database_url)
    raise UnsupportedDatabaseBackendError(f"Unsupported database backend: {config.backend!r}")


def get_database_backend():
    global _DATABASE_BACKEND
    if _DATABASE_BACKEND is None:
        _DATABASE_BACKEND = create_database_backend()
    return _DATABASE_BACKEND
