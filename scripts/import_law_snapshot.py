from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.law_bundle_service import resolve_law_bundle_path
from ogp_web.services.law_version_service import import_law_snapshot


def _parse_optional_datetime(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import law bundle JSON as a versioned DB snapshot.")
    parser.add_argument("--server", default="blackberry", help="Server code, e.g. blackberry")
    parser.add_argument("--snapshot", default="", help="Path to snapshot JSON (defaults to law_bundles/<server>.json)")
    parser.add_argument("--effective-from", default="", help="ISO datetime for effective_from")
    parser.add_argument("--effective-to", default="", help="ISO datetime for effective_to")
    args = parser.parse_args()

    snapshot_path = (
        Path(args.snapshot).expanduser().resolve()
        if str(args.snapshot or "").strip()
        else resolve_law_bundle_path(args.server)
    )
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    version_id = import_law_snapshot(
        server_code=args.server,
        payload=payload if isinstance(payload, dict) else {},
        source_ref=str(snapshot_path),
        effective_from=_parse_optional_datetime(args.effective_from),
        effective_to=_parse_optional_datetime(args.effective_to),
    )
    print(f"Imported law snapshot version_id={version_id} server={args.server} snapshot={snapshot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
