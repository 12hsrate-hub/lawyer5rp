from __future__ import annotations

from ogp_web.db.types import DatabaseBackend


class LawVersionsRepository:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    def rollback_active_version(self, *, server_code: str, target_version_id: int) -> None:
        conn = self.backend.connect()
        try:
            conn.execute(
                """
                UPDATE law_versions
                SET effective_to = NOW()
                WHERE server_code = %s AND id <> %s AND effective_to IS NULL
                """,
                (server_code, int(target_version_id)),
            )
            conn.execute(
                """
                UPDATE law_versions
                SET effective_from = NOW(), effective_to = NULL
                WHERE id = %s AND server_code = %s
                """,
                (int(target_version_id), server_code),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
