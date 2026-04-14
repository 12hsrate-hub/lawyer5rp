from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import httpx
except Exception as exc:  # pragma: no cover - exercised at runtime only
    raise RuntimeError(
        "httpx is required to run parallel suggest load tests. Install web dependencies first: "
        "py -m pip install -r web/requirements_web.txt"
    ) from exc

from load.suggest_load_support import (
    DEFAULT_DURATION,
    DEFAULT_SUGGEST_PROFILES,
    SESSION_COOKIE_NAME,
    build_artifact_dir,
    build_parallel_artifact_dir,
    build_parallel_report_markdown,
    build_parallel_summary,
    default_profile_vus_map,
    evaluate_sla,
    new_run_id,
    normalize_profile_name,
    normalize_vus,
    summarize_profile_run,
    summarize_server_metrics_csv,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multiple suggest load profiles in parallel.")
    parser.add_argument("--base-url", required=True, help="Base URL, for example https://lawyer5rp.online")
    parser.add_argument(
        "--profiles",
        default=",".join(DEFAULT_SUGGEST_PROFILES),
        help="Comma-separated profiles, e.g. short,mid,long",
    )
    parser.add_argument(
        "--profile-vus",
        action="append",
        default=[],
        help="Explicit per-profile VU mapping, e.g. short:5. Can be repeated.",
    )
    parser.add_argument("--duration", default=DEFAULT_DURATION, help="k6 duration, e.g. 30s, 1m, 5m")
    parser.add_argument("--run-id", default="", help="Optional run id. Defaults to UTC timestamp.")
    parser.add_argument("--artifacts-root", default="artifacts/load", help="Root artifact directory")
    parser.add_argument("--session-cookie", default="", help="Existing ogp_web_session cookie value")
    parser.add_argument("--username", default="", help="Username for /api/auth/login if no session cookie is provided")
    parser.add_argument("--password", default="", help="Password for /api/auth/login if no session cookie is provided")
    parser.add_argument("--python-bin", default=sys.executable, help="Python executable for child runners")
    parser.add_argument("--k6-bin", default="k6", help="Path to k6 binary")
    parser.add_argument("--threshold-p95-ms", type=int, default=0, help="Optional per-profile p95 threshold in ms")
    parser.add_argument(
        "--threshold-error-rate",
        type=float,
        default=-1.0,
        help="Optional per-profile failure rate threshold",
    )
    parser.add_argument(
        "--fail-on-sla",
        action="store_true",
        help="Exit non-zero when any profile breaches thresholds or a child runner fails.",
    )
    parser.add_argument(
        "--sample-server",
        action="store_true",
        help="Run scripts/server_sampler.py during the full parallel scenario and save parallel/server_metrics.csv",
    )
    parser.add_argument("--server-sampler-interval", type=float, default=1.0, help="Server sampler interval in seconds")
    parser.add_argument("--server-sampler-python", default=sys.executable, help="Python executable for server sampler")
    return parser.parse_args()


def _parse_profiles(raw_profiles: str) -> list[str]:
    parts = [part.strip() for part in str(raw_profiles or "").split(",") if part.strip()]
    if not parts:
        return list(DEFAULT_SUGGEST_PROFILES)
    return [normalize_profile_name(part) for part in parts]


def _parse_profile_vus_overrides(raw_items: list[str], profiles: list[str]) -> dict[str, int]:
    mapping = default_profile_vus_map(profiles)
    for raw_item in raw_items:
        normalized = str(raw_item or "").strip()
        if not normalized:
            continue
        if ":" not in normalized:
            raise ValueError(f"Invalid --profile-vus entry {raw_item!r}. Expected profile:vus.")
        profile_name, raw_vus = normalized.split(":", 1)
        mapping[normalize_profile_name(profile_name)] = normalize_vus(raw_vus)
    return mapping


def _login_for_session_cookie(*, base_url: str, username: str, password: str) -> str:
    if not username or not password:
        raise RuntimeError("Either --session-cookie or both --username and --password are required.")
    with httpx.Client(base_url=base_url.rstrip("/"), follow_redirects=False, verify=True, timeout=30.0) as client:
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        response.raise_for_status()
        cookie = client.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        raise RuntimeError(f"Login succeeded but {SESSION_COOKIE_NAME!r} cookie was not returned.")
    return cookie


def _build_child_command(
    *,
    python_bin: str,
    base_url: str,
    profile: str,
    vus: int,
    duration: str,
    run_id: str,
    artifacts_root: str,
    session_cookie: str,
    k6_bin: str,
    threshold_p95_ms: int | None,
    threshold_error_rate: float | None,
) -> list[str]:
    command = [
        python_bin,
        "scripts/run_suggest_load.py",
        "--base-url",
        base_url.rstrip("/"),
        "--profile",
        profile,
        "--vus",
        str(vus),
        "--duration",
        duration,
        "--run-id",
        run_id,
        "--artifacts-root",
        artifacts_root,
        "--session-cookie",
        session_cookie,
        "--k6-bin",
        k6_bin,
    ]
    if threshold_p95_ms is not None:
        command.extend(["--threshold-p95-ms", str(threshold_p95_ms)])
    if threshold_error_rate is not None:
        command.extend(["--threshold-error-rate", str(threshold_error_rate)])
    return command


def _start_server_sampler(
    *,
    python_bin: str,
    artifact_dir: Path,
    interval: float,
) -> tuple[subprocess.Popen[str], Path]:
    output_path = artifact_dir / "server_metrics.csv"
    command = [
        python_bin,
        "scripts/server_sampler.py",
        "--output",
        str(output_path),
        "--interval",
        str(interval),
    ]
    process = subprocess.Popen(command, cwd=REPO_ROOT)
    return process, output_path


def main() -> int:
    args = _parse_args()
    run_id = str(args.run_id or "").strip() or new_run_id()
    profiles = _parse_profiles(args.profiles)
    profile_vus = _parse_profile_vus_overrides(args.profile_vus, profiles)

    session_cookie = str(args.session_cookie or "").strip()
    if not session_cookie:
        session_cookie = _login_for_session_cookie(
            base_url=args.base_url,
            username=str(args.username or "").strip(),
            password=str(args.password or "").strip(),
        )

    threshold_p95_ms = args.threshold_p95_ms or None
    threshold_error_rate = args.threshold_error_rate if args.threshold_error_rate >= 0 else None
    running: list[tuple[str, int, subprocess.Popen[str]]] = []
    profile_runs: list[dict[str, object]] = []
    parallel_artifact_dir = build_parallel_artifact_dir(artifacts_root=args.artifacts_root, run_id=run_id)
    parallel_artifact_dir.mkdir(parents=True, exist_ok=True)

    sampler_process: subprocess.Popen[str] | None = None
    sampler_output: Path | None = None
    if args.sample_server:
        sampler_process, sampler_output = _start_server_sampler(
            python_bin=args.server_sampler_python,
            artifact_dir=parallel_artifact_dir,
            interval=args.server_sampler_interval,
        )
        time.sleep(min(max(args.server_sampler_interval, 0.1), 1.0))

    try:
        for profile in profiles:
            vus = profile_vus[profile]
            command = _build_child_command(
                python_bin=args.python_bin,
                base_url=args.base_url,
                profile=profile,
                vus=vus,
                duration=args.duration,
                run_id=run_id,
                artifacts_root=args.artifacts_root,
                session_cookie=session_cookie,
                k6_bin=args.k6_bin,
                threshold_p95_ms=threshold_p95_ms,
                threshold_error_rate=threshold_error_rate,
            )
            process = subprocess.Popen(command, cwd=REPO_ROOT)
            running.append((profile, vus, process))

        for profile, vus, process in running:
            exit_code = int(process.wait())
            artifact_dir = build_artifact_dir(artifacts_root=args.artifacts_root, run_id=run_id, profile=profile)
            summary_path = artifact_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
            profile_summary = summarize_profile_run(
                summary,
                profile=profile,
                vus=vus,
                duration=args.duration,
                base_url=args.base_url,
                artifact_dir=artifact_dir,
                exit_code=exit_code,
            )
            profile_summary["sla"] = evaluate_sla(
                profile_summary,
                threshold_p95_ms=threshold_p95_ms,
                threshold_error_rate=threshold_error_rate,
            )
            profile_runs.append(profile_summary)
    finally:
        if sampler_process is not None:
            sampler_process.terminate()
            try:
                sampler_process.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                sampler_process.kill()
                sampler_process.wait(timeout=5.0)

    server_metrics_summary: dict[str, object] | None = None
    if sampler_output is not None:
        server_metrics_summary = summarize_server_metrics_csv(sampler_output)
        (parallel_artifact_dir / "server_metrics_summary.json").write_text(
            json.dumps(server_metrics_summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    consolidated = build_parallel_summary(
        run_id=run_id,
        profile_runs=profile_runs,
        base_url=args.base_url,
        duration=args.duration,
        artifacts_root=args.artifacts_root,
        server_metrics_summary=server_metrics_summary,
    )
    (parallel_artifact_dir / "summary.json").write_text(
        json.dumps(consolidated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (parallel_artifact_dir / "report.md").write_text(
        build_parallel_report_markdown(consolidated),
        encoding="utf-8",
    )
    (parallel_artifact_dir / "run_config.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profiles": profiles,
                "profile_vus": profile_vus,
                "duration": args.duration,
                "base_url": args.base_url.rstrip("/"),
                "artifacts_root": args.artifacts_root,
                "fail_on_sla": bool(args.fail_on_sla),
                "sample_server": bool(args.sample_server),
                "server_sampler_interval": float(args.server_sampler_interval),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if args.fail_on_sla:
        for item in profile_runs:
            sla = item.get("sla")
            if isinstance(sla, dict) and not sla.get("pass", False):
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
