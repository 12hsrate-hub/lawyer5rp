from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ogp_web.db.factory import get_database_backend
@dataclass(frozen=True)
class ResolvedLawVersion:
    id: int
    server_code: str
    generated_at_utc: str
    effective_from: str
    effective_to: str
    fingerprint: str
    chunk_count: int


def list_recent_law_versions(*, server_code: str, limit: int = 10) -> tuple[ResolvedLawVersion, ...]:
    backend = get_database_backend()
    safe_limit = max(1, min(int(limit or 10), 100))
    with backend.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, server_code, generated_at_utc, effective_from, effective_to, fingerprint, chunk_count
            FROM law_versions
            WHERE server_code = %s
            ORDER BY effective_from DESC, id DESC
            LIMIT %s
            """,
            (server_code, safe_limit),
        ).fetchall()
    return tuple(
        ResolvedLawVersion(
            id=int(row["id"]),
            server_code=str(row.get("server_code") or server_code),
            generated_at_utc=_to_iso(row.get("generated_at_utc")),
            effective_from=_to_iso(row.get("effective_from")),
            effective_to=_to_iso(row.get("effective_to")),
            fingerprint=str(row.get("fingerprint") or "").strip(),
            chunk_count=int(row.get("chunk_count") or 0),
        )
        for row in rows
    )


def resolve_active_law_version(
    *,
    server_code: str,
    effective_at: datetime | None = None,
    requested_version_id: int | None = None,
) -> ResolvedLawVersion | None:
    backend = get_database_backend()
    effective_dt = effective_at or datetime.now(timezone.utc)
    with backend.connect() as conn:
        if requested_version_id:
            row = conn.execute(
                """
                SELECT id, server_code, generated_at_utc, effective_from, effective_to, fingerprint, chunk_count
                FROM law_versions
                WHERE server_code = %s AND id = %s
                LIMIT 1
                """,
                (server_code, int(requested_version_id)),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, server_code, generated_at_utc, effective_from, effective_to, fingerprint, chunk_count
                FROM law_versions
                WHERE server_code = %s
                  AND effective_from <= %s
                  AND (effective_to IS NULL OR effective_to > %s)
                ORDER BY effective_from DESC, id DESC
                LIMIT 1
                """,
                (server_code, effective_dt, effective_dt),
            ).fetchone()
    if not row:
        return None
    return ResolvedLawVersion(
        id=int(row["id"]),
        server_code=str(row.get("server_code") or server_code),
        generated_at_utc=_to_iso(row.get("generated_at_utc")),
        effective_from=_to_iso(row.get("effective_from")),
        effective_to=_to_iso(row.get("effective_to")),
        fingerprint=str(row.get("fingerprint") or "").strip(),
        chunk_count=int(row.get("chunk_count") or 0),
    )


def load_law_chunks_by_version(server_code: str, law_version_id: int) -> tuple[LawChunk, ...]:
    from ogp_web.services.law_bundle_service import LawChunk

    backend = get_database_backend()
    with backend.connect() as conn:
        rows = conn.execute(
            """
            SELECT a.article_label, a.text, d.source_url, d.document_title
            FROM law_articles AS a
            JOIN law_versions AS v ON v.id = a.law_version_id
            JOIN law_documents AS d ON d.id = a.law_document_id
            WHERE v.server_code = %s AND a.law_version_id = %s
            ORDER BY a.position ASC, a.id ASC
            """,
            (server_code, int(law_version_id)),
        ).fetchall()
    return tuple(
        LawChunk(
            url=str(row.get("source_url") or "").strip(),
            document_title=str(row.get("document_title") or "").strip(),
            article_label=str(row.get("article_label") or "").strip(),
            text=str(row.get("text") or "").strip(),
        )
        for row in rows
        if str(row.get("source_url") or "").strip()
        and str(row.get("document_title") or "").strip()
        and str(row.get("article_label") or "").strip()
        and str(row.get("text") or "").strip()
    )


def import_law_snapshot(
    *,
    server_code: str,
    payload: dict[str, Any],
    source_ref: str,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
) -> int:
    backend = get_database_backend()
    effective_from_dt = effective_from or datetime.now(timezone.utc)
    generated_at = _parse_iso_datetime(payload.get("generated_at_utc")) or effective_from_dt
    sources = payload.get("sources", []) if isinstance(payload, dict) else []
    articles = payload.get("articles", []) if isinstance(payload, dict) else []
    fingerprint = _build_snapshot_fingerprint(server_code=server_code, payload=payload)

    with backend.connect() as conn:
        row = conn.execute(
            """
            INSERT INTO law_versions (
                server_code, source_type, source_ref, generated_at_utc,
                effective_from, effective_to, fingerprint, chunk_count, meta_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                server_code,
                "snapshot_import",
                source_ref,
                generated_at,
                effective_from_dt,
                effective_to,
                fingerprint,
                len(articles) if isinstance(articles, list) else 0,
                json.dumps({"source_count": len(sources) if isinstance(sources, list) else 0}, ensure_ascii=False),
            ),
        ).fetchone()
        law_version_id = int(row["id"])

        document_ids: dict[tuple[str, str], int] = {}
        for item in articles if isinstance(articles, list) else []:
            if not isinstance(item, dict):
                continue
            source_url = str(item.get("url") or "").strip()
            document_title = str(item.get("document_title") or "").strip()
            if not source_url or not document_title:
                continue
            key = (source_url, document_title)
            if key in document_ids:
                continue
            doc_row = conn.execute(
                """
                INSERT INTO law_documents (server_code, source_url, document_title)
                VALUES (%s, %s, %s)
                ON CONFLICT (server_code, source_url, document_title)
                DO UPDATE SET document_title = EXCLUDED.document_title
                RETURNING id
                """,
                (server_code, source_url, document_title),
            ).fetchone()
            document_ids[key] = int(doc_row["id"])

        for index, item in enumerate(articles if isinstance(articles, list) else []):
            if not isinstance(item, dict):
                continue
            source_url = str(item.get("url") or "").strip()
            document_title = str(item.get("document_title") or "").strip()
            article_label = str(item.get("article_label") or "").strip()
            text = str(item.get("text") or "").strip()
            if not source_url or not document_title or not article_label or not text:
                continue
            doc_id = document_ids.get((source_url, document_title))
            if not doc_id:
                continue
            conn.execute(
                """
                INSERT INTO law_articles (law_version_id, law_document_id, article_label, text, position)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (law_version_id, doc_id, article_label, text, index),
            )
        conn.commit()
    return law_version_id


def build_law_snapshot_fingerprint(*, server_code: str, payload: dict[str, Any]) -> str:
    return _build_snapshot_fingerprint(server_code=server_code, payload=payload)


def _build_snapshot_fingerprint(*, server_code: str, payload: dict[str, Any]) -> str:
    digest_payload = json.dumps(
        {
            "server_code": server_code,
            "generated_at_utc": payload.get("generated_at_utc"),
            "sources": payload.get("sources", []),
            "articles_count": len(payload.get("articles", []) if isinstance(payload, dict) else []),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()[:24]


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value or "").strip()


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
