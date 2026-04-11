from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import httpx
except Exception as exc:  # pragma: no cover - exercised at runtime only
    raise RuntimeError(
        "httpx is required to run suggest load tests. Install web dependencies first: "
        "py -m pip install -r web/requirements_web.txt"
    ) from exc

from load.suggest_load_support import (
    DEFAULT_CONCURRENCY_TIERS,
    DEFAULT_DURATION,
    DEFAULT_K6_SCRIPT,
    DEFAULT_SUGGEST_PROFILES,
    SESSION_COOKIE_NAME,
    build_artifact_dir,
    build_k6_env,
    build_report_markdown,
    new_run_id,
    normalize_profile_name,
    normalize_vus,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single k6 suggest load scenario.")
    parser.add_argument("--base-url", required=True, help="Base URL, for example https://lawyer5rp.online")
    parser.add_argument("--profile", default="short", choices=DEFAULT_SUGGEST_PROFILES)
    parser.add_argument("--vus", type=int, default=DEFAULT_CONCURRENCY_TIERS[0], help="Concurrent virtual users")
    parser.add_argument("--duration", default=DEFAULT_DURATION, help="k6 duration, e.g. 30s, 1m, 5m")
    parser.add_argument("--run-id", default="", help="Optional run id. Defaults to UTC timestamp.")
    parser.add_argument("--artifacts-root", default="artifacts/load", help="Root artifact directory")
    parser.add_argument("--session-cookie", default="", help="Existing ogp_web_session cookie value")
    parser.add_argument("--username", default="", help="Username for /api/auth/login if no session cookie is provided")
    parser.add_argument("--password", default="", help="Password for /api/auth/login if no session cookie is provided")
    parser.add_argument("--k6-bin", default="k6", help="Path to k6 binary")
    parser.add_argument("--threshold-p95-ms", type=int, default=0, help="Optional k6 p95 threshold in ms")
    parser.add_argument("--threshold-error-rate", type=float, default=-1.0, help="Optional k6 failure rate threshold")
    return parser.parse_args()


def _login_for_session_cookie(*, base_url: str, username: str, password: str) -> str:
    if not username or not password:
        raise RuntimeError("Either --session-cookie or both --username and --password are required.")
    with httpx.Client(base_url=base_url.rstrip("/"), follow_redirects=False, verify=True, timeout=30.0) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        response.raise_for_status()
        cookie = client.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        raise RuntimeError(f"Login succeeded but {SESSION_COOKIE_NAME!r} cookie was not returned.")
    return cookie


def main() -> int:
    args = _parse_args()
    profile = normalize_profile_name(args.profile)
    vus = normalize_vus(args.vus)
    run_id = str(args.run_id or "").strip() or new_run_id()
    artifact_dir = build_artifact_dir(artifacts_root=args.artifacts_root, run_id=run_id, profile=profile)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    session_cookie = str(args.session_cookie or "").strip()
    if not session_cookie:
        session_cookie = _login_for_session_cookie(
            base_url=args.base_url,
            username=str(args.username or "").strip(),
            password=str(args.password or "").strip(),
        )

    env = os.environ.copy()
    env.update(
        build_k6_env(
            base_url=args.base_url,
            session_cookie=session_cookie,
            profile=profile,
            vus=vus,
            duration=args.duration,
            artifact_dir=artifact_dir,
            threshold_p95_ms=args.threshold_p95_ms or None,
            threshold_error_rate=args.threshold_error_rate if args.threshold_error_rate >= 0 else None,
        )
    )

    run_config = {
        "run_id": run_id,
        "profile": profile,
        "vus": vus,
        "duration": args.duration,
        "base_url": args.base_url.rstrip("/"),
        "artifact_dir": str(artifact_dir),
        "k6_script": str(DEFAULT_K6_SCRIPT),
    }
    (artifact_dir / "run_config.json").write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    command = [
        args.k6_bin,
        "run",
        str(DEFAULT_K6_SCRIPT),
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)

    summary_path = artifact_dir / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        report = build_report_markdown(
            summary,
            profile=profile,
            vus=vus,
            duration=args.duration,
            base_url=args.base_url.rstrip("/"),
            run_id=run_id,
        )
        (artifact_dir / "report.md").write_text(report, encoding="utf-8")

    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
