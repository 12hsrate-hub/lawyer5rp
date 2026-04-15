from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, status

from ogp_web.services.auth_service import AuthUser
from ogp_web.services.feature_flags import FlagDecision
from ogp_web.services.regression_metrics import (
    build_rollout_labels,
    record_async_queue_lag,
    record_validation_fail_rate,
)
from ogp_web.services.generation_orchestrator import GenerationOrchestrator
from ogp_web.services.server_context_service import (
    resolve_user_server_complaint_settings,
    resolve_user_server_identity,
)
from ogp_web.services.validation_service import ValidationService
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.user_store import UserStore
from ogp_web.storage.validation_repository import ValidationRepository

LOGGER = logging.getLogger(__name__)


class SuggestConcurrencyLimiter:
    def __init__(self, *, max_concurrency: int, retry_after_seconds: int = 3) -> None:
        self.max_concurrency = max(1, int(max_concurrency or 1))
        self.retry_after_seconds = max(1, int(retry_after_seconds or 1))
        self._semaphore = BoundedSemaphore(self.max_concurrency)
        self._lock = Lock()
        self._inflight = 0

    def try_acquire(self) -> bool:
        if not self._semaphore.acquire(blocking=False):
            return False
        with self._lock:
            self._inflight += 1
        return True

    def release(self) -> None:
        with self._lock:
            if self._inflight <= 0:
                return
            self._inflight -= 1
        self._semaphore.release()

    @property
    def inflight(self) -> int:
        with self._lock:
            return self._inflight


def env_positive_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def build_heavy_ai_executor() -> ThreadPoolExecutor | None:
    max_workers = env_positive_int("OGP_AI_HEAVY_MAX_WORKERS", 0)
    if max_workers <= 0:
        return None
    return ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ogp-ai-heavy")


class ComplaintRuntimeService:
    def __init__(
        self,
        *,
        suggest_concurrency_limiter: SuggestConcurrencyLimiter,
        heavy_ai_executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self.suggest_concurrency_limiter = suggest_concurrency_limiter
        self.heavy_ai_executor = heavy_ai_executor

    def build_validation_service(self, store: UserStore) -> ValidationService:
        return ValidationService(ValidationRepository(store.backend))

    def law_qa_selected_norms_to_citations(
        self,
        *,
        store: UserStore,
        server_id: str,
        law_version_id: int | None,
        selected_norms: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if law_version_id is None:
            return []
        citations: list[dict[str, object]] = []
        for norm in selected_norms:
            source_url = str(norm.get("source_url") or "").strip()
            document_title = str(norm.get("document_title") or "").strip()
            article_label = str(norm.get("article_label") or "").strip()
            excerpt = str(norm.get("excerpt") or norm.get("excerpt_preview") or "").strip()
            if not source_url or not document_title or not article_label:
                continue
            source = store.resolve_law_article_source(
                server_id=server_id,
                law_version_id=law_version_id,
                article_label=article_label,
                document_title=document_title,
                source_url=source_url,
            )
            if source is None:
                continue
            citations.append(
                {
                    "citation_type": "norm",
                    "source_type": "law_article",
                    "source_id": int(source["source_id"]),
                    "source_version_id": int(source["source_version_id"]),
                    "canonical_ref": f"{document_title} {article_label}",
                    "quoted_text": excerpt,
                    "usage_type": "supporting",
                }
            )
        return citations

    def resolve_law_qa_response_warnings(
        self,
        *,
        warnings: list[str],
        citations_flag: FlagDecision,
        raw_citations: list[dict[str, object]],
    ) -> list[str]:
        response_warnings = list(warnings or [])
        if citations_flag.use_new_flow and not raw_citations:
            if citations_flag.enforcement.value == "hard":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=["citations_required policy blocked the response due to missing citations."],
                )
            response_warnings.append("citations_required_warn:missing_citations")
        return response_warnings

    def persist_law_qa_artifacts(
        self,
        *,
        store: UserStore,
        user: AuthUser,
        effective_server_code: str,
        question: str,
        law_version_id: int | None,
        answer_text: str,
        used_sources: list[str],
        raw_citations: list[dict[str, object]],
        retrieval_runner: Callable[..., Any],
        citation_saver: Callable[..., list[dict[str, object]]],
    ) -> tuple[Any, int, list[dict[str, object]]]:
        retrieval = retrieval_runner(
            store=store,
            actor_username=user.username,
            server_id=effective_server_code,
            run_type="law_qa",
            query_text=question,
            effective_versions={"law_version_id": law_version_id},
            retrieved_sources=[{"url": item} for item in (used_sources or [])],
            candidates=raw_citations,
            policy_status="pass" if raw_citations else "blocked_missing_citations",
        )
        actor_id = store.get_user_id(user.username)
        if actor_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Пользователь не найден."])
        law_qa_run_id = store.create_law_qa_run(
            server_id=effective_server_code,
            user_id=int(actor_id),
            question=question,
            answer_text=answer_text,
            retrieval_run_id=retrieval.retrieval_run_id,
            snapshot_id=str(law_version_id or ""),
        )
        citations = (
            citation_saver(
                store=store,
                server_id=effective_server_code,
                law_qa_run_id=law_qa_run_id,
                retrieval_run_id=retrieval.retrieval_run_id,
                citations=raw_citations,
            )
            if raw_citations
            else []
        )
        return retrieval, int(law_qa_run_id), citations

    def maybe_validate_law_qa_result(
        self,
        *,
        store: UserStore,
        metrics_store: AdminMetricsStore,
        user: AuthUser,
        effective_server_code: str,
        question: str,
        result: Any,
        validation_flag: FlagDecision,
        path: str = "/api/ai/law-qa-test",
    ) -> None:
        try:
            validation_repo = ValidationRepository(store.backend)
            conn = store.backend.connect()
            user_row = conn.execute("SELECT id FROM users WHERE username = %s", (user.username,)).fetchone()
            conn.close()
            if user_row is not None:
                qa_run = validation_repo.create_law_qa_run(
                    server_id=effective_server_code,
                    user_id=int(user_row["id"]),
                    question=question,
                    answer_text=result.text,
                    used_sources=list(getattr(result, "used_sources", []) or []),
                    selected_norms=list(getattr(result, "selected_norms", []) or []),
                    metadata={"generation_id": result.generation_id, "legacy_endpoint": path},
                )
                if validation_flag.use_new_flow:
                    validation_result = ValidationService(validation_repo).run_validation(
                        target_type="law_qa_run",
                        target_id=int(qa_run["id"]),
                    )
                    record_validation_fail_rate(
                        metrics_store,
                        username=user.username,
                        path=path,
                        method="POST",
                        labels=build_rollout_labels(
                            flag="validation_gate_v1",
                            rollout_mode=validation_flag.mode.value,
                            cohort=validation_flag.cohort.value,
                            server_id=effective_server_code,
                            flow_type="law_qa",
                            status="fail" if validation_result.run.get("status") == "fail" else "success",
                        ),
                        failed=validation_result.run.get("status") == "fail",
                    )
        except Exception:
            if str(os.getenv("OGP_VALIDATION_LAW_QA_STRICT", "0") or "").strip() in {"1", "true", "yes", "on"}:
                raise

    def persist_generation_result(
        self,
        *,
        store: UserStore,
        user: AuthUser,
        document_kind: str,
        payload: dict[str, Any],
        result_text: str,
        context_snapshot: dict[str, object],
    ) -> Any:
        return GenerationOrchestrator(store).write_generation_bridge(
            username=user.username,
            server_code=user.server_code,
            document_kind=document_kind,
            payload=payload,
            result_text=result_text,
            context_snapshot=context_snapshot,
            legacy_generated_document_id=None,
        )

    def maybe_validate_generated_document(
        self,
        *,
        store: UserStore,
        metrics_store: AdminMetricsStore,
        user: AuthUser,
        path: str,
        validation_flag: FlagDecision,
        bridge_result: Any,
        flow_type: str = "generate",
    ) -> None:
        if bridge_result is None:
            return
        try:
            if validation_flag.use_new_flow:
                result = self.build_validation_service(store).run_validation(
                    target_type="document_version",
                    target_id=int(bridge_result.document_version_id),
                )
                record_validation_fail_rate(
                    metrics_store,
                    username=user.username,
                    path=path,
                    method="POST",
                    labels=build_rollout_labels(
                        flag="validation_gate_v1",
                        rollout_mode=validation_flag.mode.value,
                        cohort=validation_flag.cohort.value,
                        server_id=user.server_code,
                        flow_type=flow_type,
                        status="fail" if result.run.get("status") == "fail" else "success",
                    ),
                    failed=result.run.get("status") == "fail",
                )
        except Exception:
            if str(os.getenv("OGP_VALIDATION_GENERATION_STRICT", "0") or "").strip() in {"1", "true", "yes", "on"}:
                raise

    def with_shadow_citations_policy(self, context_snapshot: dict[str, object]) -> dict[str, object]:
        snapshot = dict(context_snapshot)
        snapshot["citations_policy_gate"] = {"mode": "shadow", "status": "flagged_no_citations"}
        return snapshot

    def build_complaint_generation_context_snapshot(
        self,
        *,
        store: UserStore,
        user: AuthUser,
        adapter_flag: FlagDecision,
        legacy_snapshot_builder: Callable[[], dict[str, object]],
        adapter_supported: Callable[[str, str], bool],
        adapter_snapshot_resolver: Callable[[UserStore, AuthUser], Any],
    ) -> dict[str, object]:
        if adapter_supported(user.server_code, "complaint") and adapter_flag.use_new_flow:
            return adapter_snapshot_resolver(store, user).to_generation_context_snapshot()
        return dict(legacy_snapshot_builder())

    def validate_server_payload(
        self,
        store: UserStore,
        user: AuthUser,
        *,
        org: str = "",
        complaint_basis: str = "",
    ) -> None:
        complaint_settings = resolve_user_server_complaint_settings(store, user.username, server_code=user.server_code)
        server_identity = resolve_user_server_identity(store, user.username, server_code=user.server_code)
        normalized_org = str(org or "").strip()
        normalized_basis = str(complaint_basis or "").strip()
        if normalized_org and complaint_settings.organizations and normalized_org not in complaint_settings.organizations:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=[f"Организация {normalized_org!r} не относится к серверу {server_identity.name}."],
            )
        allowed_bases = set(complaint_settings.complaint_basis_codes)
        if normalized_basis and allowed_bases and normalized_basis not in allowed_bases:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=[f"Основание жалобы {normalized_basis!r} не поддерживается для сервера {server_identity.name}."],
            )

    def ensure_suggest_capacity(
        self,
        *,
        metrics_store: AdminMetricsStore,
        user: AuthUser,
        complaint_basis: str,
        main_focus: str,
    ) -> None:
        acquired = self.suggest_concurrency_limiter.try_acquire()
        if acquired:
            return
        retry_after = str(self.suggest_concurrency_limiter.retry_after_seconds)
        metrics_store.log_event(
            event_type="ai_suggest_overload",
            username=user.username,
            server_code=user.server_code,
            path="/api/ai/suggest",
            method="POST",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            meta={
                "server_code": user.server_code,
                "complaint_basis": complaint_basis,
                "main_focus": main_focus,
                "retry_after_seconds": self.suggest_concurrency_limiter.retry_after_seconds,
                "inflight": self.suggest_concurrency_limiter.inflight,
                "max_concurrency": self.suggest_concurrency_limiter.max_concurrency,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=["Сервис AI suggest временно перегружен. Повторите попытку через несколько секунд."],
            headers={"Retry-After": retry_after},
        )

    async def run_ai_task(
        self,
        *,
        metrics_store: AdminMetricsStore,
        user: AuthUser,
        path: str,
        operation: str,
        func: Callable[..., Any],
        use_heavy_executor: bool = False,
        threadpool_runner: Callable[..., Awaitable[Any]],
        **kwargs: Any,
    ) -> Any:
        enqueued_at = monotonic()
        executor = self.heavy_ai_executor if use_heavy_executor else None
        queue_size = -1
        if executor is not None:
            queue = getattr(executor, "_work_queue", None)
            if queue is not None and hasattr(queue, "qsize"):
                try:
                    queue_size = int(queue.qsize())
                except Exception:
                    queue_size = -1

        def _invoke() -> tuple[object, float, float]:
            started_at = monotonic()
            wait_ms = (started_at - enqueued_at) * 1000.0
            result = func(**kwargs)
            finished_at = monotonic()
            run_ms = (finished_at - started_at) * 1000.0
            return result, wait_ms, run_ms

        loop = asyncio.get_running_loop()
        if executor is None:
            started_at = monotonic()
            result = await threadpool_runner(func, **kwargs)
            finished_at = monotonic()
            wait_ms = 0.0
            run_ms = (finished_at - started_at) * 1000.0
        else:
            result, wait_ms, run_ms = await loop.run_in_executor(executor, _invoke)

        metrics_store.log_event(
            event_type="threadpool_wait",
            username=user.username,
            server_code=user.server_code,
            path=path,
            method="POST",
            status_code=200,
            meta={
                "server_code": user.server_code,
                "operation": operation,
                "executor": "ai_heavy" if executor is not None else "default",
                "queue_size": queue_size,
                "wait_ms": round(wait_ms, 2),
                "run_ms": round(run_ms, 2),
            },
        )
        record_async_queue_lag(
            metrics_store,
            username=user.username,
            path=path,
            method="POST",
            labels=build_rollout_labels(
                flag="async_jobs_v1",
                rollout_mode="all" if executor is not None else "off",
                cohort="default",
                server_id=user.server_code,
                flow_type=operation,
                status="success",
            ),
            lag_ms=int(wait_ms),
        )
        return result
