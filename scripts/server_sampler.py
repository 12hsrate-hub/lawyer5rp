from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timezone
from pathlib import Path
import signal
import time
from typing import Any


SHOULD_STOP = False


def _request_stop(_signum: int, _frame: Any) -> None:
    global SHOULD_STOP
    SHOULD_STOP = True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample host-level telemetry into a CSV file.")
    parser.add_argument("--output", required=True, help="CSV path to write, e.g. artifacts/load/<run_id>/server_metrics.csv")
    parser.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds (default: 1.0)")
    return parser.parse_args()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_load_average() -> tuple[float | None, float | None, float | None]:
    try:
        load_1m, load_5m, load_15m = os.getloadavg()
    except (AttributeError, OSError):
        return None, None, None
    return float(load_1m), float(load_5m), float(load_15m)


def _coerce_number(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.6f}"


def _build_row(psutil_module: Any) -> dict[str, str]:
    virtual_memory = psutil_module.virtual_memory()
    disk_io = psutil_module.disk_io_counters()
    net_io = psutil_module.net_io_counters()
    load_1m, load_5m, load_15m = _safe_load_average()

    return {
        "timestamp_utc": _utcnow_iso(),
        "cpu_percent": _coerce_number(psutil_module.cpu_percent(interval=None)),
        "memory_percent": _coerce_number(virtual_memory.percent),
        "memory_used_mb": _coerce_number(virtual_memory.used / (1024 * 1024)),
        "load_1m": _coerce_number(load_1m),
        "load_5m": _coerce_number(load_5m),
        "load_15m": _coerce_number(load_15m),
        "disk_read_mb": _coerce_number((disk_io.read_bytes if disk_io else 0) / (1024 * 1024)),
        "disk_write_mb": _coerce_number((disk_io.write_bytes if disk_io else 0) / (1024 * 1024)),
        "net_sent_mb": _coerce_number((net_io.bytes_sent if net_io else 0) / (1024 * 1024)),
        "net_recv_mb": _coerce_number((net_io.bytes_recv if net_io else 0) / (1024 * 1024)),
        "process_count": _coerce_number(len(psutil_module.pids())),
    }


def main() -> int:
    args = _parse_args()
    interval = float(args.interval)
    if interval <= 0:
        raise SystemExit("--interval must be > 0")

    try:
        import psutil  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime only
        raise RuntimeError(
            "psutil is required for server sampling. Install it with: py -m pip install psutil"
        ) from exc

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGINT, _request_stop)
    try:
        signal.signal(signal.SIGTERM, _request_stop)
    except (AttributeError, ValueError):  # pragma: no cover - platform/runtime specific
        pass

    headers = [
        "timestamp_utc",
        "cpu_percent",
        "memory_percent",
        "memory_used_mb",
        "load_1m",
        "load_5m",
        "load_15m",
        "disk_read_mb",
        "disk_write_mb",
        "net_sent_mb",
        "net_recv_mb",
        "process_count",
    ]

    psutil.cpu_percent(interval=None)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        handle.flush()

        while not SHOULD_STOP:
            started_at = time.monotonic()
            writer.writerow(_build_row(psutil))
            handle.flush()

            elapsed = time.monotonic() - started_at
            sleep_for = interval - elapsed
            if sleep_for > 0 and not SHOULD_STOP:
                time.sleep(sleep_for)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
