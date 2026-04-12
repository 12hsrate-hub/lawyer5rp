from __future__ import annotations

from ogp_web.db.backends import PostgresBackend
from ogp_web.db.config import load_database_config


_DATABASE_BACKEND = None


def create_database_backend():
    config = load_database_config()
    return PostgresBackend(config.database_url)


def get_database_backend():
    global _DATABASE_BACKEND
    if _DATABASE_BACKEND is None:
        _DATABASE_BACKEND = create_database_backend()
    return _DATABASE_BACKEND
