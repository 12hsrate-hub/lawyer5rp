from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any

from ogp_web.server_config import DEFAULT_SERVER_CODE
from ogp_web.services.law_bundle_service import LawChunk, load_law_bundle_meta
from ogp_web.services.legal_pipeline_service import BundleHealth, build_bundle_health
from ogp_web.services.server_context_service import extract_server_identity_settings, extract_server_law_context_settings


@dataclass(frozen=True)
class LawRetrievalMatch:
    chunk: LawChunk
    score: int
    excerpt: str


@dataclass(frozen=True)
class LawRetrievalResult:
    server_code: str
    server_name: str
    profile: str
    query: str
    confidence: str
    is_configured: bool
    bundle_path: str
    law_version_id: int | None
    configured_sources: tuple[str, ...]
    indexed_chunk_count: int
    bundle_health: BundleHealth
    prefilter_count: int
    rerank_candidate_count: int
    rerank_ms: int
    matches: tuple[LawRetrievalMatch, ...]


GetServerConfig = Callable[[str], Any]
LoadLawBundleChunks = Callable[[str, str], tuple[LawChunk, ...] | list[LawChunk]]
BuildLawChunkIndex = Callable[[tuple[str, ...]], tuple[LawChunk, ...] | list[LawChunk]]
SelectLawChunks = Callable[..., tuple[list[LawChunk], str]]
ScoreLawChunk = Callable[[LawChunk, str], int]
ExtractExcerpt = Callable[..., str]


def retrieve_law_context(
    *,
    server_code: str,
    query: str,
    excerpt_chars: int,
    profile: str = "law_qa",
    get_server_config_func: GetServerConfig,
    load_law_bundle_chunks_func: LoadLawBundleChunks,
    build_law_chunk_index_func: BuildLawChunkIndex,
    select_chunks_func: SelectLawChunks,
    score_chunk_func: ScoreLawChunk,
    extract_excerpt_func: ExtractExcerpt,
    default_server_code: str = DEFAULT_SERVER_CODE,
    law_version_id: int | None = None,
) -> LawRetrievalResult:
    normalized_server_code = str(server_code or default_server_code).strip() or default_server_code
    retrieval_query = str(query or "").strip()
    server_config = get_server_config_func(normalized_server_code)
    server_identity = extract_server_identity_settings(server_config, fallback_server_code=normalized_server_code)
    law_context = extract_server_law_context_settings(server_config)
    configured_sources = law_context.source_urls
    bundle_path = law_context.bundle_path
    bundle_max_age_hours = law_context.bundle_max_age_hours
    bundle_meta = load_law_bundle_meta(normalized_server_code, bundle_path, requested_version_id=law_version_id)

    chunks: list[LawChunk] = []
    if bundle_path:
        try:
            chunks = list(load_law_bundle_chunks_func(normalized_server_code, bundle_path, law_version_id))
        except TypeError:
            chunks = list(load_law_bundle_chunks_func(normalized_server_code, bundle_path))
    if not chunks and configured_sources:
        chunks = list(build_law_chunk_index_func(configured_sources))

    selected: list[LawChunk] = []
    confidence = "low"
    prefilter_count = 0
    rerank_candidate_count = 0
    rerank_ms = 0
    if retrieval_query and chunks:
        try:
            selected, confidence = select_chunks_func(chunks, retrieval_query, profile)
        except TypeError:
            selected, confidence = select_chunks_func(chunks, retrieval_query)
        prefilter_count = len(selected)

    rerank_candidates = selected[: _profile_rerank_candidate_count(profile, confidence)]
    rerank_candidate_count = len(rerank_candidates)
    rerank_started_at = monotonic()
    matches = tuple(
        LawRetrievalMatch(
            chunk=item,
            score=score_chunk_func(item, retrieval_query),
            excerpt=extract_excerpt_func(item.text, retrieval_query, max_chars=excerpt_chars),
        )
        for item in rerank_candidates
    )
    rerank_ms = int((monotonic() - rerank_started_at) * 1000) if rerank_candidates else 0
    matches = _rerank_matches(matches, retrieval_query, profile)
    matches = matches[: _profile_target_count(profile, confidence)]
    bundle_health = build_bundle_health(
        generated_at=getattr(bundle_meta, "generated_at_utc", "") if bundle_meta else "",
        source_count=getattr(bundle_meta, "source_count", 0) if bundle_meta else len(configured_sources),
        chunk_count=getattr(bundle_meta, "chunk_count", 0) if bundle_meta else len(chunks),
        fingerprint=getattr(bundle_meta, "fingerprint", "") if bundle_meta else "",
        max_age_hours=bundle_max_age_hours,
    )

    return LawRetrievalResult(
        server_code=server_identity.code,
        server_name=server_identity.name,
        profile=profile,
        query=retrieval_query,
        confidence=confidence,
        is_configured=bool(bundle_path or configured_sources),
        bundle_path=bundle_path,
        law_version_id=getattr(bundle_meta, "law_version_id", None) if bundle_meta else None,
        configured_sources=configured_sources,
        indexed_chunk_count=len(chunks),
        bundle_health=bundle_health,
        prefilter_count=prefilter_count,
        rerank_candidate_count=rerank_candidate_count,
        rerank_ms=rerank_ms,
        matches=matches,
    )


def unique_sources(result: LawRetrievalResult) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.chunk.url for match in result.matches if match.chunk.url))


def _profile_target_count(profile: str, confidence: str) -> int:
    normalized_profile = str(profile or "law_qa").strip().lower()
    normalized_confidence = str(confidence or "low").strip().lower()
    if normalized_profile == "suggest":
        return {"high": 4, "medium": 3, "low": 3}.get(normalized_confidence, 4)
    return {"high": 5, "medium": 6, "low": 7}.get(normalized_confidence, 6)


def _profile_rerank_candidate_count(profile: str, confidence: str) -> int:
    normalized_profile = str(profile or "law_qa").strip().lower()
    normalized_confidence = str(confidence or "low").strip().lower()
    if normalized_profile == "suggest":
        return {"high": 8, "medium": 7, "low": 6}.get(normalized_confidence, 7)
    return {"high": 12, "medium": 14, "low": 16}.get(normalized_confidence, 14)


def _normalize_retrieval_text(text: str) -> str:
    normalized = str(text or "").lower().replace("ё", "е")
    return "".join(ch if ch.isalnum() or ch.isspace() or ch == "." else " " for ch in normalized)


def _query_tokens(query: str) -> tuple[str, ...]:
    tokens = []
    for token in _normalize_retrieval_text(query).split():
        if len(token) >= 3:
            tokens.append(token)
    return tuple(dict.fromkeys(tokens))


def _extract_article_numbers(query: str) -> tuple[str, ...]:
    import re

    return tuple(
        dict.fromkeys(
            match
            for match in re.findall(r"(?:article|ст\.?|статья)\s*(\d{1,3}(?:\.\d+)?)", str(query or ""), flags=re.IGNORECASE)
            if match
        )
    )


def _match_bonus(match: LawRetrievalMatch, query: str, profile: str) -> int:
    import re

    normalized_title = _normalize_retrieval_text(match.chunk.document_title)
    normalized_label = _normalize_retrieval_text(match.chunk.article_label)
    article_numbers = _extract_article_numbers(query)
    query_tokens = _query_tokens(query)
    bonus = 0

    label_specific = normalized_label and normalized_label != "general"
    if label_specific:
        bonus += 4
    if profile == "suggest" and not label_specific:
        bonus -= 8

    for article_number in article_numbers:
        article_pattern = rf"(?:article|ст\.?|статья)\s*{re.escape(article_number)}\b"
        if re.search(article_pattern, normalized_label, flags=re.IGNORECASE):
            bonus += 28
        elif re.search(article_pattern, _normalize_retrieval_text(match.chunk.text[:600]), flags=re.IGNORECASE):
            bonus += 16

    label_hits = sum(1 for token in query_tokens if token in normalized_label)
    title_hits = sum(1 for token in query_tokens if token in normalized_title)
    bonus += label_hits * 6
    bonus += title_hits * 3

    if profile == "suggest":
        if label_hits == 0 and title_hits == 0 and not article_numbers:
            bonus -= 4
        if len(match.chunk.text or "") > 2500:
            bonus -= 2
    else:
        if label_hits or article_numbers:
            bonus += 2

    return bonus


def _rerank_matches(matches: tuple[LawRetrievalMatch, ...], query: str, profile: str) -> tuple[LawRetrievalMatch, ...]:
    reranked = [
        LawRetrievalMatch(
            chunk=match.chunk,
            score=max(match.score + _match_bonus(match, query, profile), 0),
            excerpt=match.excerpt,
        )
        for match in matches
    ]
    reranked.sort(key=lambda item: item.score, reverse=True)
    return tuple(reranked)
