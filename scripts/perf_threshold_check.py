from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(ROOT_DIR / "web") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "web"))
os.environ.setdefault("OGP_DB_BACKEND", "sqlite")
from ogp_web.storage.admin_metrics_store import AdminMetricsStore


@dataclass(frozen=True)
class PerfWindow:
    window_minutes: int
    p50_ms: float | None
    p95_ms: float | None
    error_rate: float
    throughput_rps: float
    total_api_requests: int


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def load_windows(snapshot: dict[str, Any]) -> dict[int, PerfWindow]:
    windows: dict[int, PerfWindow] = {}
    for window_key, payload in (snapshot.get("windows") or {}).items():
        try:
            window_minutes = int(window_key)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        windows[window_minutes] = PerfWindow(
            window_minutes=window_minutes,
            p50_ms=_coerce_float(payload.get("p50_ms")),
            p95_ms=_coerce_float(payload.get("p95_ms")),
            error_rate=_coerce_float(payload.get("error_rate")) or 0.0,
            throughput_rps=_coerce_float(payload.get("throughput_rps")) or 0.0,
            total_api_requests=_coerce_int(payload.get("total_api_requests")),
        )
    return windows


def run_local_snapshot(top_endpoints: int = 10, windows: tuple[int, ...] = (15, 60, 1440), db_path: Path | None = None) -> dict[str, Any]:
    if db_path is None:
        db_path = ROOT_DIR / "web" / "data" / "admin_metrics.db"
    store = AdminMetricsStore(db_path, backend=None)
    windows_payload: dict[str, dict[str, Any]] = {}
    for window_minutes in windows:
        windows_payload[str(window_minutes)] = store.get_performance_overview(
            window_minutes=window_minutes,
            top_endpoints=top_endpoints,
        )
    return {
        "generated_at": None,
        "database_backend": windows_payload[str(windows[0])]["backend"] if windows else "unknown",
        "windows": windows_payload,
        "meta": {"top_endpoints": top_endpoints, "windows_requested": list(windows)},
    }


def _build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    if args.input and args.input != "-":
        snapshot_path = Path(args.input)
        return json.loads(snapshot_path.read_text(encoding="utf-8"))
    local_snapshot = run_local_snapshot(
        top_endpoints=args.top_endpoints,
        windows=tuple(args.windows),
    )
    if args.output:
        Path(args.output).write_text(
            json.dumps(local_snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return local_snapshot


def _parse_windows(raw: str) -> tuple[int, ...]:
    values = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            minutes = int(item)
        except ValueError:
            continue
        if minutes > 0:
            values.append(minutes)
    if not values:
        return (15, 60, 1440)
    return tuple(sorted(set(values)))


def _build_status(
    *,
    current_value: float,
    baseline_value: float | None,
    ratio_limit: float,
    label: str,
) -> str:
    if baseline_value in (None, 0.0):
        return (
            f"{label}: baseline={baseline_value} current={current_value:.4f} "
            f"(ratio check skipped)"
        )
    ratio = (current_value - baseline_value) / baseline_value
    if ratio > ratio_limit:
        return (
            f"{label}: FAIL current={current_value:.4f} baseline={baseline_value:.4f} "
            f"delta={ratio:.2%} limit={ratio_limit:.0%}"
        )
    return (
        f"{label}: ok current={current_value:.4f} baseline={baseline_value:.4f} "
        f"delta={ratio:.2%} limit={ratio_limit:.0%}"
    )


def _evaluate_window(
    *,
    window: int,
    current: PerfWindow,
    baseline: PerfWindow | None,
    args: argparse.Namespace,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    healthy = True
    if baseline is not None:
        if baseline.total_api_requests < args.min_requests or current.total_api_requests < args.min_requests:
            issues.append(
                f"Window {window}m skipped: insufficient request sample "
                f"(baseline={baseline.total_api_requests}, current={current.total_api_requests}, min={args.min_requests})"
            )
            return True, issues

        if baseline.p95_ms is None or current.p95_ms is None:
            issues.append(f"Window {window}m skipped: missing p95 in comparison")
            return True, issues

        status = _build_status(
            current_value=current.p95_ms,
            baseline_value=baseline.p95_ms,
            ratio_limit=args.max_p95_growth,
            label=f"Window {window}m p95_ms",
        )
        if status.startswith(f"Window {window}m p95_ms: FAIL"):
            healthy = False
            issues.append(status)

        if current.error_rate > baseline.error_rate + args.error_rate_delta:
            healthy = False
            issues.append(
                f"Window {window}m: error_rate failed "
                f"current={current.error_rate:.4f} baseline={baseline.error_rate:.4f} "
                f"delta={current.error_rate - baseline.error_rate:.4f} "
                f"limit={args.error_rate_delta:.4f}"
            )

        if baseline.throughput_rps <= 0:
            issues.append(f"Window {window}m: baseline throughput is 0, skipping throughput check")
        else:
            drop_limit = 1.0 - args.max_throughput_drop_ratio
            ratio = current.throughput_rps / baseline.throughput_rps
            if ratio < drop_limit:
                healthy = False
                issues.append(
                    f"Window {window}m: throughput_rps failed "
                    f"current={current.throughput_rps:.4f} baseline={baseline.throughput_rps:.4f} "
                    f"ratio={ratio:.4f} limit={drop_limit:.4f}"
                )
    else:
        issues.append(f"Window {window}m: no baseline snapshot for comparison")
        healthy = False
    return healthy, issues


def _evaluate(args: argparse.Namespace) -> tuple[bool, list[str], list[str]]:
    current_snapshot = _build_snapshot(args)
    if not args.baseline:
        return False, [], ["--baseline is required"]
    baseline_snapshot = _build_snapshot(argparse.Namespace(**{
        "input": args.baseline,
        "top_endpoints": args.top_endpoints,
        "windows": args.windows,
        "output": "",
    }))

    baseline_windows = load_windows(baseline_snapshot)
    current_windows = load_windows(current_snapshot)
    errors: list[str] = []
    warnings: list[str] = []
    ok = True

    for window in sorted(set(current_windows) | set(baseline_windows)):
        current = current_windows.get(window)
        baseline = baseline_windows.get(window)
        if current is None:
            warnings.append(f"Window {window}m: no current snapshot for comparison")
            continue
        window_ok, window_messages = _evaluate_window(
            window=window,
            current=current,
            baseline=baseline,
            args=args,
        )
        if baseline is None:
            if window_messages:
                warnings.append(window_messages[0])
            ok = False
            continue
        if not window_ok:
            ok = False
            errors.extend(window_messages)
            continue
        if window_messages:
            warnings.extend(window_messages)

    return ok, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare a current performance snapshot against a baseline and fail on KPI regressions.",
    )
    parser.add_argument("--baseline", required=True, help="Path to baseline JSON snapshot.")
    parser.add_argument("--input", default="", help="Optional local snapshot JSON (default: generate fresh snapshot).")
    parser.add_argument(
        "--output",
        default="",
        help="Optional output path for generated current snapshot.",
    )
    parser.add_argument(
        "--windows",
        default="15,60,1440",
        help="Comma separated windows in minutes for snapshot generation.",
    )
    parser.add_argument("--top-endpoints", type=int, default=10, help="Top endpoints per window.")
    parser.add_argument(
        "--max-p95-growth",
        type=float,
        default=0.20,
        help="Max allowed p95 growth versus baseline (ratio).",
    )
    parser.add_argument(
        "--error-rate-delta",
        type=float,
        default=0.005,
        help="Max allowed absolute error-rate increase versus baseline.",
    )
    parser.add_argument(
        "--max-throughput-drop-ratio",
        type=float,
        default=0.10,
        help="Max allowed throughput drop vs baseline, as ratio fraction.",
    )
    parser.add_argument(
        "--min-requests",
        type=int,
        default=10,
        help="Minimum request count required for comparison window.",
    )
    args = parser.parse_args()
    args.windows = _parse_windows(args.windows)
    args.max_throughput_drop_ratio = min(max(args.max_throughput_drop_ratio, 0.0), 1.0)

    healthy, errors, warnings = _evaluate(args)
    if warnings:
        print("Performance check warnings:")
        for item in warnings:
            print(f" - {item}")
    if not healthy:
        print("Performance check failed:")
        for item in errors:
            print(f" - {item}")
        return 1
    print("Performance check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
