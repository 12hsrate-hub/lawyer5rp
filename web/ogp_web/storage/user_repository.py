from __future__ import annotations

from threading import Lock
from threading import local
from typing import Any

from ogp_web.db.types import DatabaseBackend


class UserRepository:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend
        self._local = local()
        self._connections: set[Any] = set()
        self._connections_lock = Lock()

    def _register_connection(self, conn: Any) -> None:
        with self._connections_lock:
            self._connections.add(conn)

    def _unregister_connection(self, conn: Any) -> None:
        with self._connections_lock:
            self._connections.discard(conn)

    def connect(self):
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            try:
                conn.execute("SELECT 1").fetchone()
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                self._unregister_connection(conn)
                self._local.connection = None

        conn = self.backend.connect()
        self._register_connection(conn)
        self._local.connection = conn
        return conn

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()):
        try:
            return self.connect().execute(query, params).fetchone()
        except Exception as exc:
            raise self.backend.map_exception(exc) from exc

    def execute(self, query: str, params: tuple[Any, ...] = (), *, commit: bool = True) -> int:
        try:
            conn = self.connect()
            cursor = conn.execute(query, params)
            if commit:
                conn.commit()
            return int(cursor.rowcount)
        except Exception as exc:
            raise self.backend.map_exception(exc) from exc

    def close(self) -> None:
        with self._connections_lock:
            connections = list(self._connections)
            self._connections.clear()

        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass

        self._local.connection = None
