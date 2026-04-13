from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from fastapi import HTTPException, status


@dataclass(frozen=True)
class RetrievalCandidate:
    source_type: str
    source_id: int
    source_version_id: int
    canonical_ref: str
    quoted_text: str
    score: int


@dataclass(frozen=True)
class RetrievalResult:
    retrieval_run_id: int
    server_id: str
    run_type: str
    effective_versions: dict[str, Any]
    retrieved_sources: tuple[dict[str, Any], ...]
    candidates: tuple[RetrievalCandidate, ...]
    policy_status: str


def _normalize_server_id(server_id: str) -> str:
    normalized = str(server_id or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["server_id is required."])
    return normalized


def _normalize_run_type(run_type: str) -> str:
    normalized = str(run_type or "").strip().lower()
    if normalized not in {"law_qa", "document_generation"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Unsupported retrieval run_type."])
    return normalized


def _rank_candidates(candidates: Sequence[dict[str, Any]], *, max_candidates: int = 12) -> tuple[RetrievalCandidate, ...]:
    normalized: list[RetrievalCandidate] = []
    for raw in candidates:
        source_type = str(raw.get("source_type") or "").strip().lower()
        if not source_type:
            continue
        try:
            source_id = int(raw.get("source_id") or 0)
            source_version_id = int(raw.get("source_version_id") or 0)
            score = int(raw.get("score") or 0)
        except Exception:
            continue
        if source_id <= 0 or source_version_id <= 0:
            continue
        normalized.append(
            RetrievalCandidate(
                source_type=source_type,
                source_id=source_id,
                source_version_id=source_version_id,
                canonical_ref=str(raw.get("canonical_ref") or "").strip(),
                quoted_text=str(raw.get("quoted_text") or "").strip(),
                score=score,
            )
        )
    normalized.sort(key=lambda item: item.score, reverse=True)
    return tuple(normalized[:max(1, int(max_candidates or 1))])


def run_retrieval(
    *,
    store,
    actor_username: str,
    server_id: str,
    run_type: str,
    query_text: str,
    effective_versions: dict[str, Any],
    retrieved_sources: Sequence[dict[str, Any]],
    candidates: Sequence[dict[str, Any]],
    policy_status: str = "pass",
) -> RetrievalResult:
    normalized_server = _normalize_server_id(server_id)
    normalized_run_type = _normalize_run_type(run_type)
    actor_user_id = store.get_user_id(actor_username)
    if actor_user_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Пользователь не найден."])
    ranked_candidates = _rank_candidates(candidates)
    run_id = store.create_retrieval_run(
        server_id=normalized_server,
        run_type=normalized_run_type,
        actor_user_id=int(actor_user_id),
        query_text=str(query_text or "").strip(),
        effective_versions=effective_versions,
        retrieved_sources=list(retrieved_sources),
        policy_status=str(policy_status or "pending").strip().lower() or "pending",
    )
    return RetrievalResult(
        retrieval_run_id=run_id,
        server_id=normalized_server,
        run_type=normalized_run_type,
        effective_versions=dict(effective_versions or {}),
        retrieved_sources=tuple(dict(item) for item in retrieved_sources),
        candidates=ranked_candidates,
        policy_status=str(policy_status or "pending").strip().lower() or "pending",
    )
