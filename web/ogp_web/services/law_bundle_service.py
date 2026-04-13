from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import httpx
from ogp_web.services.law_version_service import load_law_chunks_by_version, resolve_active_law_version


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAW_BUNDLE_DIR = PACKAGE_ROOT / "law_bundles"
ARTICLE_LABEL_PATTERN = re.compile(r"(?i)статья\s+\d{1,3}(?:\.\d+)?(?:\s*[^.\n\r]{0,180})?\.")
ARTICLE_NUMBER_PATTERN = re.compile(r"(?i)статья\s+(\d{1,3}(?:\.\d+)?)")
SECTION_HEADING_PATTERN = re.compile(
    r"(?i)(глава\s+[ivxlcdm\d]+(?:\.\d+)?\.\s*[^.\n\r]{0,220}|раздел\s+[ivxlcdm\d]+(?:\.\d+)?\.\s*[^.\n\r]{0,220})"
)
COMMENT_PREFIX_PATTERNS = (
    "комментарии к",
    "комментарий к",
)


@dataclass(frozen=True)
class LawChunk:
    url: str
    document_title: str
    article_label: str
    text: str


@dataclass(frozen=True)
class LawBundleSource:
    url: str
    document_title: str
    page_urls: tuple[str, ...]
    post_count: int
    included_post_count: int
    chunk_count: int


@dataclass(frozen=True)
class LawBundleMeta:
    law_version_id: int | None
    server_code: str
    generated_at_utc: str
    source_count: int
    chunk_count: int
    fingerprint: str


class _ThreadTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self._parts: list[str] = []

    @property
    def title(self) -> str:
        raw = " ".join(part.strip() for part in self._parts if part and part.strip())
        normalized = re.sub(r"\s+", " ", unescape(raw)).strip()
        if not normalized:
            return ""
        normalized = re.sub(r"\s+\|\s+Форум GTA 5 RP.*$", "", normalized, flags=re.IGNORECASE)
        return normalized.strip()

    def handle_starttag(self, tag: str, attrs) -> None:
        _ = attrs
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and data:
            self._parts.append(data)


class _ThreadPostParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.posts: list[dict[str, str]] = []
        self._in_post = False
        self._post_depth = 0
        self._in_body = False
        self._body_depth = 0
        self._ignore_depth = 0
        self._current_parts: list[str] = []
        self._current_author = ""
        self._current_content_id = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        class_name = attributes.get("class", "")

        if tag.lower() == "article" and "message message--post" in class_name:
            self._in_post = True
            self._post_depth = 1
            self._in_body = False
            self._body_depth = 0
            self._ignore_depth = 0
            self._current_parts = []
            self._current_author = str(attributes.get("data-author", "") or "")
            self._current_content_id = str(attributes.get("data-content", "") or "")
            return

        if not self._in_post:
            return

        self._post_depth += 1
        if tag.lower() == "article" and "message-body" in class_name:
            self._in_body = True
            self._body_depth = 1
            return

        if self._in_body:
            self._body_depth += 1
            if tag.lower() in {"script", "style", "noscript", "template"}:
                self._ignore_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._in_post:
            return

        if self._in_body:
            if tag.lower() in {"script", "style", "noscript", "template"} and self._ignore_depth > 0:
                self._ignore_depth -= 1
            self._body_depth -= 1
            if self._body_depth == 0:
                self._in_body = False

        self._post_depth -= 1
        if self._post_depth == 0:
            text = re.sub(r"\s+", " ", " ".join(self._current_parts)).strip()
            self.posts.append(
                {
                    "author": self._current_author,
                    "content_id": self._current_content_id,
                    "text": text,
                }
            )
            self._in_post = False
            self._current_parts = []
            self._current_author = ""
            self._current_content_id = ""

    def handle_data(self, data: str) -> None:
        if self._in_post and self._in_body and self._ignore_depth == 0 and data and data.strip():
            self._current_parts.append(unescape(data.strip()))


def resolve_law_bundle_path(server_code: str, bundle_path: str = "") -> Path:
    configured = str(bundle_path or "").strip()
    if configured:
        path = Path(configured)
        if path.is_absolute():
            return path
        return PACKAGE_ROOT / path
    return DEFAULT_LAW_BUNDLE_DIR / f"{server_code}.json"


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="", query="").geturl().rstrip("/")


def _discover_thread_page_urls(thread_url: str, html: str) -> tuple[str, ...]:
    normalized_root = _normalize_url(thread_url)
    page_urls = {normalized_root}
    parsed_root = urlparse(normalized_root)
    thread_path = parsed_root.path.rstrip("/")
    for match in re.finditer(r'href="([^"]+)"', html, flags=re.IGNORECASE):
        href = match.group(1)
        absolute = _normalize_url(urljoin(normalized_root + "/", href))
        parsed = urlparse(absolute)
        if parsed.netloc != parsed_root.netloc:
            continue
        if parsed.path.startswith(thread_path + "/page-"):
            page_urls.add(absolute)
    return tuple(sorted(page_urls))


def _extract_thread_title(html: str, fallback_url: str) -> str:
    parser = _ThreadTitleParser()
    parser.feed(html)
    return parser.title or fallback_url


def _extract_thread_posts(html: str) -> list[dict[str, str]]:
    parser = _ThreadPostParser()
    parser.feed(html)
    return [item for item in parser.posts if item.get("text")]


def _looks_like_commentary_post(text: str) -> bool:
    prefix = str(text or "").lower()[:400]
    return any(marker in prefix for marker in COMMENT_PREFIX_PATTERNS)


def _count_article_labels(text: str) -> int:
    return len(ARTICLE_LABEL_PATTERN.findall(str(text or "")))


def _should_include_post(document_title: str, post_text: str) -> bool:
    text = str(post_text or "").strip()
    if not text:
        return False
    if _looks_like_commentary_post(text):
        return False

    article_count = _count_article_labels(text)
    if article_count > 0:
        return True

    normalized_title = str(document_title or "").lower()
    if "прецедент" in normalized_title and len(text) >= 300:
        return True
    return False


def _split_structured_text_into_chunks(*, url: str, document_title: str, text: str) -> list[LawChunk]:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return []

    matches = list(ARTICLE_LABEL_PATTERN.finditer(normalized_text))
    if not matches:
        return [LawChunk(url=url, document_title=document_title, article_label="Общий раздел", text=normalized_text[:5000])]

    chunks: list[LawChunk] = []
    active_section_heading = ""
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized_text)
        chunk_text = normalized_text[start:end].strip()
        trailing_heading = ""
        trailing_heading_matches = list(SECTION_HEADING_PATTERN.finditer(chunk_text))
        if index + 1 < len(matches) and trailing_heading_matches:
            candidate = trailing_heading_matches[-1]
            if candidate.start() > max(40, len(chunk_text) // 2):
                trailing_heading = chunk_text[candidate.start() :].strip()
                chunk_text = chunk_text[: candidate.start()].strip()
        article_label = re.sub(r"\s+", " ", match.group(0)).strip(" .:-")
        if chunk_text:
            if active_section_heading:
                chunk_text = f"{active_section_heading} {chunk_text}".strip()
            chunks.append(
                LawChunk(
                    url=url,
                    document_title=document_title,
                    article_label=article_label or "Статья",
                    text=chunk_text[:5000].strip(),
                )
            )
        if trailing_heading:
            active_section_heading = trailing_heading
    return chunks


def _fetch_thread_pages(thread_url: str, *, timeout_seconds: float = 12.0) -> tuple[str, str, list[dict[str, str]]]:
    normalized_root = _normalize_url(thread_url)
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        first_response = client.get(normalized_root)
        first_response.raise_for_status()
        first_html = first_response.text
        document_title = _extract_thread_title(first_html, normalized_root)
        page_urls = _discover_thread_page_urls(normalized_root, first_html)

        posts: list[dict[str, str]] = []
        seen_content_ids: set[str] = set()
        for page_url in page_urls:
            response_html = first_html if _normalize_url(page_url) == normalized_root else client.get(page_url).text
            for post in _extract_thread_posts(response_html):
                content_id = str(post.get("content_id") or "")
                if content_id and content_id in seen_content_ids:
                    continue
                if content_id:
                    seen_content_ids.add(content_id)
                posts.append(post)

    return document_title, tuple(page_urls), posts


def build_law_bundle(server_code: str, source_urls: Iterable[str]) -> dict[str, object]:
    all_chunks: list[LawChunk] = []
    source_items: list[LawBundleSource] = []

    for source_url in source_urls:
        normalized_url = str(source_url or "").strip()
        if not normalized_url:
            continue

        document_title, page_urls, posts = _fetch_thread_pages(normalized_url)
        included_posts = [post for post in posts if _should_include_post(document_title, post.get("text", ""))]
        joined_text = "\n\n".join(str(post.get("text") or "").strip() for post in included_posts if post.get("text"))
        chunks = _split_structured_text_into_chunks(
            url=normalized_url,
            document_title=document_title,
            text=joined_text,
        )
        all_chunks.extend(chunks)
        source_items.append(
            LawBundleSource(
                url=normalized_url,
                document_title=document_title,
                page_urls=page_urls,
                post_count=len(posts),
                included_post_count=len(included_posts),
                chunk_count=len(chunks),
            )
        )

    return {
        "server_code": server_code,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [asdict(item) for item in source_items],
        "articles": [asdict(item) for item in all_chunks],
    }


def write_law_bundle(bundle: dict[str, object], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def load_law_bundle_meta(server_code: str, bundle_path: str = "", requested_version_id: int | None = None) -> LawBundleMeta | None:
    resolved_version = resolve_active_law_version(server_code=server_code, requested_version_id=requested_version_id)
    if resolved_version:
        return LawBundleMeta(
            law_version_id=resolved_version.id,
            server_code=resolved_version.server_code,
            generated_at_utc=resolved_version.generated_at_utc,
            source_count=0,
            chunk_count=resolved_version.chunk_count,
            fingerprint=resolved_version.fingerprint,
        )
    path = resolve_law_bundle_path(server_code, bundle_path)
    if not path.exists():
        return None
    payload = _load_law_bundle_payload_cached(str(path), path.stat().st_mtime_ns)
    return _payload_to_bundle_meta(server_code, payload)


def load_law_bundle_chunks(
    server_code: str,
    bundle_path: str = "",
    requested_version_id: int | None = None,
) -> tuple[LawChunk, ...]:
    resolved_version = resolve_active_law_version(server_code=server_code, requested_version_id=requested_version_id)
    if resolved_version:
        return load_law_chunks_by_version(server_code, resolved_version.id)
    path = resolve_law_bundle_path(server_code, bundle_path)
    if not path.exists():
        return ()
    payload = _load_law_bundle_payload_cached(str(path), path.stat().st_mtime_ns)
    return _payload_to_law_chunks(payload)


@lru_cache(maxsize=16)
def _load_law_bundle_payload_cached(bundle_path: str, bundle_mtime_ns: int) -> dict[str, object]:
    _ = bundle_mtime_ns
    path = Path(bundle_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _payload_to_bundle_meta(server_code: str, payload: dict[str, object]) -> LawBundleMeta:
    articles = payload.get("articles", []) if isinstance(payload, dict) else []
    sources = payload.get("sources", []) if isinstance(payload, dict) else []
    fingerprint_source = json.dumps(
        {
            "server_code": payload.get("server_code") if isinstance(payload, dict) else server_code,
            "generated_at_utc": payload.get("generated_at_utc") if isinstance(payload, dict) else "",
            "source_urls": [
                str(item.get("url") or "").strip()
                for item in sources
                if isinstance(item, dict) and str(item.get("url") or "").strip()
            ],
            "chunk_count": len(articles) if isinstance(articles, list) else 0,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return LawBundleMeta(
        law_version_id=None,
        server_code=str(payload.get("server_code") or server_code).strip() or server_code,
        generated_at_utc=str(payload.get("generated_at_utc") or "").strip(),
        source_count=len(sources) if isinstance(sources, list) else 0,
        chunk_count=len(articles) if isinstance(articles, list) else 0,
        fingerprint=hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:16],
    )


def _payload_to_law_chunks(payload: dict[str, object]) -> tuple[LawChunk, ...]:
    items: list[LawChunk] = []
    for raw_item in payload.get("articles", []) if isinstance(payload, dict) else []:
        if not isinstance(raw_item, dict):
            continue
        url = str(raw_item.get("url") or "").strip()
        document_title = str(raw_item.get("document_title") or "").strip()
        article_label = str(raw_item.get("article_label") or "").strip()
        text = str(raw_item.get("text") or "").strip()
        if not url or not document_title or not article_label or not text:
            continue
        items.append(
            LawChunk(
                url=url,
                document_title=document_title,
                article_label=article_label,
                text=text,
            )
        )
    return tuple(items)
