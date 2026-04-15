from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from ogp_web.services.generation_snapshot_schema_service import extract_generation_persistence_blocks
from ogp_web.storage.user_store import UserStore


@dataclass(frozen=True)
class BridgeWriteResult:
    case_id: int
    case_document_id: int
    document_version_id: int
    generation_snapshot_id: int
    generated_document_id: int


class GenerationOrchestrator:
    SYNTHETIC_GENERATED_DOCUMENT_ID_OFFSET = 1_000_000_000_000

    def __init__(self, store: UserStore):
        self.store = store
        self.backend = store.backend

    @staticmethod
    def bridge_mode() -> str:
        mode = str(os.getenv("OGP_GENERATION_BRIDGE_MODE", "shadow_write") or "").strip().lower()
        if mode not in {"off", "shadow_write", "strict"}:
            return "shadow_write"
        return mode

    def _connect(self):
        return self.backend.connect()

    def _fetchone(self, conn, query: str, params: tuple[Any, ...]):
        return conn.execute(query, params).fetchone()

    def _resolve_user_id(self, conn, *, username: str) -> int:
        row = self._fetchone(conn, "SELECT id FROM users WHERE username = %s", (username,))
        if row is None:
            raise RuntimeError("Пользователь не найден для bridge write.")
        return int(row["id"])

    def _ensure_case_document(
        self,
        conn,
        *,
        user_id: int,
        server_code: str,
        document_kind: str,
    ) -> tuple[int, int]:
        existing = self._fetchone(
            conn,
            """
            SELECT cd.id AS document_id, cd.case_id AS case_id
            FROM case_documents cd
            JOIN cases c ON c.id = cd.case_id
            WHERE c.owner_user_id = %s
              AND c.server_id = %s
              AND c.case_type = %s
              AND cd.document_type = %s
            ORDER BY cd.id DESC
            LIMIT 1
            """,
            (user_id, server_code, f"generated_{document_kind}", document_kind),
        )
        if existing is not None:
            return int(existing["case_id"]), int(existing["document_id"])

        created_case = self._fetchone(
            conn,
            """
            INSERT INTO cases (server_id, owner_user_id, title, case_type, status, metadata_json)
            VALUES (%s, %s, %s, %s, 'draft', '{}'::jsonb)
            RETURNING id
            """,
            (
                server_code,
                user_id,
                f"Generated {document_kind} documents",
                f"generated_{document_kind}",
            ),
        )
        case_id = int(created_case["id"])
        created_document = self._fetchone(
            conn,
            """
            INSERT INTO case_documents (case_id, server_id, document_type, status, created_by, metadata_json)
            VALUES (%s, %s, %s, 'draft', %s, '{}'::jsonb)
            RETURNING id
            """,
            (case_id, server_code, document_kind, user_id),
        )
        return case_id, int(created_document["id"])

    def _create_generation_snapshot(
        self,
        conn,
        *,
        user_id: int,
        server_code: str,
        document_kind: str,
        payload: dict[str, Any],
        result_text: str,
        context_snapshot: dict[str, Any],
        legacy_generated_document_id: int | None,
    ) -> tuple[int, int]:
        effective_config_snapshot, content_workflow_ref = extract_generation_persistence_blocks(context_snapshot or {})
        row = self._fetchone(
            conn,
            """
            INSERT INTO generation_snapshots (
                server_id,
                user_id,
                document_kind,
                payload_json,
                result_text,
                context_snapshot_json,
                effective_config_snapshot_json,
                content_workflow_ref_json,
                legacy_generated_document_id
            )
            VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            RETURNING id
            """,
            (
                server_code,
                user_id,
                document_kind,
                json.dumps(payload or {}, ensure_ascii=False),
                result_text,
                json.dumps(context_snapshot or {}, ensure_ascii=False),
                json.dumps(effective_config_snapshot, ensure_ascii=False),
                json.dumps(content_workflow_ref, ensure_ascii=False),
                legacy_generated_document_id,
            ),
        )
        snapshot_id = int(row["id"])
        resolved_generated_document_id = int(legacy_generated_document_id or 0)
        if resolved_generated_document_id <= 0:
            resolved_generated_document_id = self.SYNTHETIC_GENERATED_DOCUMENT_ID_OFFSET + snapshot_id
            conn.execute(
                """
                UPDATE generation_snapshots
                SET legacy_generated_document_id = %s
                WHERE id = %s
                """,
                (resolved_generated_document_id, snapshot_id),
            )
        return snapshot_id, resolved_generated_document_id

    def write_generation_bridge(
        self,
        *,
        username: str,
        server_code: str,
        document_kind: str,
        payload: dict[str, Any],
        result_text: str,
        context_snapshot: dict[str, Any],
        legacy_generated_document_id: int | None,
    ) -> BridgeWriteResult:
        conn = self._connect()
        try:
            user_id = self._resolve_user_id(conn, username=username)
            case_id, case_document_id = self._ensure_case_document(
                conn,
                user_id=user_id,
                server_code=server_code,
                document_kind=document_kind,
            )
            snapshot_id, generated_document_id = self._create_generation_snapshot(
                conn,
                user_id=user_id,
                server_code=server_code,
                document_kind=document_kind,
                payload=payload,
                result_text=result_text,
                context_snapshot=context_snapshot,
                legacy_generated_document_id=legacy_generated_document_id,
            )
            version_row = self._fetchone(
                conn,
                """
                INSERT INTO document_versions (
                    document_id,
                    version_number,
                    content_json,
                    created_by,
                    generation_snapshot_id
                )
                SELECT
                    %s,
                    COALESCE(MAX(version_number), 0) + 1,
                    %s::jsonb,
                    %s,
                    %s
                FROM document_versions
                WHERE document_id = %s
                RETURNING id, version_number
                """,
                (
                    case_document_id,
                    json.dumps(
                        {
                            "bbcode": result_text,
                            "payload": payload or {},
                            "legacy_generated_document_id": generated_document_id,
                        },
                        ensure_ascii=False,
                    ),
                    user_id,
                    snapshot_id,
                    case_document_id,
                ),
            )
            conn.execute(
                """
                UPDATE case_documents
                SET latest_version_id = %s,
                    updated_at = NOW(),
                    metadata_json = jsonb_set(
                        jsonb_set(
                            COALESCE(metadata_json, '{}'::jsonb),
                            '{bridge}',
                            COALESCE(metadata_json->'bridge', '{}'::jsonb),
                            true
                        ),
                        '{bridge,legacy_generated_document_id}',
                        to_jsonb(%s::bigint),
                        true
                    )
                WHERE id = %s
                """,
                (int(version_row["id"]), generated_document_id, case_document_id),
            )
            conn.commit()
            return BridgeWriteResult(
                case_id=case_id,
                case_document_id=case_document_id,
                document_version_id=int(version_row["id"]),
                generation_snapshot_id=snapshot_id,
                generated_document_id=generated_document_id,
            )
        except Exception:
            conn.rollback()
            raise

    def list_history(self, *, username: str, limit: int) -> list[dict[str, Any]]:
        safe_limit = max(1, min(200, int(limit or 30)))
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT
                gs.legacy_generated_document_id AS id,
                gs.server_id AS server_code,
                gs.document_kind AS document_kind,
                gs.created_at AS created_at
            FROM generation_snapshots gs
            JOIN users u ON u.id = gs.user_id
            WHERE u.username = %s
            ORDER BY gs.created_at DESC, gs.id DESC
            LIMIT %s
            """,
            (username, safe_limit),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            if int(row.get("id") or 0) <= 0:
                continue
            payload = dict(row)
            payload["created_at"] = str(payload.get("created_at") or "")
            items.append(payload)
        return items

    def get_snapshot_by_legacy_id(self, *, username: str, legacy_generated_document_id: int) -> dict[str, Any] | None:
        normalized_id = int(legacy_generated_document_id or 0)
        if normalized_id <= 0:
            return None
        conn = self._connect()
        row = conn.execute(
            """
            SELECT
                gs.id AS generation_snapshot_id,
                gs.legacy_generated_document_id AS id,
                gs.server_id AS server_code,
                gs.document_kind AS document_kind,
                gs.created_at AS created_at,
                CAST(gs.context_snapshot_json AS TEXT) AS context_snapshot_json
            FROM generation_snapshots gs
            JOIN users u ON u.id = gs.user_id
            WHERE u.username = %s
              AND gs.legacy_generated_document_id = %s
            ORDER BY gs.id DESC
            LIMIT 1
            """,
            (username, normalized_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "generation_snapshot_id": int(row["generation_snapshot_id"]),
            "server_code": str(row["server_code"] or ""),
            "document_kind": str(row["document_kind"] or ""),
            "created_at": str(row["created_at"] or ""),
            "context_snapshot": json.loads(str(row["context_snapshot_json"] or "{}")),
        }
