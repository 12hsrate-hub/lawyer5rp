from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
import uuid
from typing import Any, Iterable


LEGAL_PIPELINE_CONTRACT_VERSION = "legal_pipeline.v1"

FEEDBACK_ISSUE_ALIASES: dict[str, tuple[str, ...]] = {
    "wrong_fact": ("fact", "facts", "wrongfact", "bad_fact"),
    "wrong_law": ("law", "wronglaw", "bad_law", "wrong_norm"),
    "missing_law": ("missing_norm", "missing_article", "missing_source"),
    "hallucination": ("made_up", "fabricated", "external_fact"),
    "guard_false_positive": ("guard_fp", "false_positive"),
    "guard_false_negative": ("guard_fn", "false_negative"),
    "unclear_answer": ("unclear", "vague", "weak_answer"),
}

_SOURCE_CITATION_PATTERN = re.compile(r"\[\s*Источник\s*:\s*(https?://[^\]\s]+)\s*\]", flags=re.IGNORECASE)
_URL_PATTERN = re.compile(r"https?://[^\s)\]]+", flags=re.IGNORECASE)
_META_SECTION_PATTERN = re.compile(r"^\s*\[[a-z_]+\]\s*$", flags=re.IGNORECASE | re.MULTILINE)
_MARKDOWN_EMPHASIS_PATTERN = re.compile(r"(?<!\*)\*\*(.+?)\*\*(?!\*)|(?<!_)__(.+?)__(?!_)")
_MARKDOWN_INLINE_PATTERN = re.compile(r"(?<!\*)\*(.+?)\*(?!\*)|(?<!_)_(.+?)_(?!_)|`([^`]+)`")
_LIST_MARKER_PATTERN = re.compile(r"^\s*(?:[-*•]+|\d+[.)])\s+")


@dataclass(frozen=True)
class BundleHealth:
    status: str
    generated_at: str = ""
    age_hours: int | None = None
    source_count: int = 0
    chunk_count: int = 0
    fingerprint: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class GuardIssue:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class GuardResult:
    status: str
    issues: tuple[GuardIssue, ...] = ()
    retryable: bool = False

    @property
    def warning_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues if issue.severity == "warn")

    @property
    def failure_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues if issue.severity == "fail")


@dataclass(frozen=True)
class ShadowComparison:
    enabled: bool
    profile: str = ""
    diverged: bool = False
    overlap_count: int = 0
    primary_labels: tuple[str, ...] = ()
    shadow_labels: tuple[str, ...] = ()


def new_generation_id() -> str:
    return uuid.uuid4().hex


def short_text_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def mask_text_preview(text: str, *, max_chars: int = 240) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def parse_source_citations(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.strip() for match in _SOURCE_CITATION_PATTERN.findall(str(text or "")) if match.strip()))


def parse_urls(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.strip(".,;") for match in _URL_PATTERN.findall(str(text or "")) if match.strip()))


def strip_law_qa_source_urls(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""

    cleaned = _SOURCE_CITATION_PATTERN.sub("", normalized)
    cleaned = _URL_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\[\s*Источник\s*:\s*\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip()


def normalize_law_qa_text_formatting(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""

    cleaned = _MARKDOWN_EMPHASIS_PATTERN.sub(lambda match: match.group(1) or match.group(2) or "", normalized)
    cleaned = _MARKDOWN_INLINE_PATTERN.sub(lambda match: match.group(1) or match.group(2) or match.group(3) or "", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.strip() for line in cleaned.split("\n")]
    paragraphs: list[str] = []
    list_items: list[str] = []

    def flush_list_items() -> None:
        if not list_items:
            return
        paragraphs.append("; ".join(item.strip().rstrip(" ;") for item in list_items if item.strip()))
        list_items.clear()

    for line in lines:
        if not line:
            flush_list_items()
            continue
        stripped = _LIST_MARKER_PATTERN.sub("", line).strip()
        if stripped != line:
            if stripped:
                list_items.append(stripped)
            continue
        flush_list_items()
        paragraphs.append(line)

    flush_list_items()

    cleaned = "\n".join(part for part in paragraphs if part)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip()


def build_bundle_health(
    *,
    generated_at: str = "",
    source_count: int = 0,
    chunk_count: int = 0,
    fingerprint: str = "",
    max_age_hours: int = 168,
) -> BundleHealth:
    warnings: list[str] = []
    status = "unknown"
    age_hours: int | None = None
    normalized_generated_at = str(generated_at or "").strip()
    if not normalized_generated_at:
        warnings.append("bundle_generation_time_missing")
        status = "unknown"
    else:
        try:
            parsed = datetime.fromisoformat(normalized_generated_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age_hours = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds() // 3600))
            status = "stale" if age_hours > max(1, int(max_age_hours or 1)) else "fresh"
            if status == "stale":
                warnings.append("bundle_stale")
        except ValueError:
            warnings.append("bundle_generation_time_invalid")
            status = "unknown"
    if chunk_count <= 0:
        warnings.append("bundle_empty")
        status = "missing"
    return BundleHealth(
        status=status,
        generated_at=normalized_generated_at,
        age_hours=age_hours,
        source_count=max(0, int(source_count or 0)),
        chunk_count=max(0, int(chunk_count or 0)),
        fingerprint=str(fingerprint or "").strip(),
        warnings=tuple(warnings),
    )


def guard_law_qa_answer(
    *,
    text: str,
    allowed_source_urls: Iterable[str],
    bundle_health: BundleHealth,
) -> GuardResult:
    issues: list[GuardIssue] = []
    normalized_text = str(text or "").strip()
    if not normalized_text:
        issues.append(GuardIssue(code="empty_output", severity="fail", message="The model returned an empty answer."))
        return GuardResult(status="fail", issues=tuple(issues), retryable=True)

    cited_sources = set(parse_source_citations(normalized_text))
    leaked_urls = set(parse_urls(normalized_text))

    if cited_sources:
        issues.append(
            GuardIssue(
                code="source_citation_leak",
                severity="warn",
                message="The answer still contains inline source citations.",
            )
        )
    if leaked_urls:
        issues.append(
            GuardIssue(
                code="source_url_leak",
                severity="warn",
                message="The answer still contains raw source URLs.",
            )
        )
    if "```" in normalized_text:
        issues.append(
            GuardIssue(
                code="code_block_leak",
                severity="warn",
                message="The answer still contains fenced formatting.",
            )
        )
    if "\n-" in normalized_text or "\n*" in normalized_text or re.search(r"\n\s*\d+[.)]\s+", normalized_text):
        issues.append(
            GuardIssue(
                code="list_format_leak",
                severity="warn",
                message="The answer still contains list formatting.",
            )
        )
    if "**" in normalized_text or "__" in normalized_text or re.search(r"`[^`]+`", normalized_text):
        issues.append(
            GuardIssue(
                code="markdown_format_leak",
                severity="warn",
                message="The answer still contains markdown emphasis.",
            )
        )
    if bundle_health.status == "stale":
        issues.append(
            GuardIssue(
                code="bundle_stale",
                severity="warn",
                message="The law bundle is stale and may need rebuilding.",
            )
        )
    if bundle_health.status == "missing":
        issues.append(
            GuardIssue(
                code="bundle_missing",
                severity="fail",
                message="The law bundle is missing or empty.",
            )
        )

    status = "pass"
    if any(item.severity == "fail" for item in issues):
        status = "fail"
    elif issues:
        status = "warn"
    return GuardResult(status=status, issues=tuple(issues), retryable=status == "fail")


def guard_suggest_answer(*, text: str) -> GuardResult:
    issues: list[GuardIssue] = []
    normalized_text = str(text or "").strip()
    if not normalized_text:
        issues.append(GuardIssue(code="empty_output", severity="fail", message="The model returned an empty answer."))
        return GuardResult(status="fail", issues=tuple(issues), retryable=True)
    if "```" in normalized_text:
        issues.append(
            GuardIssue(
                code="code_block_leak",
                severity="warn",
                message="The answer still contains fenced formatting.",
            )
        )
    if parse_urls(normalized_text):
        issues.append(
            GuardIssue(
                code="source_url_leak",
                severity="warn",
                message="The complaint text still contains raw URLs.",
            )
        )
    if _META_SECTION_PATTERN.search(normalized_text):
        issues.append(
            GuardIssue(
                code="meta_section_leak",
                severity="warn",
                message="The answer contains service/meta sections.",
            )
        )
    if "\n-" in normalized_text or "\n*" in normalized_text:
        issues.append(
            GuardIssue(
                code="list_format_leak",
                severity="warn",
                message="The answer contains list formatting, expected one cohesive text block.",
            )
        )
    status = "pass" if not issues else "warn"
    return GuardResult(status=status, issues=tuple(issues), retryable=False)


def build_shadow_comparison(
    *,
    enabled: bool,
    profile: str,
    primary_matches: Iterable[Any],
    shadow_matches: Iterable[Any] | None = None,
) -> ShadowComparison:
    primary_labels = tuple(
        dict.fromkeys(
            str(getattr(getattr(item, "chunk", None), "article_label", "") or "").strip()
            for item in primary_matches
            if str(getattr(getattr(item, "chunk", None), "article_label", "") or "").strip()
        )
    )
    shadow_labels = tuple(
        dict.fromkeys(
            str(getattr(getattr(item, "chunk", None), "article_label", "") or "").strip()
            for item in (shadow_matches or ())
            if str(getattr(getattr(item, "chunk", None), "article_label", "") or "").strip()
        )
    )
    overlap = len(set(primary_labels) & set(shadow_labels))
    diverged = bool(enabled and shadow_labels and primary_labels != shadow_labels)
    return ShadowComparison(
        enabled=enabled,
        profile=str(profile or "").strip(),
        diverged=diverged,
        overlap_count=overlap,
        primary_labels=primary_labels,
        shadow_labels=shadow_labels,
    )


def normalize_feedback_issues(raw_issues: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw_issue in raw_issues:
        value = str(raw_issue or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not value:
            continue
        canonical = None
        for issue_code, aliases in FEEDBACK_ISSUE_ALIASES.items():
            if value == issue_code or value in aliases:
                canonical = issue_code
                break
        if canonical is None:
            canonical = "other"
        if canonical not in normalized:
            normalized.append(canonical)
    return tuple(normalized)
