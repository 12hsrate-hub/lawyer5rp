from __future__ import annotations

import json
from typing import Any

from ogp_web.db.types import DatabaseBackend


class CaseRepository:
    def __init__(self, backend: DatabaseBackend):
        self.backend = backend

    def _connect(self):
        return self.backend.connect()

    def _fetchone(self, query: str, params: tuple[Any, ...]):
        try:
            return self._connect().execute(query, params).fetchone()
        except Exception as exc:  # noqa: BLE001
            raise self.backend.map_exception(exc) from exc

    def _execute(self, query: str, params: tuple[Any, ...], *, commit: bool = True):
        conn = self._connect()
        try:
            cursor = conn.execute(query, params)
            if commit:
                conn.commit()
            return cursor
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise self.backend.map_exception(exc) from exc

    def get_user_id_by_username(self, username: str) -> int | None:
        row = self._fetchone("SELECT id FROM users WHERE username = %s", (username,))
        return int(row["id"]) if row else None

    def create_case(self, *, server_id: str, owner_user_id: int, title: str, case_type: str):
        cursor = self._execute(
            """
            INSERT INTO cases (server_id, owner_user_id, title, case_type, status, metadata_json)
            VALUES (%s, %s, %s, %s, 'draft', '{}'::jsonb)
            RETURNING id, server_id, owner_user_id, title, case_type, status, CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at
            """,
            (server_id, owner_user_id, title, case_type),
        )
        return cursor.fetchone()

    def get_case(self, *, case_id: int):
        return self._fetchone(
            """
            SELECT id, server_id, owner_user_id, title, case_type, status, CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at
            FROM cases
            WHERE id = %s
            LIMIT 1
            """,
            (case_id,),
        )

    def create_case_event(
        self,
        *,
        case_id: int,
        server_id: str,
        event_type: str,
        actor_user_id: int,
        payload: dict[str, Any],
    ) -> None:
        self._execute(
            """
            INSERT INTO case_events (case_id, server_id, event_type, actor_user_id, payload_json)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (case_id, server_id, event_type, actor_user_id, json.dumps(payload, ensure_ascii=False)),
        )
