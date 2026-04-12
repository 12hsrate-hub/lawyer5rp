from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
from pathlib import Path
import re
from typing import Iterable

import yaml

from ogp_web.schemas import SuggestPayload
from ogp_web.services.law_retrieval_service import LawRetrievalMatch


ROOT_DIR = Path(__file__).resolve().parents[3]
ARTICLE_TRIGGER_CONFIG_PATH = ROOT_DIR / "config" / "legal_article_triggers.yaml"
POINT3_EVAL_THRESHOLD_PATH = ROOT_DIR / "config" / "point3_eval_thresholds.yaml"
logger = logging.getLogger(__name__)
ARTICLE_REF_PATTERN = re.compile(r"(?i)(?:ст\.?|статья|article)\s*(\d{1,3}(?:\.\d+)?)")
DATE_TOKEN_PATTERN = re.compile(r"\b\d{1,4}[./:-]\d{1,2}[./:-]\d{1,4}\b|\b\d{1,2}:\d{2}\b")
LONG_NUMBER_PATTERN = re.compile(r"(?:#\d{2,}|\b\d{3,}\b)")
URL_PATTERN = re.compile(r"https?://\S+", flags=re.IGNORECASE)
LIST_MARKER_PATTERN = re.compile(r"(?m)^\s*(?:[-*]|\d+\.)\s+")
DEFAULT_POINT3_EVAL_THRESHOLDS: dict[str, object] = {
    "version": 1,
    "release_gates": {
        "factual_integrity_min": 1.0,
        "unsupported_article_rate_max": 0.0,
        "new_fact_rate_max": 0.0,
        "format_violation_rate_max": 0.01,
        "safe_fallback_rate_max": 0.1,
        "validation_retry_rate_max": 0.12,
    },
    "monitoring": {
        "warning": {
            "unsupported_article_rate": 0.01,
            "new_fact_rate": 0.01,
            "format_violation_rate": 0.03,
            "validation_retry_rate": 0.08,
            "safe_fallback_rate": 0.08,
        },
        "critical": {
            "unsupported_article_rate": 0.03,
            "new_fact_rate": 0.02,
            "format_violation_rate": 0.05,
            "validation_retry_rate": 0.12,
            "safe_fallback_rate": 0.12,
        },
    },
}


@dataclass(frozen=True)
class ArticleTriggerRule:
    key: str
    document_title_contains: str
    article_numbers: tuple[str, ...]
    basis_codes_any: tuple[str, ...]
    trigger_terms_any: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class ArticleApplicabilityHit:
    key: str
    article_numbers: tuple[str, ...]
    document_title_contains: str
    triggered_terms: tuple[str, ...]
    description: str
    explicit_article_reference: bool = False


@dataclass(frozen=True)
class ArticleApplicabilityResult:
    matches: tuple[LawRetrievalMatch, ...]
    mode: str
    allowed_article_numbers: tuple[str, ...]
    allowed_article_labels: tuple[str, ...]
    prompt_block: str
    hits: tuple[ArticleApplicabilityHit, ...]


@dataclass(frozen=True)
class SuggestOutputValidationResult:
    status: str
    error_codes: tuple[str, ...]
    messages: tuple[str, ...]
    unsupported_article_numbers: tuple[str, ...]
    new_fact_signals: tuple[str, ...]


def _normalize_text(value: str) -> str:
    normalized = str(value or "").lower().replace("ё", "е")
    normalized = re.sub(r"[\r\n\t]+", " ", normalized)
    normalized = re.sub(r"[^\w./:#-]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(token for token in _normalize_text(value).split() if token)


def _token_matches(token: str, candidate: str) -> bool:
    if token == candidate:
        return True
    if len(token) >= 5 and len(candidate) >= 5:
        return token[:5] == candidate[:5]
    return False


def _contains_trigger(text: str, trigger: str) -> bool:
    normalized_text = _normalize_text(text)
    normalized_trigger = _normalize_text(trigger)
    if not normalized_text or not normalized_trigger:
        return False
    if normalized_trigger in normalized_text:
        return True
    trigger_tokens = _tokenize(normalized_trigger)
    text_tokens = _tokenize(normalized_text)
    if not trigger_tokens or not text_tokens:
        return False
    return all(any(_token_matches(token, candidate) for candidate in text_tokens) for token in trigger_tokens)


def _extract_article_numbers(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match for match in ARTICLE_REF_PATTERN.findall(str(text or "")) if match))


def _extract_literal_signals(text: str) -> tuple[str, ...]:
    signals: list[str] = []
    for pattern in (DATE_TOKEN_PATTERN, LONG_NUMBER_PATTERN, URL_PATTERN):
        signals.extend(pattern.findall(str(text or "")))
    return tuple(dict.fromkeys(str(item).strip() for item in signals if str(item).strip()))


def _match_rule(rule: ArticleTriggerRule, match: LawRetrievalMatch) -> bool:
    title = _normalize_text(match.chunk.document_title)
    label_numbers = set(_extract_article_numbers(match.chunk.article_label))
    if rule.document_title_contains and _normalize_text(rule.document_title_contains) not in title:
        return False
    return bool(label_numbers & set(rule.article_numbers))


@lru_cache(maxsize=16)
def _load_article_trigger_rules_payload() -> dict[str, object]:
    raw = ARTICLE_TRIGGER_CONFIG_PATH.read_text(encoding="utf-8")
    payload = yaml.safe_load(raw) or {}
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=16)
def load_article_trigger_rules(server_code: str) -> tuple[ArticleTriggerRule, ...]:
    payload = _load_article_trigger_rules_payload()
    server_payload = (((payload.get("servers") or {}).get(str(server_code or "").strip().lower()) or {}).get("suggest") or {})
    rules: list[ArticleTriggerRule] = []
    for item in server_payload.get("rules") or []:
        if not isinstance(item, dict):
            continue
        rules.append(
            ArticleTriggerRule(
                key=str(item.get("key") or "").strip(),
                document_title_contains=str(item.get("document_title_contains") or "").strip(),
                article_numbers=tuple(str(value).strip() for value in (item.get("article_numbers") or []) if str(value).strip()),
                basis_codes_any=tuple(str(value).strip() for value in (item.get("basis_codes_any") or []) if str(value).strip()),
                trigger_terms_any=tuple(str(value).strip() for value in (item.get("trigger_terms_any") or []) if str(value).strip()),
                description=str(item.get("description") or "").strip(),
            )
        )
    return tuple(rule for rule in rules if rule.key and rule.article_numbers)


@lru_cache(maxsize=4)
def load_point3_eval_thresholds() -> dict[str, object]:
    try:
        raw = POINT3_EVAL_THRESHOLD_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(
            "point3_eval_thresholds_missing path=%s; using built-in defaults",
            POINT3_EVAL_THRESHOLD_PATH,
        )
        return dict(DEFAULT_POINT3_EVAL_THRESHOLDS)
    try:
        payload = yaml.safe_load(raw) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "point3_eval_thresholds_invalid path=%s error=%s; using built-in defaults",
            POINT3_EVAL_THRESHOLD_PATH,
            exc,
        )
        return dict(DEFAULT_POINT3_EVAL_THRESHOLDS)
    return payload if isinstance(payload, dict) else dict(DEFAULT_POINT3_EVAL_THRESHOLDS)


def _payload_input_text(payload: SuggestPayload) -> str:
    return " ".join(
        part
        for part in (
            payload.victim_name,
            payload.org,
            payload.subject,
            payload.event_dt,
            payload.complaint_basis,
            payload.main_focus,
            payload.raw_desc,
        )
        if str(part or "").strip()
    )


def select_applicable_articles(
    *,
    server_code: str,
    payload: SuggestPayload,
    matches: Iterable[LawRetrievalMatch],
) -> ArticleApplicabilityResult:
    rules = load_article_trigger_rules(server_code)
    input_text = _payload_input_text(payload)
    explicit_numbers = set(_extract_article_numbers(input_text))
    selected_matches: list[LawRetrievalMatch] = []
    hits: list[ArticleApplicabilityHit] = []
    allowed_numbers: list[str] = []
    allowed_labels: list[str] = []

    for match in matches:
        match_numbers = tuple(_extract_article_numbers(match.chunk.article_label))
        explicit_match = bool(set(match_numbers) & explicit_numbers)
        matched_rule = next((rule for rule in rules if _match_rule(rule, match)), None)
        triggered_terms: list[str] = []
        if matched_rule is not None:
            triggered_terms = [term for term in matched_rule.trigger_terms_any if _contains_trigger(input_text, term)]
            if matched_rule.basis_codes_any and payload.complaint_basis not in matched_rule.basis_codes_any and not explicit_match:
                triggered_terms = []

        if not explicit_match and not triggered_terms:
            continue

        selected_matches.append(match)
        allowed_numbers.extend(match_numbers)
        allowed_labels.append(match.chunk.article_label)
        if matched_rule is not None:
            hits.append(
                ArticleApplicabilityHit(
                    key=matched_rule.key,
                    article_numbers=matched_rule.article_numbers,
                    document_title_contains=matched_rule.document_title_contains,
                    triggered_terms=tuple(triggered_terms),
                    description=matched_rule.description,
                    explicit_article_reference=explicit_match,
                )
            )
        elif explicit_match:
            hits.append(
                ArticleApplicabilityHit(
                    key="explicit_input_article_reference",
                    article_numbers=match_numbers,
                    document_title_contains=match.chunk.document_title,
                    triggered_terms=(),
                    description="Статья явно названа во входе.",
                    explicit_article_reference=True,
                )
            )

    if not selected_matches:
        return ArticleApplicabilityResult(
            matches=(),
            mode="factual_only",
            allowed_article_numbers=(),
            allowed_article_labels=(),
            prompt_block="Прямые факт-триггеры для статей во входе не найдены. Пиши только нейтральный фактический абзац без ссылок на статьи.",
            hits=(),
        )

    prompt_lines = ["Применимые нормы по прямым факт-триггерам во входе:"]
    for hit in hits:
        article_text = ", ".join(hit.article_numbers) or "unknown"
        trigger_text = ", ".join(hit.triggered_terms) if hit.triggered_terms else "явное указание статьи во входе"
        prompt_lines.append(
            f"- {hit.document_title_contains}, статьи {article_text}: использовать только потому, что во входе есть триггеры [{trigger_text}]."
        )
    prompt_lines.append("Не упоминай статьи, которых нет в этом списке.")
    return ArticleApplicabilityResult(
        matches=tuple(selected_matches),
        mode="factual_plus_legal",
        allowed_article_numbers=tuple(dict.fromkeys(allowed_numbers)),
        allowed_article_labels=tuple(dict.fromkeys(allowed_labels)),
        prompt_block="\n".join(prompt_lines),
        hits=tuple(hits),
    )


def validate_suggest_output(
    *,
    text: str,
    payload: SuggestPayload,
    server_code: str,
    allowed_article_numbers: Iterable[str],
    allow_article_citations: bool,
) -> SuggestOutputValidationResult:
    normalized_text = str(text or "").strip()
    normalized_input = _payload_input_text(payload)
    error_codes: list[str] = []
    messages: list[str] = []
    output_article_numbers = set(_extract_article_numbers(normalized_text))
    allowed_numbers = set(str(value).strip() for value in allowed_article_numbers if str(value).strip())

    unsupported_numbers: list[str] = []
    if output_article_numbers:
        if not allow_article_citations:
            unsupported_numbers = sorted(output_article_numbers)
        else:
            unsupported_numbers = sorted(number for number in output_article_numbers if number not in allowed_numbers)
    if unsupported_numbers:
        error_codes.append("unsupported_article_reference")
        messages.append("В ответе упомянуты статьи без подтвержденного факт-триггера: " + ", ".join(unsupported_numbers))

    new_fact_signals: list[str] = []
    input_literals = set(_extract_literal_signals(normalized_input))
    output_literals = set(_extract_literal_signals(normalized_text))
    for signal in sorted(output_literals - input_literals):
        if signal not in allowed_numbers:
            new_fact_signals.append(signal)

    for rule in load_article_trigger_rules(server_code):
        for term in rule.trigger_terms_any:
            if _contains_trigger(normalized_text, term) and not _contains_trigger(normalized_input, term):
                new_fact_signals.append(term)

    deduped = tuple(dict.fromkeys(new_fact_signals))
    if deduped:
        error_codes.append("new_fact_detected")
        messages.append("В ответе появились неподтвержденные фактические сигналы: " + ", ".join(deduped[:5]))

    has_multiple_paragraphs = "\n\n" in normalized_text
    has_lists = bool(LIST_MARKER_PATTERN.search(normalized_text))
    has_urls = bool(URL_PATTERN.search(normalized_text))
    if has_multiple_paragraphs or has_lists or has_urls:
        error_codes.append("format_violation")
        messages.append("Ответ должен быть одним абзацем без списков и URL.")

    status = "pass" if not error_codes else "fail"
    return SuggestOutputValidationResult(
        status=status,
        error_codes=tuple(error_codes),
        messages=tuple(messages),
        unsupported_article_numbers=tuple(unsupported_numbers),
        new_fact_signals=deduped,
    )


def build_validation_retry_instruction(validation: SuggestOutputValidationResult) -> str:
    if validation.status == "pass":
        return ""
    return (
        "Предыдущая версия ответа не прошла валидацию. Исправь только следующие ошибки: "
        + "; ".join(validation.messages)
        + " Не добавляй новые факты и не упоминай неподтвержденные статьи."
    )


def build_safe_factual_fallback(payload: SuggestPayload) -> str:
    base_parts: list[str] = []
    if str(payload.victim_name or "").strip():
        base_parts.append(f"Действуя в интересах {payload.victim_name.strip()}, сообщаю следующие обстоятельства.")
    if str(payload.event_dt or "").strip():
        base_parts.append(f"Событие относится к периоду {payload.event_dt.strip()}.")
    facts = re.sub(r"\s+", " ", URL_PATTERN.sub("", str(payload.raw_desc or "").strip()))
    facts = LIST_MARKER_PATTERN.sub("", facts)
    if facts:
        base_parts.append(facts)
    paragraph = " ".join(part.strip() for part in base_parts if part and part.strip())
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    return paragraph.rstrip(".") + "." if paragraph else "Сообщаю обстоятельства, изложенные в черновике, без дополнительных правовых выводов."
