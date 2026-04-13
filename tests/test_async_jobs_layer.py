from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.exam_import_tasks import execute_transitional_runner
from ogp_web.workers.job_worker import JobWorker


@dataclass
class _Policy:
    max_attempts: int


class InMemoryJobService:
    def __init__(self):
        self.backend = None
        self.jobs: dict[int, dict[str, Any]] = {}
        self.attempts: dict[int, list[dict[str, Any]]] = {}
        self.dead_letters: list[int] = []
        self._seq = 1

    def create_job(self, *, job_type: str, payload_json: dict[str, Any], idempotency_key: str | None = None, server_id: str | None = "srv", **kwargs):
        if idempotency_key:
            for job in self.jobs.values():
                if job.get("idempotency_key") == idempotency_key and job.get("payload_json") == payload_json:
                    return dict(job)
        job = {
            "id": self._seq,
            "job_type": job_type,
            "payload_json": payload_json,
            "status": "queued",
            "attempt_count": 0,
            "max_attempts": 2,
            "server_scope": "server" if server_id else "global",
            "server_id": server_id,
            "idempotency_key": idempotency_key,
            "result_json": {},
        }
        self.jobs[self._seq] = job
        self.attempts[self._seq] = []
        self._seq += 1
        return dict(job)

    def claim_available_jobs(self, *, worker_id: str, server_id: str | None, limit: int = 10):
        items = []
        for job in self.jobs.values():
            if job["status"] not in {"queued", "pending", "failed"}:
                continue
            if job["server_scope"] == "server" and job["server_id"] != server_id:
                continue
            job["status"] = "processing"
            self.attempts[job["id"]].append({"attempt_number": len(self.attempts[job["id"]]) + 1, "status": "started"})
            items.append(dict(job))
            if len(items) >= limit:
                break
        return items

    def mark_succeeded(self, *, job_id: int, worker_id: str, result_json: dict[str, Any]):
        job = self.jobs[job_id]
        job["status"] = "succeeded"
        job["attempt_count"] += 1
        job["result_json"] = result_json
        self.attempts[job_id][-1]["status"] = "succeeded"
        return dict(job)

    def mark_failed(self, *, job_id: int, worker_id: str, error_code: str, error_message: str, error_details: dict[str, Any] | None = None):
        job = self.jobs[job_id]
        job["attempt_count"] += 1
        self.attempts[job_id][-1]["status"] = "failed"
        if job["attempt_count"] >= job["max_attempts"]:
            job["status"] = "dead_lettered"
            self.dead_letters.append(job_id)
        else:
            job["status"] = "queued"
        job["last_error_code"] = error_code
        job["last_error_message"] = error_message
        return dict(job)


def test_execute_transitional_runner_supports_progress_callback():
    def _runner(progress_callback):
        progress_callback({"progress": 50})
        return {"ok": True}

    progress = []
    result = execute_transitional_runner(_runner, progress_callback=lambda item: progress.append(item))
    assert result["ok"] is True
    assert progress == [{"progress": 50}]


def test_async_job_happy_path_and_idempotency():
    service = InMemoryJobService()
    first = service.create_job(job_type="content_import", payload_json={"source": "sheet"}, idempotency_key="same")
    second = service.create_job(job_type="content_import", payload_json={"source": "sheet"}, idempotency_key="same")
    assert first["id"] == second["id"]

    worker = JobWorker(
        service=service,
        server_id="srv",
        handlers={"content_import": lambda _job: {"imported": True}},
    )
    processed = worker.run_once()
    assert processed[0]["status"] == "succeeded"
    assert service.jobs[first["id"]]["result_json"] == {"imported": True}


def test_retry_and_dead_letter_flow():
    service = InMemoryJobService()
    job = service.create_job(job_type="document_export", payload_json={"version_id": 1}, idempotency_key="exp")

    worker = JobWorker(
        service=service,
        server_id="srv",
        handlers={"document_export": lambda _job: (_ for _ in ()).throw(RuntimeError("boom"))},
    )
    first = worker.run_once()[0]
    second = worker.run_once()[0]

    assert first["status"] == "queued"
    assert second["status"] == "dead_lettered"
    assert job["id"] in service.dead_letters
    assert [item["status"] for item in service.attempts[job["id"]]] == ["failed", "failed"]


def test_cross_server_isolation_during_claim():
    service = InMemoryJobService()
    service.create_job(job_type="content_reindex", payload_json={}, server_id="a")
    service.create_job(job_type="content_reindex", payload_json={}, server_id="b")

    worker_a = JobWorker(service=service, server_id="a", handlers={"content_reindex": lambda _job: {"ok": True}})
    processed_a = worker_a.run_once()
    assert len(processed_a) == 1
    assert processed_a[0]["server_id"] == "a"

    remaining = [job for job in service.jobs.values() if job["status"] == "queued"]
    assert len(remaining) == 1
    assert remaining[0]["server_id"] == "b"
