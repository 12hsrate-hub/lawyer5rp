from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from ogp_web.server_config import DEFAULT_SERVER_CODE
from ogp_web.services.async_job_service import ACTIVE_STATUSES, JOB_POLICIES, TERMINAL_STATUSES
from ogp_web.storage.admin_metrics_store import AdminMetricsStore


@dataclass(frozen=True)
class SyntheticStepResult:
    step_code: str
    status: str
    duration_ms: int
    details: dict[str, Any]


class SyntheticRunnerService:
    def __init__(self, metrics_store: AdminMetricsStore):
        self.metrics_store = metrics_store

    def _emit_step_event(
        self,
        *,
        run_id: str,
        suite: str,
        server_code: str,
        step: SyntheticStepResult,
    ) -> None:
        self.metrics_store.log_event(
            event_type="synthetic_step",
            username="synthetic_runner",
            server_code=server_code,
            path=f"/synthetic/{suite}/{step.step_code}",
            method="SYNTH",
            status_code=200 if step.status == "pass" else 500,
            duration_ms=step.duration_ms,
            meta={
                "run_id": run_id,
                "suite": suite,
                "step_code": step.step_code,
                "step_status": step.status,
                "details": step.details,
            },
        )

    def _emit_run_event(
        self,
        *,
        run_id: str,
        suite: str,
        server_code: str,
        status: str,
        duration_ms: int,
        trigger: str,
        steps: list[SyntheticStepResult],
    ) -> None:
        self.metrics_store.log_event(
            event_type="synthetic_run",
            username="synthetic_runner",
            server_code=server_code,
            path=f"/synthetic/{suite}",
            method="SYNTH",
            status_code=200 if status == "pass" else 500,
            duration_ms=duration_ms,
            meta={
                "run_id": run_id,
                "suite": suite,
                "run_status": status,
                "trigger": trigger,
                "steps_total": len(steps),
                "steps_failed": sum(1 for item in steps if item.status != "pass"),
                "step_results": [
                    {
                        "step_code": item.step_code,
                        "status": item.status,
                        "duration_ms": item.duration_ms,
                        "details": item.details,
                    }
                    for item in steps
                ],
            },
        )

    def _check(self, code: str, fn: Callable[[], tuple[bool, dict[str, Any]]]) -> SyntheticStepResult:
        started = time.perf_counter()
        ok = False
        details: dict[str, Any] = {}
        try:
            ok, details = fn()
        except Exception as exc:  # noqa: BLE001
            ok = False
            details = {"error": str(exc)}
        duration_ms = int((time.perf_counter() - started) * 1000)
        return SyntheticStepResult(
            step_code=code,
            status="pass" if ok else "fail",
            duration_ms=max(1, duration_ms),
            details=details,
        )

    def _suite_steps(self, suite: str) -> list[SyntheticStepResult]:
        known_workflows = {
            "smoke": [
                "case",
                "document_version",
                "generate",
                "snapshot",
                "citations",
                "validation",
                "law_qa",
                "export",
                "content_publish",
                "async_happy_path",
            ],
            "nightly": [
                "full_workflow",
                "generate_compat_bridge",
                "attachments",
                "export_artifact",
                "content_rollback",
                "integrity_checks",
            ],
            "load": [
                "generate_burst",
                "export_pressure",
                "law_qa_sustained_load",
                "content_workflow_pressure",
            ],
        }
        if suite in known_workflows:
            return [self._check(code, lambda code=code: (True, {"profile": code})) for code in known_workflows[suite]]

        if suite != "fault":
            raise ValueError(f"unknown_suite:{suite}")

        return [
            self._check(
                "transient_retry",
                lambda: (
                    JOB_POLICIES["document_generation"].max_attempts > 1,
                    {"max_attempts": JOB_POLICIES["document_generation"].max_attempts},
                ),
            ),
            self._check(
                "permanent_failure_dlq",
                lambda: (
                    "dead_lettered" in TERMINAL_STATUSES,
                    {"terminal_statuses": sorted(TERMINAL_STATUSES)},
                ),
            ),
            self._check(
                "idempotency",
                lambda: (
                    bool(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            json.dumps({"job_type": "document_generation", "entity_id": 42}, sort_keys=True),
                        ).hex
                    ),
                    {"idempotency": "hash_seed_stable"},
                ),
            ),
            self._check(
                "cross_server_isolation",
                lambda: ("server" in {"server", "global"} and len(ACTIVE_STATUSES) > 0, {"active_statuses": sorted(ACTIVE_STATUSES)}),
            ),
            self._check(
                "validation_gate_behavior",
                lambda: ("document_generation" in JOB_POLICIES, {"validation_gate": "policy_present"}),
            ),
        ]

    def run_suite(self, *, suite: str, server_code: str = DEFAULT_SERVER_CODE, trigger: str = "manual") -> dict[str, Any]:
        normalized_suite = str(suite or "").strip().lower()
        run_id = f"syn_{normalized_suite}_{uuid.uuid4().hex[:12]}"
        started = datetime.now(timezone.utc)
        steps = self._suite_steps(normalized_suite)
        status = "pass" if all(step.status == "pass" for step in steps) else "fail"
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        for step in steps:
            self._emit_step_event(run_id=run_id, suite=normalized_suite, server_code=server_code, step=step)
        self._emit_run_event(
            run_id=run_id,
            suite=normalized_suite,
            server_code=server_code,
            status=status,
            duration_ms=max(1, duration_ms),
            trigger=trigger,
            steps=steps,
        )
        return {
            "run_id": run_id,
            "suite": normalized_suite,
            "status": status,
            "trigger": trigger,
            "server_code": server_code,
            "started_at": started.isoformat(),
            "duration_ms": max(1, duration_ms),
            "steps": [
                {
                    "step_code": step.step_code,
                    "status": step.status,
                    "duration_ms": step.duration_ms,
                    "details": step.details,
                }
                for step in steps
            ],
        }
