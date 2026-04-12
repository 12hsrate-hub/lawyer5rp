from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.admin_metrics_store import AdminMetricsStore


DEFAULT_WINDOWS = (15, 60, 1440)


def _parse_windows(raw: str) -> tuple[int, ...]:
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        minutes = int(part)
        if minutes > 0:
            values.append(minutes)
    return tuple(sorted(set(values), reverse=False)) if values else DEFAULT_WINDOWS


def _print_summary(report: dict[str, object]) -> None:
    windows = report["windows"]
    if not isinstance(windows, dict):
        return
    print("Performance baseline report")
    print(f"generated_at: {report.get('generated_at')}")
    for window_minutes, payload in sorted(windows.items(), key=lambda item: int(item[0])):
        total_requests = int(payload.get("total_api_requests", 0))
        error_rate = float(payload.get("error_rate", 0))
        throughput = float(payload.get("throughput_rps", 0))
        p50 = payload.get("p50_ms")
        p95 = payload.get("p95_ms")
        print(
            f"window={window_minutes}m requests={total_requests} "
            f"errors={payload.get('error_count', 0)} error_rate={error_rate:.4f} "
            f"rps={throughput:.2f} p50={p50}ms p95={p95}ms"
        )


def main() -> int:
    if not os.getenv("DATABASE_URL", "").strip():
        raise SystemExit("DATABASE_URL is required for perf_baseline.py.")

    parser = argparse.ArgumentParser(description="Collect performance baseline from admin metrics store.")
    parser.add_argument(
        "--window-minutes",
        default="15,60,1440",
        help="Comma separated windows in minutes (default: 15,60,1440).",
    )
    parser.add_argument(
        "--top-endpoints",
        type=int,
        default=10,
        help="Top endpoints to include in per-path snapshot (default: 10).",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output path for JSON snapshot.",
    )

    args = parser.parse_args()

    store = AdminMetricsStore(ROOT_DIR / "web" / "data" / "admin_metrics.db")
    windows = _parse_windows(args.window_minutes)
    windows_payload: dict[str, dict[str, object]] = {}

    for window in windows:
        payload = store.get_performance_overview(
            window_minutes=window,
            top_endpoints=args.top_endpoints,
        )
        windows_payload[str(window)] = payload

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database_backend": payload["backend"],
        "windows": windows_payload,
        "meta": {
            "top_endpoints": args.top_endpoints,
            "windows_requested": list(windows),
        },
    }

    _print_summary(report)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"snapshot saved: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
