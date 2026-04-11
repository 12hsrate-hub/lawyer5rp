from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.server_config import get_server_config
from ogp_web.services.law_bundle_service import build_law_bundle, resolve_law_bundle_path, write_law_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Build structured local law bundle for a configured server.")
    parser.add_argument("--server", default="blackberry", help="Server code, for example: blackberry")
    args = parser.parse_args()

    server_config = get_server_config(args.server)
    bundle_path = resolve_law_bundle_path(server_config.code, getattr(server_config, "law_qa_bundle_path", ""))
    bundle = build_law_bundle(server_config.code, server_config.law_qa_sources)
    write_law_bundle(bundle, bundle_path)

    sources = bundle.get("sources", []) if isinstance(bundle, dict) else []
    articles = bundle.get("articles", []) if isinstance(bundle, dict) else []
    print(f"Server: {server_config.code}")
    print(f"Bundle: {bundle_path}")
    print(f"Sources processed: {len(sources)}")
    print(f"Articles stored: {len(articles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
