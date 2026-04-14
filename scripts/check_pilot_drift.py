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
    mismatch_threshold = 0.05
    backend = get_database_backend()
    with closing(backend.connect()) as conn:
        rows = conn.execute(
            """
            SELECT meta_json
            FROM metric_events
            WHERE event_type = 'pilot_runtime_shadow_compare'
            ORDER BY created_at DESC
            LIMIT 200
            """
        ).fetchall()

    total = len(rows)
    mismatched = 0
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
        if int(meta.get("mismatch_count") or 0) > 0:
            mismatched += 1

    mismatch_rate = (mismatched / total) if total else 0.0
    print(
        json.dumps(
            {
                "event_type": "pilot_runtime_shadow_compare",
                "total_events": total,
                "mismatched_events": mismatched,
                "mismatch_rate": round(mismatch_rate, 4),
                "threshold": mismatch_threshold,
                "ok": mismatch_rate <= mismatch_threshold,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if mismatch_rate <= mismatch_threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
