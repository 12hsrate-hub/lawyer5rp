from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SUGGEST_PROFILES = ("short", "mid", "long")
DEFAULT_CONCURRENCY_TIERS = (5, 10, 30, 50)
DEFAULT_DURATION = "1m"
DEFAULT_K6_SCRIPT = Path("load/k6/suggest_load.js")
SESSION_COOKIE_NAME = "ogp_web_session"


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_profile_name(profile: str) -> str:
    normalized = str(profile or "").strip().lower()
    if normalized not in DEFAULT_SUGGEST_PROFILES:
        allowed = ", ".join(DEFAULT_SUGGEST_PROFILES)
        raise ValueError(f"Unsupported suggest load profile {profile!r}. Expected one of: {allowed}.")
    return normalized


def normalize_vus(vus: int | str) -> int:
    try:
        value = int(vus)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid VU count: {vus!r}") from exc
    if value < 1:
        raise ValueError("VU count must be >= 1.")
    return value


def build_artifact_dir(*, artifacts_root: str | Path, run_id: str, profile: str) -> Path:
    normalized_run_id = str(run_id or "").strip() or new_run_id()
    normalized_profile = normalize_profile_name(profile)
    return Path(artifacts_root).expanduser().resolve() / normalized_run_id / normalized_profile


def build_parallel_artifact_dir(*, artifacts_root: str | Path, run_id: str) -> Path:
    normalized_run_id = str(run_id or "").strip() or new_run_id()
    return Path(artifacts_root).expanduser().resolve() / normalized_run_id / "parallel"


def default_profile_vus_map(profiles: tuple[str, ...] | list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    normalized_profiles = [normalize_profile_name(profile) for profile in profiles]
    if not normalized_profiles:
        return mapping
    last_tier = DEFAULT_CONCURRENCY_TIERS[-1]
    for index, profile in enumerate(normalized_profiles):
        mapping[profile] = DEFAULT_CONCURRENCY_TIERS[index] if index < len(DEFAULT_CONCURRENCY_TIERS) else last_tier
    return mapping


def build_k6_env(
    *,
    base_url: str,
    session_cookie: str,
    profile: str,
    vus: int,
    duration: str,
    artifact_dir: str | Path,
    threshold_p95_ms: int | None = None,
    threshold_error_rate: float | None = None,
) -> dict[str, str]:
    normalized_profile = normalize_profile_name(profile)
    normalized_vus = normalize_vus(vus)
    summary_path = Path(artifact_dir) / "summary.json"
    env = {
        "BASE_URL": str(base_url or "").rstrip("/"),
        "SESSION_COOKIE": str(session_cookie or "").strip(),
        "PROFILE": normalized_profile,
        "VUS": str(normalized_vus),
        "DURATION": str(duration or DEFAULT_DURATION).strip() or DEFAULT_DURATION,
        "SUMMARY_PATH": str(summary_path),
    }
    if threshold_p95_ms is not None:
        env["THRESHOLD_P95_MS"] = str(max(1, int(threshold_p95_ms)))
    if threshold_error_rate is not None:
        env["THRESHOLD_ERROR_RATE"] = str(max(0.0, float(threshold_error_rate)))
    return env


def extract_metric_value(summary: dict[str, Any], metric_name: str, nested_key: str) -> float | int | None:
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict):
        return None
    metric = metrics.get(metric_name)
    if not isinstance(metric, dict):
        return None
    values = metric.get("values")
    if not isinstance(values, dict):
        return None
    value = values.get(nested_key)
    if isinstance(value, (int, float)):
        return value
    return None


def summarize_profile_run(
    summary: dict[str, Any],
    *,
    profile: str,
    vus: int,
    duration: str,
    base_url: str,
    artifact_dir: str | Path,
    exit_code: int = 0,
) -> dict[str, Any]:
    normalized_profile = normalize_profile_name(profile)
    normalized_vus = normalize_vus(vus)
    return {
        "profile": normalized_profile,
        "vus": normalized_vus,
        "duration": str(duration or DEFAULT_DURATION).strip() or DEFAULT_DURATION,
        "base_url": str(base_url or "").rstrip("/"),
        "artifact_dir": str(Path(artifact_dir)),
        "exit_code": int(exit_code),
        "p95_ms": extract_metric_value(summary, "http_req_duration", "p(95)"),
        "p99_ms": extract_metric_value(summary, "http_req_duration", "p(99)"),
        "avg_ms": extract_metric_value(summary, "http_req_duration", "avg"),
        "fail_rate": extract_metric_value(summary, "http_req_failed", "rate"),
        "suggest_ok": extract_metric_value(summary, "suggest_ok", "count"),
        "suggest_overload": extract_metric_value(summary, "suggest_overload", "count"),
        "suggest_error": extract_metric_value(summary, "suggest_error", "count"),
    }


def evaluate_sla(
    profile_summary: dict[str, Any],
    *,
    threshold_p95_ms: int | None = None,
    threshold_error_rate: float | None = None,
) -> dict[str, Any]:
    breaches: list[str] = []
    exit_code = int(profile_summary.get("exit_code") or 0)
    p95_ms = profile_summary.get("p95_ms")
    fail_rate = profile_summary.get("fail_rate")

    if exit_code != 0:
        breaches.append("runner_exit_nonzero")
    if threshold_p95_ms is not None:
        if not isinstance(p95_ms, (int, float)):
            breaches.append("missing_p95")
        elif float(p95_ms) > float(threshold_p95_ms):
            breaches.append("p95_exceeded")
    if threshold_error_rate is not None:
        if not isinstance(fail_rate, (int, float)):
            breaches.append("missing_fail_rate")
        elif float(fail_rate) > float(threshold_error_rate):
            breaches.append("error_rate_exceeded")

    return {
        "pass": not breaches,
        "breaches": breaches,
        "threshold_p95_ms": threshold_p95_ms,
        "threshold_error_rate": threshold_error_rate,
    }


def build_parallel_summary(
    *,
    run_id: str,
    profile_runs: list[dict[str, Any]],
    base_url: str,
    duration: str,
    artifacts_root: str | Path,
) -> dict[str, Any]:
    failing_profiles: list[str] = []
    for item in profile_runs:
        if not isinstance(item, dict):
            continue
        sla = item.get("sla")
        if isinstance(sla, dict) and not sla.get("pass", False):
            failing_profiles.append(str(item.get("profile") or "unknown"))
    return {
        "run_id": str(run_id or "").strip(),
        "base_url": str(base_url or "").rstrip("/"),
        "duration": str(duration or DEFAULT_DURATION).strip() or DEFAULT_DURATION,
        "artifacts_root": str(Path(artifacts_root)),
        "profile_run_count": len(profile_runs),
        "all_sla_pass": not failing_profiles,
        "failing_profiles": failing_profiles,
        "profiles": profile_runs,
    }


def build_parallel_report_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Parallel Suggest Load Report",
        "",
        f"- Run ID: `{summary.get('run_id')}`",
        f"- Base URL: `{summary.get('base_url')}`",
        f"- Duration: `{summary.get('duration')}`",
        f"- Profile runs: `{summary.get('profile_run_count')}`",
        f"- All SLA pass: `{summary.get('all_sla_pass')}`",
        f"- Failing profiles: `{', '.join(summary.get('failing_profiles', [])) or 'none'}`",
        "",
        "## Per-profile results",
        "",
    ]

    for item in summary.get("profiles", []):
        if not isinstance(item, dict):
            continue
        sla = item.get("sla") if isinstance(item.get("sla"), dict) else {}
        lines.extend(
            [
                f"### {item.get('profile')} ({item.get('vus')} VUs)",
                "",
                f"- Exit code: `{item.get('exit_code')}`",
                f"- `p95`: `{item.get('p95_ms')}`",
                f"- `p99`: `{item.get('p99_ms')}`",
                f"- `avg`: `{item.get('avg_ms')}`",
                f"- `fail_rate`: `{item.get('fail_rate')}`",
                f"- `suggest_ok`: `{item.get('suggest_ok')}`",
                f"- `suggest_overload`: `{item.get('suggest_overload')}`",
                f"- `suggest_error`: `{item.get('suggest_error')}`",
                f"- SLA pass: `{sla.get('pass')}`",
                f"- SLA breaches: `{', '.join(sla.get('breaches', [])) or 'none'}`",
                f"- Artifact dir: `{item.get('artifact_dir')}`",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def build_report_markdown(
    summary: dict[str, Any],
    *,
    profile: str,
    vus: int,
    duration: str,
    base_url: str,
    run_id: str,
) -> str:
    normalized_profile = normalize_profile_name(profile)
    normalized_vus = normalize_vus(vus)
    p95 = extract_metric_value(summary, "http_req_duration", "p(95)")
    p99 = extract_metric_value(summary, "http_req_duration", "p(99)")
    avg = extract_metric_value(summary, "http_req_duration", "avg")
    fail_rate = extract_metric_value(summary, "http_req_failed", "rate")
    ok_count = extract_metric_value(summary, "suggest_ok", "count")
    overload_count = extract_metric_value(summary, "suggest_overload", "count")
    error_count = extract_metric_value(summary, "suggest_error", "count")

    lines = [
        "# Suggest Load Test Report",
        "",
        f"- Run ID: `{run_id}`",
        f"- Profile: `{normalized_profile}`",
        f"- VUs: `{normalized_vus}`",
        f"- Duration: `{duration}`",
        f"- Base URL: `{base_url}`",
        "",
        "## Summary",
        "",
        f"- `http_req_duration p95`: `{p95}`",
        f"- `http_req_duration p99`: `{p99}`",
        f"- `http_req_duration avg`: `{avg}`",
        f"- `http_req_failed rate`: `{fail_rate}`",
        f"- `suggest_ok count`: `{ok_count}`",
        f"- `suggest_overload count`: `{overload_count}`",
        f"- `suggest_error count`: `{error_count}`",
        "",
        "## Artifact",
        "",
        "- `summary.json` contains the full k6 output for this run.",
    ]
    return "\n".join(lines).strip() + "\n"
