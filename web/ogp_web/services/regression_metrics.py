from __future__ import annotations

from time import monotonic


def _labels(*, flag: str, rollout_mode: str, cohort: str, server_id: str, flow_type: str, status: str) -> dict[str, object]:
    return {
        "feature_flag": flag,
        "rollout_mode": rollout_mode,
        "rollout_cohort": cohort,
        "server_id": server_id,
        "flow_type": flow_type,
        "status": status,
    }


def start_timer() -> float:
    return monotonic()


def record_error_rate(metrics_store, *, username: str, path: str, method: str, labels: dict[str, object]) -> None:
    metrics_store.log_event(
        event_type="rollout_error_rate",
        username=username,
        path=path,
        method=method,
        status_code=200,
        meta=dict(labels),
    )


def record_generation_latency(metrics_store, *, username: str, path: str, method: str, labels: dict[str, object], started_at: float) -> None:
    payload = dict(labels)
    payload["generation_latency_ms"] = int((monotonic() - started_at) * 1000)
    metrics_store.log_event(
        event_type="rollout_generation_latency",
        username=username,
        path=path,
        method=method,
        status_code=200,
        meta=payload,
    )


def record_validation_fail_rate(metrics_store, *, username: str, path: str, method: str, labels: dict[str, object], failed: bool) -> None:
    payload = dict(labels)
    payload["validation_failed"] = bool(failed)
    metrics_store.log_event(
        event_type="rollout_validation_fail_rate",
        username=username,
        path=path,
        method=method,
        status_code=200,
        meta=payload,
    )


def record_async_queue_lag(metrics_store, *, username: str, path: str, method: str, labels: dict[str, object], lag_ms: int) -> None:
    payload = dict(labels)
    payload["async_queue_lag_ms"] = max(0, int(lag_ms or 0))
    metrics_store.log_event(
        event_type="rollout_async_queue_lag",
        username=username,
        path=path,
        method=method,
        status_code=200,
        meta=payload,
    )


def build_rollout_labels(*, flag: str, rollout_mode: str, cohort: str, server_id: str, flow_type: str, status: str) -> dict[str, object]:
    return _labels(
        flag=flag,
        rollout_mode=rollout_mode,
        cohort=cohort,
        server_id=server_id,
        flow_type=flow_type,
        status=status,
    )
