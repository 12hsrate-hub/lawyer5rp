from __future__ import annotations

import logging
import threading
import time
from typing import Any

from ogp_web.providers.queue_provider import QueueProvider
from ogp_web.workers.job_worker import JobWorker


logger = logging.getLogger(__name__)


class JobWorkerPool:
    def __init__(
        self,
        *,
        worker: JobWorker,
        queue_provider: QueueProvider,
        concurrency: int = 2,
        idle_sleep_seconds: float = 1.0,
    ):
        self.worker = worker
        self.queue_provider = queue_provider
        self.concurrency = max(1, int(concurrency))
        self.idle_sleep_seconds = max(0.1, float(idle_sleep_seconds))
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._threads:
            return
        for index in range(self.concurrency):
            thread = threading.Thread(target=self._run_forever, name=f"job-worker-{index+1}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads = []

    def _run_forever(self) -> None:
        while not self._stop.is_set():
            message = self.queue_provider.blocking_pop(timeout_seconds=3)
            if message is None:
                time.sleep(self.idle_sleep_seconds)
                continue
            job = self.worker.service.claim_job_by_id(
                job_id=message.job_id,
                worker_id=self.worker.worker_id,
                server_id=self.worker.server_id,
            )
            if job is None:
                continue
            try:
                self.worker._process_job(job)
            except Exception:  # noqa: BLE001
                logger.exception("Worker pool failed processing job_id=%s", message.job_id)
