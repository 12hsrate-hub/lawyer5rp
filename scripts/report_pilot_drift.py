from __future__ import annotations

import json
import sys
from contextlib import closing
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from ogp_web.db.factory import get_database_backend


def main() -> int:
    backend = get_database_backend()
    with closing(backend.connect()) as conn:
        rows = conn.execute(
            """
            SELECT created_at, username, server_code, path, meta_json
            FROM metric_events
            WHERE event_type = 'pilot_runtime_shadow_compare'
            ORDER BY created_at DESC
            LIMIT 200
            """
        ).fetchall()

    total = len(rows)
    mismatched = 0
    latest: dict[str, object] | None = None
    servers: dict[str, int] = {}
    mismatch_keys: dict[str, int] = {}

    for row in rows:
        raw_meta = row.get("meta_json") if isinstance(row, dict) else None
        if isinstance(raw_meta, str):
            try:
                meta = json.loads(raw_meta)
            except Exception:
                meta = {}
        elif isinstance(raw_meta, dict):
            meta = raw_meta
        else:
            meta = {}
        latest = latest or {
            "created_at": str(row.get("created_at") or ""),
            "username": str(row.get("username") or ""),
            "server_code": str(row.get("server_code") or ""),
            "path": str(row.get("path") or ""),
            "meta": meta,
        }
        server_code = str(row.get("server_code") or "").strip().lower() or "unknown"
        servers[server_code] = servers.get(server_code, 0) + 1
        mismatch_count = int(meta.get("mismatch_count") or 0)
        if mismatch_count > 0:
            mismatched += 1
            for key in (meta.get("mismatches") or {}).keys():
                mismatch_keys[str(key)] = mismatch_keys.get(str(key), 0) + 1

    payload = {
        "event_type": "pilot_runtime_shadow_compare",
        "total_events": total,
        "mismatched_events": mismatched,
        "match_rate": round(((total - mismatched) / total), 4) if total else None,
        "servers": servers,
        "top_mismatch_keys": mismatch_keys,
        "latest_event": latest,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
