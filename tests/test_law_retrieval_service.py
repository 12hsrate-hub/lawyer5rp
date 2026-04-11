from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.law_bundle_service import LawChunk
from ogp_web.services.law_retrieval_service import retrieve_law_context, unique_sources


class TestLawRetrievalService:
    def test_retrieve_law_context_returns_stable_contract(self):
        chunk = LawChunk(
            url="https://laws.example/article-20",
            document_title="Procedural Code",
            article_label="Article 20",
            text="Release grounds for detained person.",
        )

        result = retrieve_law_context(
            server_code="blackberry",
            query="release grounds",
            excerpt_chars=120,
            profile="law_qa",
            get_server_config_func=lambda _: SimpleNamespace(
                code="blackberry",
                name="BlackBerry",
                law_qa_sources=("https://laws.example/base",),
                law_qa_bundle_path="",
            ),
            load_law_bundle_chunks_func=lambda server_code, bundle_path: [],
            build_law_chunk_index_func=lambda source_urls: [chunk],
            select_chunks_func=lambda chunks, query: (list(chunks), "high"),
            score_chunk_func=lambda item, query: 77,
            extract_excerpt_func=lambda text, query, max_chars=0: text[:max_chars or len(text)],
        )

        assert result.server_code == "blackberry"
        assert result.server_name == "BlackBerry"
        assert result.profile == "law_qa"
        assert result.query == "release grounds"
        assert result.confidence == "high"
        assert result.is_configured is True
        assert result.indexed_chunk_count == 1
        assert len(result.matches) == 1
        assert result.matches[0].score >= 77
        assert result.matches[0].chunk.article_label == "Article 20"
        assert result.matches[0].excerpt == "Release grounds for detained person."

    def test_retrieve_law_context_marks_unconfigured_server(self):
        result = retrieve_law_context(
            server_code="blackberry",
            query="anything",
            excerpt_chars=120,
            profile="law_qa",
            get_server_config_func=lambda _: SimpleNamespace(
                code="blackberry",
                name="BlackBerry",
                law_qa_sources=(),
                law_qa_bundle_path="",
            ),
            load_law_bundle_chunks_func=lambda server_code, bundle_path: [],
            build_law_chunk_index_func=lambda source_urls: [],
            select_chunks_func=lambda chunks, query: ([], "low"),
            score_chunk_func=lambda item, query: 0,
            extract_excerpt_func=lambda text, query, max_chars=0: "",
        )

        assert result.is_configured is False
        assert result.indexed_chunk_count == 0
        assert result.matches == ()

    def test_unique_sources_deduplicates_urls(self):
        chunk_one = LawChunk(
            url="https://laws.example/article-20",
            document_title="Procedural Code",
            article_label="Article 20",
            text="One",
        )
        chunk_two = LawChunk(
            url="https://laws.example/article-20",
            document_title="Procedural Code",
            article_label="Article 20.1",
            text="Two",
        )

        result = retrieve_law_context(
            server_code="blackberry",
            query="release grounds",
            excerpt_chars=120,
            profile="law_qa",
            get_server_config_func=lambda _: SimpleNamespace(
                code="blackberry",
                name="BlackBerry",
                law_qa_sources=("https://laws.example/base",),
                law_qa_bundle_path="",
            ),
            load_law_bundle_chunks_func=lambda server_code, bundle_path: [],
            build_law_chunk_index_func=lambda source_urls: [chunk_one, chunk_two],
            select_chunks_func=lambda chunks, query: (list(chunks), "medium"),
            score_chunk_func=lambda item, query: 10,
            extract_excerpt_func=lambda text, query, max_chars=0: text,
        )

        assert unique_sources(result) == ("https://laws.example/article-20",)

    def test_suggest_profile_prefers_specific_norms_and_limits_matches(self):
        general = LawChunk(
            url="https://laws.example/general",
            document_title="Procedural Code",
            article_label="general",
            text="General overview of detention and attorney rights.",
        )
        specific = LawChunk(
            url="https://laws.example/article-22",
            document_title="Procedural Code",
            article_label="Article 22",
            text="Attorney rights of detained person.",
        )

        result = retrieve_law_context(
            server_code="blackberry",
            query="attorney rights during detention",
            excerpt_chars=120,
            profile="suggest",
            get_server_config_func=lambda _: SimpleNamespace(
                code="blackberry",
                name="BlackBerry",
                law_qa_sources=("https://laws.example/base",),
                law_qa_bundle_path="",
            ),
            load_law_bundle_chunks_func=lambda server_code, bundle_path: [],
            build_law_chunk_index_func=lambda source_urls: [general, specific],
            select_chunks_func=lambda chunks, query: (list(chunks), "medium"),
            score_chunk_func=lambda item, query: 20,
            extract_excerpt_func=lambda text, query, max_chars=0: text,
        )

        assert result.profile == "suggest"
        assert len(result.matches) <= 4
        assert result.matches[0].chunk.article_label == "Article 22"
