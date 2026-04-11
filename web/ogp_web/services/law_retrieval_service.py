from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ogp_web.server_config import DEFAULT_SERVER_CODE
from ogp_web.services.law_bundle_service import LawChunk


@dataclass(frozen=True)
class LawRetrievalMatch:
    chunk: LawChunk
    score: int
    excerpt: str


@dataclass(frozen=True)
class LawRetrievalResult:
    server_code: str
    server_name: str
    query: str
    confidence: str
    is_configured: bool
    bundle_path: str
    configured_sources: tuple[str, ...]
    indexed_chunk_count: int
    matches: tuple[LawRetrievalMatch, ...]


GetServerConfig = Callable[[str], Any]
LoadLawBundleChunks = Callable[[str, str], tuple[LawChunk, ...] | list[LawChunk]]
BuildLawChunkIndex = Callable[[tuple[str, ...]], tuple[LawChunk, ...] | list[LawChunk]]
SelectLawChunks = Callable[[list[LawChunk], str], tuple[list[LawChunk], str]]
ScoreLawChunk = Callable[[LawChunk, str], int]
ExtractExcerpt = Callable[..., str]


def retrieve_law_context(
    *,
    server_code: str,
    query: str,
    excerpt_chars: int,
    get_server_config_func: GetServerConfig,
    load_law_bundle_chunks_func: LoadLawBundleChunks,
    build_law_chunk_index_func: BuildLawChunkIndex,
    select_chunks_func: SelectLawChunks,
    score_chunk_func: ScoreLawChunk,
    extract_excerpt_func: ExtractExcerpt,
    default_server_code: str = DEFAULT_SERVER_CODE,
) -> LawRetrievalResult:
    normalized_server_code = str(server_code or default_server_code).strip() or default_server_code
    retrieval_query = str(query or "").strip()
    server_config = get_server_config_func(normalized_server_code)
    configured_sources = tuple(
        str(item or "").strip() for item in getattr(server_config, "law_qa_sources", ()) if str(item or "").strip()
    )
    bundle_path = str(getattr(server_config, "law_qa_bundle_path", "") or "").strip()

    chunks = list(load_law_bundle_chunks_func(normalized_server_code, bundle_path)) if bundle_path else []
    if not chunks and configured_sources:
        chunks = list(build_law_chunk_index_func(configured_sources))

    selected: list[LawChunk] = []
    confidence = "low"
    if retrieval_query and chunks:
        selected, confidence = select_chunks_func(chunks, retrieval_query)

    matches = tuple(
        LawRetrievalMatch(
            chunk=item,
            score=score_chunk_func(item, retrieval_query),
            excerpt=extract_excerpt_func(item.text, retrieval_query, max_chars=excerpt_chars),
        )
        for item in selected
    )

    return LawRetrievalResult(
        server_code=str(getattr(server_config, "code", normalized_server_code) or normalized_server_code),
        server_name=str(getattr(server_config, "name", normalized_server_code) or normalized_server_code),
        query=retrieval_query,
        confidence=confidence,
        is_configured=bool(bundle_path or configured_sources),
        bundle_path=bundle_path,
        configured_sources=configured_sources,
        indexed_chunk_count=len(chunks),
        matches=matches,
    )


def unique_sources(result: LawRetrievalResult) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.chunk.url for match in result.matches if match.chunk.url))

