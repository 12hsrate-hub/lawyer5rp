#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.db.factory import get_database_backend
from ogp_web.env import load_web_env
from ogp_web.services.synthetic_runner_service import SyntheticRunnerService
from ogp_web.storage.admin_metrics_store import AdminMetricsStore


def main() -> int:
    load_web_env()
    parser = argparse.ArgumentParser(description="Run synthetic suite and persist results in admin metrics.")
    parser.add_argument("--suite", required=True, choices=["smoke", "nightly", "load", "fault"])
    parser.add_argument("--server", default=os.getenv("OGP_DEFAULT_SERVER_CODE", "blackberry"))
    parser.add_argument("--trigger", default="manual")
    args = parser.parse_args()

    backend = get_database_backend()
    store = AdminMetricsStore(ROOT_DIR / "web" / "data" / "admin_metrics.db", backend=backend)
    service = SyntheticRunnerService(store)
    payload = service.run_suite(suite=args.suite, server_code=args.server, trigger=args.trigger)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
