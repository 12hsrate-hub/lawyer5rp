from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from load.suggest_load_support import (  # noqa: E402
    DEFAULT_SINGLE_ERROR_RATE_THRESHOLD,
    DEFAULT_SINGLE_P95_THRESHOLD_MS,
    build_rollout_report_markdown,
    build_rollout_summary,
    evaluate_single_summary,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate single, parallel, and mixed load artifacts for suggest rollout.")
    parser.add_argument("--single-summary", required=True, help="Path to single-profile summary.json")
    parser.add_argument("--parallel-summary", required=True, help="Path to parallel summary.json")
    parser.add_argument("--mixed-summary", required=True, help="Path to mixed summary.json")
    parser.add_argument("--stage", default="telemetry_only", help="Rollout stage: telemetry_only | optimization | limits")
    parser.add_argument("--output-dir", required=True, help="Directory for rollout_summary.json and rollout_report.md")
    parser.add_argument("--single-threshold-p95-ms", type=float, default=DEFAULT_SINGLE_P95_THRESHOLD_MS)
    parser.add_argument("--single-threshold-error-rate", type=float, default=DEFAULT_SINGLE_ERROR_RATE_THRESHOLD)
    parser.add_argument("--fail-on-blockers", action="store_true", help="Exit non-zero if rollout blockers are present")
    return parser.parse_args()


def _read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    single_summary = _read_json(args.single_summary)
    parallel_summary = _read_json(args.parallel_summary)
    mixed_summary = _read_json(args.mixed_summary)

    rollout_summary = build_rollout_summary(
        stage=args.stage,
        single_evaluation=evaluate_single_summary(
            single_summary,
            threshold_p95_ms=args.single_threshold_p95_ms,
            threshold_error_rate=args.single_threshold_error_rate,
        ),
        parallel_summary=parallel_summary,
        mixed_summary=mixed_summary,
    )

    (output_dir / "rollout_summary.json").write_text(
        json.dumps(rollout_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "rollout_report.md").write_text(
        build_rollout_report_markdown(rollout_summary),
        encoding="utf-8",
    )

    if args.fail_on_blockers and rollout_summary.get("blockers"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
