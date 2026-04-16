#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from ogp_web.db.factory import get_database_backend
from ogp_web.env import load_web_env


def _pack_path(server_code: str) -> Path:
    return ROOT_DIR / "web" / "ogp_web" / "server_config" / "packs" / f"{server_code}.bootstrap.json"


def _load_pack_payload(server_code: str) -> dict[str, object]:
    path = _pack_path(server_code)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Bootstrap pack must be an object: {path}")
    return payload


def sync_server_pack(*, server_code: str) -> dict[str, object]:
    payload = _load_pack_payload(server_code)
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise TypeError("Bootstrap pack metadata must be an object")

    load_web_env()
    backend = get_database_backend()
    conn = backend.connect()
    try:
        server_row = conn.execute(
            """
            SELECT code
            FROM servers
            WHERE code = %s
            LIMIT 1
            """,
            (server_code,),
        ).fetchone()
        if server_row is None:
            return {
                "server_code": server_code,
                "changed": False,
                "version": 0,
                "reason": "server_missing",
            }

        row = conn.execute(
            """
            SELECT id, version, metadata_json
            FROM server_packs
            WHERE server_code = %s AND status = 'published'
            ORDER BY published_at DESC NULLS LAST, version DESC, id DESC
            LIMIT 1
            """,
            (server_code,),
        ).fetchone()

        normalized_metadata = json.loads(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
        if row is not None:
            current_metadata = dict(row.get("metadata_json") or {})
            normalized_current = json.loads(json.dumps(current_metadata, ensure_ascii=False, sort_keys=True))
            if normalized_current == normalized_metadata:
                return {
                    "server_code": server_code,
                    "changed": False,
                    "version": int(row.get("version") or 0),
                    "reason": "already_synced",
                }
            next_version = int(row.get("version") or 0) + 1
        else:
            next_version = 1

        conn.execute(
            """
            INSERT INTO server_packs (server_code, version, status, metadata_json, published_at)
            VALUES (%s, %s, 'published', %s::jsonb, NOW())
            """,
            (server_code, next_version, json.dumps(metadata, ensure_ascii=False)),
        )
        return {
            "server_code": server_code,
            "changed": True,
            "version": next_version,
            "reason": "published_pack_synced",
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync published server pack from bootstrap JSON")
    parser.add_argument("--server", default="blackberry", help="Server code to sync")
    args = parser.parse_args()
    result = sync_server_pack(server_code=str(args.server or "").strip().lower())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
