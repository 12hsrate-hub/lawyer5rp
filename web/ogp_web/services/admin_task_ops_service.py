from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException, status

from ogp_web.schemas import AdminBulkActionPayload
from ogp_web.services.admin_user_mutations_service import execute_bulk_user_mutation_action
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.job_status_service import enrich_job_status
from ogp_web.services.law_rebuild_tasks import find_active_law_rebuild_task
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.user_store import UserStore

DEFAULT_ADMIN_TASKS_PATH = Path(__file__).resolve().parents[3] / "web" / "data" / "admin_tasks.json"


class AdminTaskOpsService:
    def __init__(
        self,
        *,
        tasks_path: Path | None = None,
        bulk_action_executor: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self._tasks_path = tasks_path or DEFAULT_ADMIN_TASKS_PATH
        self._bulk_action_executor = bulk_action_executor or execute_bulk_user_mutation_action
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._loaded = False

    def _ensure_loaded(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._load_tasks_from_disk_unlocked()
            self._loaded = True

    def _save_tasks_to_disk_unlocked(self) -> None:
        try:
            self._tasks_path.parent.mkdir(parents=True, exist_ok=True)
            self._tasks_path.write_text(
                json.dumps(self._tasks, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load_tasks_from_disk_unlocked(self) -> None:
        try:
            raw = self._tasks_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except Exception:
            return
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return
        if isinstance(parsed, dict):
            self._tasks.clear()
            for key, value in parsed.items():
                if isinstance(value, dict):
                    self._tasks[str(key)] = value

    def put_task(self, task: dict[str, Any]) -> None:
        with self._lock:
            self._ensure_loaded()
            self._tasks[str(task["task_id"])] = deepcopy(task)
            self._save_tasks_to_disk_unlocked()

    def patch_task(self, task_id: str, **changes: Any) -> None:
        with self._lock:
            self._ensure_loaded()
            current = self._tasks.get(task_id)
            if not current:
                return
            current.update(changes)
            self._tasks[task_id] = current
            self._save_tasks_to_disk_unlocked()

    def load_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._ensure_loaded()
            item = self._tasks.get(task_id)
            return deepcopy(item) if isinstance(item, dict) else None

    def load_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            self._ensure_loaded()
            return [deepcopy(item) for item in self._tasks.values() if isinstance(item, dict)]

    def claim_law_rebuild_task(self, *, server_code: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        with self._lock:
            self._ensure_loaded()
            active_task = find_active_law_rebuild_task(tasks=self._tasks, server_code=server_code)
            if active_task:
                return deepcopy(active_task), None
            task = {
                "task_id": f"law-rebuild-{uuid.uuid4().hex}",
                "scope": "law_sources_rebuild",
                "server_code": server_code,
                "status": "queued",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "started_at": "",
                "finished_at": "",
                "progress": {"done": 0, "total": 1},
                "result": None,
                "error": "",
            }
            self._tasks[str(task["task_id"])] = deepcopy(task)
            self._save_tasks_to_disk_unlocked()
            return None, deepcopy(task)

    def execute_bulk_action(
        self,
        *,
        payload: AdminBulkActionPayload,
        user: AuthUser,
        metrics_store: AdminMetricsStore,
        user_store: UserStore,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        progress_callback = None
        if task_id:
            progress_callback = lambda done, total: self.patch_task(  # noqa: E731
                task_id,
                progress={"done": done, "total": total},
            )
        return self._bulk_action_executor(
            payload=payload,
            user=user,
            metrics_store=metrics_store,
            user_store=user_store,
            progress_callback=progress_callback,
        )

    def start_bulk_action_task(
        self,
        *,
        payload: AdminBulkActionPayload,
        user: AuthUser,
        metrics_store: AdminMetricsStore,
        user_store: UserStore,
    ) -> dict[str, Any]:
        task_id = f"admin-bulk-{uuid.uuid4().hex}"
        created_at = datetime.now(timezone.utc).isoformat()
        self.put_task(
            {
                "task_id": task_id,
                "scope": "bulk_user_mutation",
                "server_code": user.server_code,
                "status": "queued",
                "created_at": created_at,
                "started_at": "",
                "finished_at": "",
                "progress": {"done": 0, "total": len(payload.usernames)},
                "result": None,
                "error": "",
            }
        )

        def _runner() -> None:
            self.patch_task(task_id, status="running", started_at=datetime.now(timezone.utc).isoformat())
            try:
                result = self.execute_bulk_action(
                    payload=payload,
                    user=user,
                    metrics_store=metrics_store,
                    user_store=user_store,
                    task_id=task_id,
                )
                self.patch_task(
                    task_id,
                    status="finished",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    result=result,
                )
            except Exception as exc:  # noqa: BLE001
                self.patch_task(
                    task_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    error=str(exc),
                )

        threading.Thread(target=_runner, daemon=True).start()
        return {"ok": True, "task_id": task_id, "status": "queued"}

    def start_law_sources_rebuild_task(
        self,
        *,
        server_code: str,
        user: AuthUser,
        metrics_store: AdminMetricsStore,
        rebuild_callback: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        active_task, queued_task = self.claim_law_rebuild_task(server_code=server_code)
        if active_task:
            metrics_store.log_event(
                event_type="admin_law_sources_rebuild_async_conflict",
                username=user.username,
                server_code=server_code,
                path="/api/admin/law-sources/rebuild-async",
                method="POST",
                status_code=409,
                meta={"active_task_id": active_task.get("task_id"), "active_status": active_task.get("status")},
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=[f"law_rebuild_already_in_progress:{active_task.get('task_id')}"],
            )
        assert queued_task is not None
        task_id = str(queued_task["task_id"])

        def _runner() -> None:
            self.patch_task(task_id, status="running", started_at=datetime.now(timezone.utc).isoformat())
            try:
                result = rebuild_callback()
                self.patch_task(
                    task_id,
                    status="finished",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    progress={"done": 1, "total": 1},
                    result=result,
                )
                metrics_store.log_event(
                    event_type="admin_law_sources_rebuild_async_finished",
                    username=user.username,
                    server_code=server_code,
                    path="/api/admin/law-sources/rebuild-async",
                    method="POST",
                    status_code=200,
                    meta={"task_id": task_id, "law_version_id": result.get("law_version_id")},
                )
            except Exception as exc:  # noqa: BLE001
                self.patch_task(
                    task_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    error=str(exc),
                )
                metrics_store.log_event(
                    event_type="admin_law_sources_rebuild_async_failed",
                    username=user.username,
                    server_code=server_code,
                    path="/api/admin/law-sources/rebuild-async",
                    method="POST",
                    status_code=500,
                    meta={"task_id": task_id, "error": str(exc)},
                )

        threading.Thread(target=_runner, daemon=True).start()
        metrics_store.log_event(
            event_type="admin_law_sources_rebuild_async_queued",
            username=user.username,
            server_code=server_code,
            path="/api/admin/law-sources/rebuild-async",
            method="POST",
            status_code=200,
            meta={"task_id": task_id},
        )
        return {"ok": True, "task_id": task_id, "status": "queued"}

    def require_task_status_payload(self, *, task_id: str) -> dict[str, Any]:
        task = self.load_task(task_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Задача не найдена."])
        return enrich_job_status(task, subsystem="admin_task")
