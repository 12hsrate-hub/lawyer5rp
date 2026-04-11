from __future__ import annotations

import argparse
import json
import os
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
        "httpx is required to run mixed suggest load tests. Install web dependencies first: "
        "py -m pip install -r web/requirements_web.txt"
    ) from exc

from load.suggest_load_support import (
    DEFAULT_COLLATERAL_P95_GROWTH_LIMIT,
    DEFAULT_COLLATERAL_P99_GROWTH_LIMIT,
    DEFAULT_DURATION,
    DEFAULT_GROUP_A_VUS,
    DEFAULT_GROUP_B_VUS,
    DEFAULT_MIXED_K6_SCRIPT,
    DEFAULT_SUGGEST_PROFILES,
    SESSION_COOKIE_NAME,
    build_mixed_artifact_dir,
    build_mixed_k6_env,
    build_mixed_phase_artifact_dir,
    build_mixed_report_markdown,
    build_mixed_summary,
    evaluate_mixed_impact,
    new_run_id,
    normalize_profile_name,
    normalize_vus,
    summarize_mixed_phase_run,
    summarize_server_metrics_csv,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Group B baseline + mixed Group A/Group B impact test.")
    parser.add_argument("--base-url", required=True, help="Base URL, for example https://lawyer5rp.online")
    parser.add_argument("--group-a-profile", default="long", choices=DEFAULT_SUGGEST_PROFILES)
    parser.add_argument("--group-a-vus", type=int, default=DEFAULT_GROUP_A_VUS, help="Heavy suggest VUs for Group A")
    parser.add_argument("--group-b-vus", type=int, default=DEFAULT_GROUP_B_VUS, help="Standard endpoint VUs for Group B")
    parser.add_argument("--duration", default=DEFAULT_DURATION, help="k6 duration, e.g. 30s, 1m, 5m")
    parser.add_argument("--run-id", default="", help="Optional run id. Defaults to UTC timestamp.")
    parser.add_argument("--artifacts-root", default="artifacts/load", help="Root artifact directory")
    parser.add_argument("--session-cookie", default="", help="Existing ogp_web_session cookie value")
    parser.add_argument("--username", default="", help="Username for /api/auth/login if no session cookie is provided")
    parser.add_argument("--password", default="", help="Password for /api/auth/login if no session cookie is provided")
    parser.add_argument("--k6-bin", default="k6", help="Path to k6 binary")
    parser.add_argument(
        "--collateral-p95-growth-limit",
        type=float,
        default=DEFAULT_COLLATERAL_P95_GROWTH_LIMIT,
        help="Maximum allowed Group B p95 growth ratio during mixed load",
    )
    parser.add_argument(
        "--collateral-p99-growth-limit",
        type=float,
        default=DEFAULT_COLLATERAL_P99_GROWTH_LIMIT,
        help="Maximum allowed Group B p99 growth ratio during mixed load",
    )
    parser.add_argument(
        "--fail-on-sla",
        action="store_true",
        help="Exit non-zero when collateral impact exceeds limits or a phase fails.",
    )
    parser.add_argument(
        "--sample-server",
        action="store_true",
        help="Run scripts/server_sampler.py during each phase and save phase-level server metrics.",
    )
    parser.add_argument("--server-sampler-interval", type=float, default=1.0, help="Server sampler interval in seconds")
    parser.add_argument("--server-sampler-python", default=sys.executable, help="Python executable for server sampler")
    return parser.parse_args()


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


def _start_server_sampler(*, python_bin: str, artifact_dir: Path, interval: float) -> tuple[subprocess.Popen[str], Path]:
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


def _run_phase(
    *,
    phase: str,
    base_url: str,
    session_cookie: str,
    group_a_profile: str,
    group_a_vus: int,
    group_b_vus: int,
    duration: str,
    artifact_dir: Path,
    k6_bin: str,
    sample_server: bool,
    server_sampler_python: str,
    server_sampler_interval: float,
) -> dict[str, object]:
    artifact_dir.mkdir(parents=True, exist_ok=True)

    phase_config = {
        "phase": phase,
        "base_url": base_url.rstrip("/"),
        "group_a_profile": group_a_profile,
        "group_a_vus": group_a_vus,
        "group_b_vus": group_b_vus,
        "duration": duration,
        "k6_script": str(DEFAULT_MIXED_K6_SCRIPT),
        "sample_server": bool(sample_server),
        "server_sampler_interval": float(server_sampler_interval),
    }
    (artifact_dir / "run_config.json").write_text(
        json.dumps(phase_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        build_mixed_k6_env(
            base_url=base_url,
            session_cookie=session_cookie,
            group_a_profile=group_a_profile,
            group_a_vus=group_a_vus,
            group_b_vus=group_b_vus,
            duration=duration,
            artifact_dir=artifact_dir,
        )
    )

    sampler_process: subprocess.Popen[str] | None = None
    sampler_output: Path | None = None
    if sample_server:
        sampler_process, sampler_output = _start_server_sampler(
            python_bin=server_sampler_python,
            artifact_dir=artifact_dir,
            interval=server_sampler_interval,
        )
        time.sleep(min(max(server_sampler_interval, 0.1), 1.0))

    command = [k6_bin, "run", str(DEFAULT_MIXED_K6_SCRIPT)]
    try:
        completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    finally:
        if sampler_process is not None:
            sampler_process.terminate()
            try:
                sampler_process.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                sampler_process.kill()
                sampler_process.wait(timeout=5.0)

    summary_path = artifact_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    server_metrics_summary: dict[str, object] | None = None
    if sampler_output is not None:
        server_metrics_summary = summarize_server_metrics_csv(sampler_output)
        (artifact_dir / "server_metrics_summary.json").write_text(
            json.dumps(server_metrics_summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    phase_summary = summarize_mixed_phase_run(
        summary,
        phase=phase,
        group_a_profile=group_a_profile,
        group_a_vus=group_a_vus,
        group_b_vus=group_b_vus,
        duration=duration,
        base_url=base_url,
        artifact_dir=artifact_dir,
        exit_code=int(completed.returncode),
        server_metrics_summary=server_metrics_summary,
    )
    return phase_summary


def main() -> int:
    args = _parse_args()
    group_a_profile = normalize_profile_name(args.group_a_profile)
    group_a_vus = max(0, int(args.group_a_vus))
    group_b_vus = normalize_vus(args.group_b_vus)
    run_id = str(args.run_id or "").strip() or new_run_id()

    session_cookie = str(args.session_cookie or "").strip()
    if not session_cookie:
        session_cookie = _login_for_session_cookie(
            base_url=args.base_url,
            username=str(args.username or "").strip(),
            password=str(args.password or "").strip(),
        )

    mixed_artifact_dir = build_mixed_artifact_dir(artifacts_root=args.artifacts_root, run_id=run_id)
    baseline_dir = build_mixed_phase_artifact_dir(
        artifacts_root=args.artifacts_root,
        run_id=run_id,
        phase="baseline_group_b",
    )
    mixed_dir = build_mixed_phase_artifact_dir(
        artifacts_root=args.artifacts_root,
        run_id=run_id,
        phase="mixed_group_ab",
    )
    mixed_artifact_dir.mkdir(parents=True, exist_ok=True)

    baseline_phase = _run_phase(
        phase="baseline_group_b",
        base_url=args.base_url,
        session_cookie=session_cookie,
        group_a_profile=group_a_profile,
        group_a_vus=0,
        group_b_vus=group_b_vus,
        duration=args.duration,
        artifact_dir=baseline_dir,
        k6_bin=args.k6_bin,
        sample_server=bool(args.sample_server),
        server_sampler_python=args.server_sampler_python,
        server_sampler_interval=args.server_sampler_interval,
    )
    mixed_phase = _run_phase(
        phase="mixed_group_ab",
        base_url=args.base_url,
        session_cookie=session_cookie,
        group_a_profile=group_a_profile,
        group_a_vus=group_a_vus,
        group_b_vus=group_b_vus,
        duration=args.duration,
        artifact_dir=mixed_dir,
        k6_bin=args.k6_bin,
        sample_server=bool(args.sample_server),
        server_sampler_python=args.server_sampler_python,
        server_sampler_interval=args.server_sampler_interval,
    )

    impact_sla = evaluate_mixed_impact(
        baseline_phase,
        mixed_phase,
        p95_growth_limit=args.collateral_p95_growth_limit,
        p99_growth_limit=args.collateral_p99_growth_limit,
    )
    summary = build_mixed_summary(
        run_id=run_id,
        base_url=args.base_url,
        duration=args.duration,
        artifacts_root=args.artifacts_root,
        group_a_profile=group_a_profile,
        group_a_vus=group_a_vus,
        group_b_vus=group_b_vus,
        baseline_phase=baseline_phase,
        mixed_phase=mixed_phase,
        impact_sla=impact_sla,
    )

    (mixed_artifact_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (mixed_artifact_dir / "report.md").write_text(
        build_mixed_report_markdown(summary),
        encoding="utf-8",
    )
    (mixed_artifact_dir / "run_config.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "base_url": args.base_url.rstrip("/"),
                "group_a_profile": group_a_profile,
                "group_a_vus": group_a_vus,
                "group_b_vus": group_b_vus,
                "duration": args.duration,
                "artifacts_root": args.artifacts_root,
                "sample_server": bool(args.sample_server),
                "server_sampler_interval": float(args.server_sampler_interval),
                "collateral_p95_growth_limit": float(args.collateral_p95_growth_limit),
                "collateral_p99_growth_limit": float(args.collateral_p99_growth_limit),
                "fail_on_sla": bool(args.fail_on_sla),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if args.fail_on_sla and not impact_sla.get("pass", False):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
