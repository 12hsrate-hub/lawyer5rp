from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class LawSourcesValidation:
    normalized_urls: tuple[str, ...]
    accepted_urls: tuple[str, ...]
    invalid_urls: tuple[str, ...]
    invalid_details: tuple[dict[str, str], ...]
    duplicate_count: int
    duplicate_urls: tuple[str, ...]


def normalize_source_urls(source_urls: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in source_urls:
        value = str(raw or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)


def source_url_error(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return "unsupported_scheme"
    if not parsed.netloc:
        return "missing_host"
    return None


def is_valid_source_url(value: str) -> bool:
    return source_url_error(value) is None


def canonicalize_source_url(value: str) -> str:
    parsed = urlparse(value)
    normalized_path = parsed.path.rstrip("/")
    return parsed._replace(path=normalized_path, params="", query="", fragment="").geturl()


def validate_source_urls(source_urls: list[str] | tuple[str, ...]) -> LawSourcesValidation:
    normalized = tuple(canonicalize_source_url(item) for item in normalize_source_urls(source_urls))
    accepted: list[str] = []
    invalid: list[str] = []
    invalid_details: list[dict[str, str]] = []
    seen: set[str] = set()
    duplicate_count = 0
    duplicate_urls: list[str] = []

    for raw in source_urls:
        raw_value = str(raw or "").strip()
        if not raw_value:
            continue
        error_code = source_url_error(raw_value)
        if error_code:
            invalid.append(raw_value)
            invalid_details.append({"url": raw_value, "reason": error_code})
            continue
        value = canonicalize_source_url(raw_value)
        if value in seen:
            duplicate_count += 1
            duplicate_urls.append(value)
            continue
        seen.add(value)
        accepted.append(value)

    return LawSourcesValidation(
        normalized_urls=normalized,
        accepted_urls=tuple(accepted),
        invalid_urls=tuple(invalid),
        invalid_details=tuple(invalid_details),
        duplicate_count=duplicate_count,
        duplicate_urls=tuple(duplicate_urls),
    )
