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
