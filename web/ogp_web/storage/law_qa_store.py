from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from ogp_web.db.factory import get_database_backend
from ogp_web.db.types import DatabaseBackend

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "web" / "data"
DB_PATH = DATA_DIR / "law_qa.db"


class LawQaStore:
    def __init__(self, db_path: Path, backend: DatabaseBackend | None = None):
        self.db_path = db_path
        self.backend = backend or get_database_backend()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self):
        return self.backend.connect()

    @property
    def is_postgres_backend(self) -> bool:
        name = self.backend.__class__.__name__
        return name == "PostgresBackend" or name.endswith("PostgresBackend")

    def _placeholder(self) -> str:
        return "%s" if self.is_postgres_backend else "?"

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            if self.is_postgres_backend:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS law_qa_documents (
                        id BIGSERIAL PRIMARY KEY,
                        server_code TEXT NOT NULL,
                        title TEXT NOT NULL,
                        source_url TEXT NOT NULL,
                        content TEXT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE (server_code, source_url)
                    )
                    """
                )
            else:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS law_qa_documents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_code TEXT NOT NULL,
                        title TEXT NOT NULL,
                        source_url TEXT NOT NULL,
                        content TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (server_code, source_url)
                    )
                    """
                )
                columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(law_qa_documents)").fetchall()}
                if "title" not in columns:
                    try:
                        conn.execute("ALTER TABLE law_qa_documents ADD COLUMN title TEXT NOT NULL DEFAULT ''")
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).lower():
                            raise
            conn.execute("CREATE INDEX IF NOT EXISTS idx_law_qa_documents_server ON law_qa_documents(server_code)")
            conn.commit()

    def count_documents(self, server_code: str) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS total FROM law_qa_documents WHERE server_code = {self._placeholder()}",
                (server_code,),
            ).fetchone()
            return int(row["total"] or 0) if row else 0

    def replace_server_documents(self, server_code: str, documents: list[dict[str, str]]) -> int:
        normalized_server = str(server_code or "").strip().lower()
        with closing(self._connect()) as conn:
            conn.execute(
                f"DELETE FROM law_qa_documents WHERE server_code = {self._placeholder()}",
                (normalized_server,),
            )
            if documents:
                placeholder = self._placeholder()
                now_sql = "NOW()" if self.is_postgres_backend else "CURRENT_TIMESTAMP"
                conn.executemany(
                    f"""
                    INSERT INTO law_qa_documents (server_code, title, source_url, content, updated_at)
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {now_sql})
                    """,
                    [
                        (
                            normalized_server,
                            str(item.get("title") or "").strip(),
                            str(item.get("source_url") or "").strip(),
                            str(item.get("content") or "").strip(),
                        )
                        for item in documents
                        if str(item.get("content") or "").strip() and str(item.get("source_url") or "").strip()
                    ],
                )
            conn.commit()
            return self.count_documents(normalized_server)

    def list_documents(self, server_code: str) -> list[dict[str, str]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"""
                SELECT title, source_url, content
                FROM law_qa_documents
                WHERE server_code = {self._placeholder()}
                ORDER BY id ASC
                """,
                (str(server_code or "").strip().lower(),),
            ).fetchall()
        return [
            {
                "title": str(row["title"] or "").strip(),
                "url": str(row["source_url"] or "").strip(),
                "text": str(row["content"] or "").strip(),
            }
            for row in rows
            if str(row["content"] or "").strip()
        ]


_default_law_qa_store: LawQaStore | None = None


def get_default_law_qa_store() -> LawQaStore:
    global _default_law_qa_store
    if _default_law_qa_store is None:
        _default_law_qa_store = LawQaStore(DB_PATH)
    return _default_law_qa_store
