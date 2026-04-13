from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import HTTPException, status


@dataclass(frozen=True)
class CitationItem:
    citation_type: str
    source_type: str
    source_id: int
    source_version_id: int
    canonical_ref: str
    quoted_text: str
    usage_type: str


def _normalize_citation(raw: dict[str, Any]) -> CitationItem:
    source_type = str(raw.get("source_type") or "").strip().lower()
    citation_type = str(raw.get("citation_type") or "norm").strip().lower() or "norm"
    usage_type = str(raw.get("usage_type") or "supporting").strip().lower() or "supporting"
    canonical_ref = str(raw.get("canonical_ref") or "").strip()
    quoted_text = str(raw.get("quoted_text") or "").strip()
    source_id = int(raw.get("source_id") or 0)
    source_version_id = int(raw.get("source_version_id") or 0)
    if not source_type or source_id <= 0 or source_version_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=["Citation must include a valid versioned source linkage."],
        )
    if not canonical_ref:
        canonical_ref = f"{source_type}:{source_id}@v{source_version_id}"
    return CitationItem(
        citation_type=citation_type,
        source_type=source_type,
        source_id=source_id,
        source_version_id=source_version_id,
        canonical_ref=canonical_ref,
        quoted_text=quoted_text,
        usage_type=usage_type,
    )


def _dedupe_citations(citations: Iterable[CitationItem]) -> tuple[CitationItem, ...]:
    seen: set[tuple[str, int, int, str, str]] = set()
    unique: list[CitationItem] = []
    for item in citations:
        key = (
            item.source_type,
            item.source_id,
            item.source_version_id,
            item.canonical_ref,
            item.usage_type,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def _validate_server_scope(store, *, server_id: str, citation: CitationItem) -> None:
    if not store.validate_citation_source_scope(
        server_id=server_id,
        source_type=citation.source_type,
        source_id=citation.source_id,
        source_version_id=citation.source_version_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=["Citation source/version is invalid for the current server scope."],
        )


def save_document_version_citations(
    *,
    store,
    server_id: str,
    document_version_id: int,
    retrieval_run_id: int,
    citations: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized = _dedupe_citations(_normalize_citation(item) for item in citations)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=["Citations are required."])
    created_ids: list[int] = []
    for item in normalized:
        _validate_server_scope(store, server_id=server_id, citation=item)
        created_ids.append(
            store.create_document_version_citation(
                server_id=server_id,
                document_version_id=document_version_id,
                retrieval_run_id=retrieval_run_id,
                citation_type=item.citation_type,
                source_type=item.source_type,
                source_id=item.source_id,
                source_version_id=item.source_version_id,
                canonical_ref=item.canonical_ref,
                quoted_text=item.quoted_text,
                usage_type=item.usage_type,
            )
        )
    return store.get_document_version_citations(document_version_id=document_version_id, server_id=server_id)


def save_answer_citations(
    *,
    store,
    server_id: str,
    law_qa_run_id: int,
    retrieval_run_id: int,
    citations: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized = _dedupe_citations(_normalize_citation(item) for item in citations)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=["Citations are required."])
    for item in normalized:
        _validate_server_scope(store, server_id=server_id, citation=item)
        store.create_answer_citation(
            server_id=server_id,
            law_qa_run_id=law_qa_run_id,
            retrieval_run_id=retrieval_run_id,
            citation_type=item.citation_type,
            source_type=item.source_type,
            source_id=item.source_id,
            source_version_id=item.source_version_id,
            canonical_ref=item.canonical_ref,
            quoted_text=item.quoted_text,
            usage_type=item.usage_type,
        )
    return store.get_law_qa_run_citations(law_qa_run_id=law_qa_run_id, server_id=server_id)
