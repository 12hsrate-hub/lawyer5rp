from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
import logging
import os
import re
import socket
from time import monotonic
from html.parser import HTMLParser
from ipaddress import ip_address
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status

from ogp_web.schemas import LawQaPayload, PrincipalScanPayload, PrincipalScanResult, SuggestPayload
from ogp_web.server_config import DEFAULT_SERVER_CODE, get_server_config
from ogp_web.services.ai_budget_service import (
    build_ai_telemetry,
    evaluate_budget,
    policy_to_meta,
    telemetry_to_meta,
)
from ogp_web.services.law_bundle_service import LawChunk, load_law_bundle_chunks
from ogp_web.services.legal_pipeline_service import (
    LEGAL_PIPELINE_CONTRACT_VERSION,
    ShadowComparison,
    build_shadow_comparison,
    guard_law_qa_answer,
    guard_suggest_answer,
    mask_text_preview,
    new_generation_id,
    normalize_feedback_issues,
    short_text_hash,
)
from ogp_web.services.point3_pipeline import (
    MODE_FACTUAL_FALLBACK_EXPANDED,
    apply_validation_remediation,
    build_point3_pipeline_context,
    load_policy_thresholds,
)
from ogp_web.services.law_retrieval_service import retrieve_law_context, unique_sources
from shared.ogp_ai import (
    AiUsageSummary,
    OPENAI_TEXT_MODEL,
    TextGenerationResult,
    create_openai_client,
    extract_response_text,
    extract_response_usage,
    extract_principal_fields_with_proxy_fallback,
    suggest_description_with_proxy_fallback_result,
)
from shared.ogp_ai_prompts import SUGGEST_PROMPT_VERSION, build_suggest_prompt

LOGGER = logging.getLogger(__name__)
LAW_QA_PROMPT_VERSION = "law_qa.v2"


_LawChunk = LawChunk


@dataclass(frozen=True)
class LawQaAnswerResult:
    text: str
    generation_id: str
    used_sources: list[str]
    indexed_documents: int
    retrieval_confidence: str
    retrieval_profile: str
    guard_status: str
    contract_version: str
    bundle_status: str
    bundle_generated_at: str
    bundle_fingerprint: str
    warnings: list[str]
    shadow: dict[str, object]
    selected_norms: list[dict[str, object]]
    telemetry: dict[str, object]
    budget_status: str
    budget_warnings: list[str]
    budget_policy: dict[str, object]


@dataclass(frozen=True)
class SuggestTextResult:
    text: str
    generation_id: str
    guard_status: str
    contract_version: str
    warnings: list[str]
    shadow: dict[str, object]
    telemetry: dict[str, object]
    budget_status: str
    budget_warnings: list[str]
    budget_policy: dict[str, object]
    retrieval_ms: int
    openai_ms: int
    total_suggest_ms: int
    prompt_mode: str
    retrieval_confidence: str
    retrieval_context_mode: str
    retrieval_profile: str
    bundle_status: str
    bundle_generated_at: str
    bundle_fingerprint: str
    selected_norms_count: int
    policy_mode: str = ""
    policy_reason: str = ""
    valid_triggers_count: int = 0
    avg_trigger_confidence: float = 0.0
    remediation_retries: int = 0
    safe_fallback_used: bool = False
    input_warning_codes: tuple[str, ...] = ()
    protected_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class SuggestContextBuildResult:
    context_text: str
    retrieval_confidence: str
    retrieval_context_mode: str
    retrieval_profile: str
    bundle_status: str
    bundle_generated_at: str
    bundle_fingerprint: str
    selected_norms_count: int
    selected_norms: tuple[dict[str, object], ...] = ()


def normalize_ai_feedback_issues(raw_issues: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return normalize_feedback_issues(raw_issues)


LAW_QA_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "by",
    "for",
    "from",
    "how",
    "if",
    "in",
    "is",
    "of",
    "or",
    "that",
    "the",
    "then",
    "what",
    "when",
    "where",
    "which",
    "with",
    "без",
    "вопрос",
    "для",
    "его",
    "ее",
    "ему",
    "если",
    "или",
    "как",
    "когда",
    "кто",
    "ли",
    "лица",
    "лицо",
    "мне",
    "можно",
    "надо",
    "нет",
    "нужно",
    "него",
    "нее",
    "них",
    "оно",
    "они",
    "она",
    "про",
    "просто",
    "считается",
    "стат",
    "стать",
    "статей",
    "статье",
    "статьи",
    "статью",
    "статьям",
    "статья",
    "тогда",
    "это",
    "этого",
}
LAW_QA_SHORT_TERMS = {"ук", "пк", "ак", "дк", "огп", "фбр", "lspd", "lssd"}
LAW_QA_STEM_SUFFIXES = (
    "иями",
    "ями",
    "ами",
    "иями",
    "ости",
    "ение",
    "ения",
    "енией",
    "ению",
    "енного",
    "енного",
    "ировать",
    "ировать",
    "ющего",
    "ющая",
    "яющие",
    "яющая",
    "яющий",
    "овать",
    "ировать",
    "ность",
    "ности",
    "иями",
    "ение",
    "ений",
    "енного",
    "ания",
    "ение",
    "ении",
    "анием",
    "овать",
    "ировать",
    "аться",
    "яться",
    "ение",
    "ения",
    "иями",
    "ыми",
    "ими",
    "ого",
    "его",
    "ому",
    "ему",
    "ыми",
    "ими",
    "ать",
    "ять",
    "ить",
    "еть",
    "ать",
    "ять",
    "ить",
    "еть",
    "ого",
    "ему",
    "ому",
    "ия",
    "ий",
    "ие",
    "иям",
    "иях",
    "ов",
    "ев",
    "ах",
    "ях",
    "ой",
    "ей",
    "ом",
    "ем",
    "ам",
    "ям",
    "ы",
    "и",
    "а",
    "я",
    "у",
    "ю",
    "е",
    "о",
)
LAW_QA_PHRASE_ALIASES: dict[str, tuple[str, ...]] = {
    "не считается преступлением": (
        "обстоятельства исключающие преступность деяния",
        "уголовный кодекс",
        "исключают преступность деяния",
    ),
    "что не считается преступлением": (
        "обстоятельства исключающие преступность деяния",
        "уголовный кодекс",
    ),
    "какие обстоятельства исключают преступность деяния": (
        "обстоятельства исключающие преступность деяния",
        "уголовный кодекс",
    ),
    "обязаны отпустить": (
        "освобождение задержанного",
        "основания освобождения задержанного",
    ),
    "после задержания": (
        "освобождение задержанного",
        "задержанный",
    ),
    "освобождение задержанного": (
        "статья 20",
        "процессуальный кодекс",
    ),
    "по ук": ("уголовный кодекс",),
    "по пк": ("процессуальный кодекс",),
    "по ак": ("административный кодекс",),
    "по дк": ("дорожный кодекс",),
    "сумма залога": (
        "залог",
        "санкция",
        "статья 14",
    ),
    "как считается залог": (
        "сумма залога",
        "санкция",
        "статья 14",
    ),
    "по нескольким административным статьям": (
        "административный кодекс",
        "залог",
        "несколько статей",
        "статья 14",
    ),
}
LAW_QA_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "освобождение": ("освободить", "освобождения", "выпустить", "отпустить", "release"),
    "задержанный": ("задержание", "задержанного", "detention", "detainee", "удержание"),
    "основания": ("условия", "случаи", "поводы", "когда"),
    "адвокат": ("защитник", "защита"),
    "обыск": ("досмотр", "осмотр"),
    "залог": ("залога", "bail"),
    "санкция": ("наказание", "размер", "сумма"),
    "преступность": ("преступления", "уголовный", "уголовного"),
    "преступление": ("преступления", "преступностью", "уголовное"),
    "исключают": ("исключается", "исключающие", "исключение"),
    "деяние": ("действие", "бездействие"),
    "ук": ("уголовный", "уголовного", "уголовный кодекс"),
    "пк": ("процессуальный", "процессуального", "процессуальный кодекс"),
    "ак": ("административный", "административного", "административный кодекс"),
    "дк": ("дорожный", "дорожного", "дорожный кодекс"),
}

def _humanize_ai_exception(exc: Exception) -> str:
    raw = str(exc).strip() or exc.__class__.__name__
    lower = raw.lower()

    if "capacity" in lower or "overloaded" in lower:
        return "Выбранная модель сейчас перегружена. Попробуйте еще раз чуть позже или переключите модель."
    if "model" in lower and ("not found" in lower or "does not exist" in lower):
        return "Указанная модель недоступна для этого аккаунта или не существует."
    if "api key" in lower or "invalid_api_key" in lower or "incorrect api key" in lower:
        return "Проблема с OpenAI API key. Проверьте переменную окружения OPENAI_API_KEY на сервере."
    if "timeout" in lower:
        return "Запрос к OpenAI превысил время ожидания. Попробуйте еще раз."
    if "connection" in lower or "network" in lower:
        return "Не удалось подключиться к OpenAI. Проверьте сеть и настройки прокси."
    return f"Не удалось получить ответ от модели: {raw}"


def _ai_exception_details(exc: Exception) -> list[str]:
    raw = str(exc).strip() or repr(exc)
    details = [_humanize_ai_exception(exc), f"Тип ошибки: {exc.__class__.__name__}"]
    if raw != details[0]:
        details.append(f"Полная ошибка OpenAI: {raw}")
    return details


def get_law_qa_model_choices() -> tuple[str, ...]:
    raw = os.getenv("OPENAI_LAW_QA_MODELS", "").strip()
    if raw:
        values = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
        if values:
            return values
    return ("gpt-5.4-mini",)


def get_default_law_qa_model() -> str:
    configured = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.4-mini").strip() or "gpt-5.4-mini"
    choices = get_law_qa_model_choices()
    if configured in choices:
        return configured
    return choices[0]


def resolve_law_qa_model(requested_model: str) -> str:
    _ = requested_model
    return get_default_law_qa_model()
    normalized = str(requested_model or "").strip()
    if not normalized:
        return get_default_law_qa_model()
    allowed = set(get_law_qa_model_choices())
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Выбрана неподдерживаемая модель для поиска по законодательной базе."],
        )
    return normalized


class _LawHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._ignored_tag_depth = 0

    @property
    def text(self) -> str:
        merged = " ".join(chunk.strip() for chunk in self._chunks if chunk and chunk.strip())
        return re.sub(r"\s+", " ", merged).strip()

    def handle_starttag(self, tag: str, attrs) -> None:
        _ = attrs
        if tag.lower() in {"script", "style", "noscript", "template"}:
            self._ignored_tag_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "template"} and self._ignored_tag_depth > 0:
            self._ignored_tag_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_tag_depth > 0:
            return
        if data:
            self._chunks.append(data)


def _clean_law_document_text(text: str) -> str:
    normalized = str(text or "")
    garbage_patterns = (
        r"XF\.ready\s*\(\s*\(\)\s*=>.*?(?=Статья|\bГлава\b|\bРаздел\b|\bВажно\b|$)",
        r"XF\.extendObject\s*\(.*?(?=Статья|\bГлава\b|\bРаздел\b|\bВажно\b|$)",
        r"cookie:\s*\{.*?\}",
        r"visitorCounts:\s*\{.*?\}",
        r"jsMt:\s*\{.*?\}",
        r"short_date_x_minutes:\s*['\"{].*?['\"}]",
    )
    for pattern in garbage_patterns:
        normalized = re.sub(pattern, " ", normalized, flags=re.IGNORECASE | re.DOTALL)
    normalized = re.sub(
        r"\b(?:XF|css\.php|keep-alive|pushAppServerKey|publicPushBadgeUrl)\b.*",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _tokenize_normalized_text(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in str(text or "").split():
        normalized = token.strip()
        if not normalized:
            continue
        if len(normalized) >= 3 or normalized in LAW_QA_SHORT_TERMS:
            tokens.append(normalized)
    return tuple(dict.fromkeys(tokens))


def _stem_law_token(token: str) -> str:
    normalized = str(token or "").strip().lower()
    if len(normalized) <= 4:
        return normalized
    for suffix in LAW_QA_STEM_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 4:
            return normalized[: -len(suffix)]
    return normalized


@lru_cache(maxsize=32768)
def _token_similarity(left: str, right: str) -> float:
    normalized_left = _normalize_law_text(left)
    normalized_right = _normalize_law_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0

    left_stem = _stem_law_token(normalized_left)
    right_stem = _stem_law_token(normalized_right)
    if left_stem and left_stem == right_stem:
        return 0.96
    if normalized_left in normalized_right or normalized_right in normalized_left:
        shorter, longer = sorted((normalized_left, normalized_right), key=len)
        if len(shorter) >= 4:
            return max(len(shorter) / max(len(longer), 1), 0.88)
    if abs(len(normalized_left) - len(normalized_right)) > 4:
        return 0.0
    if normalized_left[:1] != normalized_right[:1] and left_stem[:2] != right_stem[:2]:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _best_token_similarity(term: str, candidates: tuple[str, ...]) -> float:
    normalized_term = _normalize_law_text(term)
    if not normalized_term or not candidates:
        return 0.0
    return max((_token_similarity(normalized_term, candidate) for candidate in candidates), default=0.0)


def _extract_keywords(question: str) -> set[str]:
    return {
        token
        for token in _tokenize_normalized_text(_normalize_law_text(question))
        if token not in LAW_QA_STOPWORDS and (len(token) >= 4 or token in LAW_QA_SHORT_TERMS)
    }


def _normalize_law_text(text: str) -> str:
    normalized = str(text or "").lower().replace("ё", "е")
    normalized = re.sub(r"[^\w\s]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized, flags=re.UNICODE).strip()

def _extract_article_numbers(question: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            match
            for match in re.findall(r"(?:article|ст\.?|статья)\s*(\d{1,3})", str(question or ""), flags=re.IGNORECASE)
            if match
        )
    )


def _expand_question_terms(question: str) -> set[str]:
    normalized_question = _normalize_law_text(question)
    tokens = {
        token
        for token in _tokenize_normalized_text(normalized_question)
        if token not in LAW_QA_STOPWORDS
    }
    expanded = set(tokens)

    for phrase, aliases in LAW_QA_PHRASE_ALIASES.items():
        normalized_phrase = _normalize_law_text(phrase)
        phrase_tokens = tuple(token for token in _tokenize_normalized_text(normalized_phrase) if token not in LAW_QA_STOPWORDS)
        matched = normalized_phrase in normalized_question
        if not matched and phrase_tokens:
            present = sum(1 for token in phrase_tokens if token in tokens)
            required = len(phrase_tokens) if len(phrase_tokens) <= 2 else len(phrase_tokens) - 1
            matched = present >= required
        if matched:
            for item in (phrase, *aliases):
                expanded.update(_tokenize_normalized_text(_normalize_law_text(item)))

    for token in list(tokens):
        token_stem = _stem_law_token(token)
        for key, aliases in LAW_QA_QUERY_ALIASES.items():
            alias_tokens = {
                alias_token
                for item in (key, *aliases)
                for alias_token in _tokenize_normalized_text(_normalize_law_text(item))
            }
            if not alias_tokens:
                continue
            if token in alias_tokens or (token_stem and token_stem in {_stem_law_token(alias) for alias in alias_tokens}):
                expanded.update(alias_tokens)
                continue
            if _best_token_similarity(token, tuple(alias_tokens)) >= 0.86:
                expanded.update(alias_tokens)

    expanded_with_stems = set(expanded)
    for item in list(expanded):
        stem = _stem_law_token(item)
        if stem and len(stem) >= 4:
            expanded_with_stems.add(stem)
    return {
        item
        for item in expanded_with_stems
        if item and item not in LAW_QA_STOPWORDS and (len(item) >= 3 or item in LAW_QA_SHORT_TERMS)
    }


@lru_cache(maxsize=4096)
def _chunk_search_payload(chunk: _LawChunk) -> tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    normalized_title = _normalize_law_text(chunk.document_title)
    normalized_label = _normalize_law_text(chunk.article_label)
    normalized_text = _normalize_law_text(f"{chunk.document_title} {chunk.article_label} {chunk.text}")
    title_tokens = _tokenize_normalized_text(normalized_title)
    label_tokens = _tokenize_normalized_text(normalized_label)
    text_tokens = _tokenize_normalized_text(normalized_text)
    title_stems = tuple(dict.fromkeys(_stem_law_token(token) for token in title_tokens if len(_stem_law_token(token)) >= 4))
    label_stems = tuple(dict.fromkeys(_stem_law_token(token) for token in label_tokens if len(_stem_law_token(token)) >= 4))
    text_stems = tuple(dict.fromkeys(_stem_law_token(token) for token in text_tokens if len(_stem_law_token(token)) >= 4))
    return normalized_text, normalized_label, title_tokens, label_tokens, text_tokens, title_stems, label_stems, text_stems

def _extract_document_title(text: str, url: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return url
    article_match = re.search(r"(?i)(?:article|ст\.?|статья)\s*\d{1,3}", normalized)
    if article_match:
        candidate = normalized[: article_match.start()].strip(" :-")
        if candidate:
            return candidate[:160]
    return normalized[:160].rsplit(" ", 1)[0].strip() or url


def _split_law_document_into_chunks(document: dict[str, str]) -> list[_LawChunk]:
    text = str(document.get("text") or "").strip()
    url = str(document.get("url") or "").strip()
    if not text:
        return []

    title = _extract_document_title(text, url)
    article_pattern = r"(?i)(?:article|статья)\s*\d{1,3}(?:\.\d+)?(?:\s*[^.\n\r]{0,160})?\."
    article_matches = list(re.finditer(article_pattern, text))
    if not article_matches:
        return [_LawChunk(url=url, document_title=title, article_label="general", text=text[:4000].strip())]

    chunks: list[_LawChunk] = []
    for index, match in enumerate(article_matches):
        start = match.start()
        end = article_matches[index + 1].start() if index + 1 < len(article_matches) else len(text)
        chunk_text = text[start:end].strip()
        article_label = re.sub(r"\s+", " ", match.group(0)).strip(" .:-")[:120]
        if chunk_text:
            chunks.append(
                _LawChunk(
                    url=url,
                    document_title=title,
                    article_label=article_label or "article",
                    text=chunk_text[:5000].strip(),
                )
            )
    return chunks or [_LawChunk(url=url, document_title=title, article_label="general", text=text[:4000].strip())]


def _score_law_chunk(chunk: _LawChunk, question: str) -> int:
    (
        normalized_text,
        normalized_label,
        title_tokens,
        label_tokens,
        text_tokens,
        title_stems,
        label_stems,
        text_stems,
    ) = _chunk_search_payload(chunk)
    terms = _expand_question_terms(question)
    score = 0

    code_hint_tokens = {
        token
        for token in terms
        if token
        in {
            "ук",
            "пк",
            "ак",
            "дк",
            "уголовный",
            "уголовного",
            "процессуальный",
            "процессуального",
            "административный",
            "административного",
            "дорожный",
            "дорожного",
            "кодекс",
        }
    }
    if code_hint_tokens:
        score += sum(1 for token in code_hint_tokens if token in title_tokens) * 12
        score += sum(1 for token in code_hint_tokens if _stem_law_token(token) in title_stems) * 6

    for term in terms:
        if not term:
            continue
        term_stem = _stem_law_token(term)
        if term in label_tokens:
            score += 20
        elif term_stem and term_stem in label_stems:
            score += 12
        else:
            label_similarity = _best_token_similarity(term, label_tokens)
            if label_similarity >= 0.92:
                score += 12
            elif label_similarity >= 0.86:
                score += 8

        if term in text_tokens:
            score += 10
        elif term_stem and term_stem in text_stems:
            score += 6
        else:
            text_similarity = _best_token_similarity(term, text_tokens)
            if text_similarity >= 0.92:
                score += 6
            elif text_similarity >= 0.86:
                score += 3

        if f" {term} " in f" {normalized_text} ":
            score += 3
        elif term in normalized_text:
            score += 1

    for article_number in _extract_article_numbers(question):
        article_pattern = rf"(?i)(?:article|ст\.?|статья)\s*{re.escape(article_number)}(?:\.\d+)?\b"
        if re.search(article_pattern, normalized_label):
            score += 55
        elif re.search(article_pattern, normalized_text):
            score += 40

    if terms:
        matched_terms = sum(
            1
            for term in terms
            if term in text_tokens
            or term in label_tokens
            or (len(term) >= 5 and _best_token_similarity(term, text_tokens + label_tokens + title_tokens) >= 0.86)
        )
        score += matched_terms * 2
        if matched_terms >= max(2, min(4, len(terms) // 3 or 1)):
            score += 8
    return score


def _cheap_score_law_chunk(chunk: _LawChunk, question: str) -> int:
    (
        normalized_text,
        normalized_label,
        title_tokens,
        label_tokens,
        text_tokens,
        title_stems,
        label_stems,
        text_stems,
    ) = _chunk_search_payload(chunk)
    terms = _expand_question_terms(question)
    score = 0

    code_hint_tokens = {
        token
        for token in terms
        if token
        in {
            "СѓРє",
            "РїРє",
            "Р°Рє",
            "РґРє",
            "СѓРіРѕР»РѕРІРЅС‹Р№",
            "СѓРіРѕР»РѕРІРЅРѕРіРѕ",
            "РїСЂРѕС†РµСЃСЃСѓР°Р»СЊРЅС‹Р№",
            "РїСЂРѕС†РµСЃСЃСѓР°Р»СЊРЅРѕРіРѕ",
            "Р°РґРјРёРЅРёСЃС‚СЂР°С‚РёРІРЅС‹Р№",
            "Р°РґРјРёРЅРёСЃС‚СЂР°С‚РёРІРЅРѕРіРѕ",
            "РґРѕСЂРѕР¶РЅС‹Р№",
            "РґРѕСЂРѕР¶РЅРѕРіРѕ",
            "РєРѕРґРµРєСЃ",
        }
    }
    if code_hint_tokens:
        score += sum(1 for token in code_hint_tokens if token in title_tokens) * 10
        score += sum(1 for token in code_hint_tokens if _stem_law_token(token) in title_stems) * 5

    for term in terms:
        if not term:
            continue
        term_stem = _stem_law_token(term)
        if term in label_tokens:
            score += 14
        elif term_stem and term_stem in label_stems:
            score += 8

        if term in title_tokens:
            score += 8
        elif term_stem and term_stem in title_stems:
            score += 4

        if term in text_tokens:
            score += 6
        elif term_stem and term_stem in text_stems:
            score += 3

        if f" {term} " in f" {normalized_text} ":
            score += 2
        elif term in normalized_label:
            score += 1

    for article_number in _extract_article_numbers(question):
        article_pattern = rf"(?i)(?:article|СЃС‚\.?|СЃС‚Р°С‚СЊСЏ)\s*{re.escape(article_number)}(?:\.\d+)?\b"
        if re.search(article_pattern, normalized_label):
            score += 42
        elif re.search(article_pattern, normalized_text):
            score += 28

    if terms:
        matched_terms = sum(
            1
            for term in terms
            if term in text_tokens or term in label_tokens or term in title_tokens or (_stem_law_token(term) in text_stems)
        )
        score += matched_terms * 2
        if matched_terms >= max(2, min(4, len(terms) // 3 or 1)):
            score += 6
    return score


def _classify_law_qa_confidence(scores: list[int], question: str) -> str:
    if not scores:
        return "low"
    top = scores[0]
    nonzero = sum(1 for score in scores if score > 0)
    terms = _expand_question_terms(question)
    article_numbers = _extract_article_numbers(question)
    if article_numbers and top >= 40:
        return "high"
    if top >= 48 and nonzero >= 3:
        return "high"
    if top >= 26 and (nonzero >= 2 or len(terms) <= 4):
        return "medium"
    return "low"


def _select_law_qa_chunks(chunks: list[_LawChunk], question: str, profile: str = "law_qa") -> tuple[list[_LawChunk], str]:
    scored = [(item, _cheap_score_law_chunk(item, question)) for item in chunks]
    ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)
    positive = [item for item, score in ranked if score > 0]
    confidence = _classify_law_qa_confidence([score for _, score in ranked], question)
    if str(profile or "law_qa").strip().lower() == "suggest":
        target_count = {"high": 8, "medium": 7, "low": 6}.get(confidence, 7)
        fallback_count = 4
    else:
        target_count = {"high": 12, "medium": 14, "low": 16}.get(confidence, 14)
        fallback_count = 6
    selected = positive[:target_count] or [item for item, _ in ranked[:fallback_count]]
    return selected, confidence


@lru_cache(maxsize=16)
def _build_law_chunk_index_cached(source_urls: tuple[str, ...]) -> tuple[_LawChunk, ...]:
    documents = _fetch_law_documents(list(source_urls))
    chunks: list[_LawChunk] = []
    for document in documents:
        chunks.extend(_split_law_document_into_chunks(document))
    return tuple(chunks)


def _is_blocked_law_host(host: str) -> bool:
    normalized = (host or "").strip().strip(".").lower()
    if not normalized:
        return True
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    if normalized.endswith(".local"):
        return True
    try:
        resolved = socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
    except OSError:
        return True
    for _, _, _, _, sockaddr in resolved:
        ip_raw = str(sockaddr[0]).split("%", 1)[0]
        try:
            addr = ip_address(ip_raw)
        except ValueError:
            continue
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        ):
            return True
    return False


def _fetch_law_documents(source_urls: list[str], *, max_documents: int = 24, max_doc_chars: int = 120000) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    normalized_sources: list[str] = []

    for source_url in source_urls:
        parsed_source = urlparse(source_url)
        if parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc:
            continue
        if _is_blocked_law_host(parsed_source.hostname or ""):
            continue
        normalized_sources.append(source_url)

    if not normalized_sources:
        return documents

    with httpx.Client(timeout=8.0, follow_redirects=True) as client:
        for current in normalized_sources[:max_documents]:
            try:
                response = client.get(current)
                response.raise_for_status()
            except Exception:
                continue
            content_type = (response.headers.get("content-type") or "").lower()
            if "text/html" not in content_type:
                continue
            parser = _LawHtmlParser()
            parser.feed(response.text)
            text = _clean_law_document_text(parser.text)[:max_doc_chars].strip()
            if text:
                documents.append({"url": current, "text": text})
    return documents


def _extract_relevant_law_excerpt(text: str, question: str, *, max_chars: int = 2500) -> str:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return ""
    if len(normalized_text) <= max_chars:
        return normalized_text

    direct_keywords = sorted(_extract_keywords(question), key=len, reverse=True)
    expanded_keywords = sorted((_expand_question_terms(question) - set(direct_keywords)), key=len, reverse=True)
    keywords = direct_keywords + expanded_keywords
    if not keywords:
        return normalized_text[:max_chars].strip()

    lower_text = normalized_text.lower()
    hit_positions: list[int] = []
    for keyword in keywords[:12]:
        index = lower_text.find(keyword.lower())
        if index >= 0:
            hit_positions.append(index)

    article_matches = re.findall(r"(?:ст\.?|статья)\s*(\d{1,3})", question, flags=re.IGNORECASE)
    for article_number in article_matches[:3]:
        article_pattern = re.search(rf"(ст\.?|статья)\s*{re.escape(article_number)}", lower_text, flags=re.IGNORECASE)
        if article_pattern:
            hit_positions.append(article_pattern.start())

    if not hit_positions:
        return normalized_text[:max_chars].strip()

    anchor = min(hit_positions)
    radius = max_chars // 2
    start = max(0, anchor - radius)
    end = min(len(normalized_text), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)

    snippet = normalized_text[start:end].strip()
    if start > 0:
        snippet = "... " + snippet
    if end < len(normalized_text):
        snippet = snippet + " ..."
    return snippet


def _build_law_qa_prompt(
    *,
    server_name: str,
    server_code: str,
    model_name: str,
    question: str,
    max_answer_chars: int,
    context_blocks: list[str],
    retrieval_confidence: str,
) -> str:
    confidence_guidance = {
        "high": "Уверенность в подборе норм высокая: отвечай прямо, но только в пределах переданного корпуса.",
        "medium": "Уверенность в подборе норм средняя: если есть сомнение между нормами или формулировками, коротко обозначь его и не достраивай выводы.",
        "low": "Уверенность в подборе норм низкая: избегай категоричности; если прямого подтверждения нет, прямо скажи, что данных недостаточно.",
    }.get(retrieval_confidence, "Уверенность в подборе норм не определена.")
    return (
        f"Ты юридический ассистент игрового сервера {server_name} ({server_code}).\n"
        "Отвечай только по переданным внутриигровым нормам.\n\n"
        "Правила:\n"
        "1. Не используй реальные законы, внешнюю судебную практику или фоновые знания из реального мира.\n"
        "2. Не додумывай нормы по аналогии. Если прямого основания нет, так и напиши.\n"
        "3. Если вопрос содержит неверную предпосылку, смешивает кодексы или не подтверждается переданными нормами, укажи это в первой фразе.\n"
        "4. Если вопрос задан разговорно, с опечатками или перефразированием, трактуй его только по ближайшему смыслу внутри переданных норм.\n"
        "5. Если вопрос требует перечисления, перечисляй только прямо подтвержденные элементы.\n"
        "6. В конце каждого смыслового абзаца указывай ссылки на использованные источники в формате [Источник: URL].\n"
        "7. Ответ должен быть точным, прикладным, без воды и не длиннее заданного лимита.\n"
        f"8. {confidence_guidance}\n\n"
        "Формат ответа:\n"
        "- Сначала дай прямой вывод по вопросу.\n"
        "- Затем коротко приведи правовое основание: статья, кодекс и смысл нормы.\n"
        "- Если данных недостаточно, скажи это прямо без догадок.\n\n"
        f"Лимит ответа: не более {max_answer_chars} символов.\n"
        f"Модель: {model_name}\n\n"
        f"Вопрос:\n{question}\n\n"
        "Нормы:\n"
        + "\n\n".join(context_blocks)
    )


def _response_diagnostics(response: object) -> str:
    output_items = []
    for output_item in getattr(response, "output", None) or []:
        item_type = str(getattr(output_item, "type", "") or "")
        content_types = []
        for content_item in getattr(output_item, "content", None) or []:
            content_types.append(str(getattr(content_item, "type", "") or "unknown"))
        output_items.append(f"{item_type}({','.join(content_types)})" if content_types else item_type or "unknown")
    status_value = str(getattr(response, "status", "") or "")
    output_text = str(getattr(response, "output_text", "") or "")
    return (
        f"status={status_value or 'n/a'}; "
        f"output_text_len={len(output_text.strip())}; "
        f"items={output_items or ['none']}"
    )


def _is_context_window_error(exc: Exception) -> bool:
    raw = str(exc or "").strip().lower()
    return (
        "context_length_exceeded" in raw
        or "context window" in raw
        or "maximum context length" in raw
        or ("input exceeds" in raw and "context" in raw)
    )


def _truncate_law_excerpt(text: str, *, max_chars: int) -> str:
    normalized = str(text or "").strip()
    if max_chars <= 0 or len(normalized) <= max_chars:
        return normalized
    head = normalized[: max_chars + 1]
    split_index = head.rfind(" ")
    if split_index < max(0, int(max_chars * 0.6)):
        split_index = max_chars
    return head[:split_index].rstrip(" ,;:-") + "..."


def _build_law_qa_context_blocks_limited(
    retrieval_result,
    *,
    max_blocks: int,
    max_excerpt_chars: int,
) -> list[str]:
    context_blocks: list[str] = []
    for match in retrieval_result.matches[: max(1, int(max_blocks))]:
        excerpt = _truncate_law_excerpt(match.excerpt or match.chunk.text, max_chars=max_excerpt_chars)
        context_blocks.append(
            (
                f"[\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a: {match.chunk.url}]\n"
                f"[\u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442: {match.chunk.document_title}]\n"
                f"[\u041d\u043e\u0440\u043c\u0430: {match.chunk.article_label}]\n"
                f"{excerpt}"
            )
        )
    return context_blocks


def _request_law_qa_text(*, client, model_name: str, prompt: str, max_output_tokens: int) -> tuple[str, AiUsageSummary]:
    attempts = (
        prompt,
        prompt
        + "\n\nТехническое требование: верни непустой финальный текст ответа обычным текстом, без служебных блоков reasoning.",
    )
    diagnostics: list[str] = []

    for attempt_index, current_prompt in enumerate(attempts, start=1):
        response = client.responses.create(
            model=model_name,
            input=current_prompt,
            max_output_tokens=max_output_tokens,
        )
        text = extract_response_text(response)
        if text:
            return text, extract_response_usage(response)
        diagnostic = _response_diagnostics(response)
        diagnostics.append(diagnostic)
        LOGGER.warning(
            "Law QA model returned empty text on attempt %s for model %s. %s",
            attempt_index,
            model_name,
            diagnostic,
        )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=[
            f"Модель {model_name} вернула пустой ответ даже после повторной попытки.",
            "Попробуйте отправить вопрос еще раз или выберите другую модель.",
        ],
    )


def _retrieve_law_context(*, server_code: str, query: str, excerpt_chars: int, profile: str = "law_qa"):
    return retrieve_law_context(
        server_code=server_code,
        query=query,
        excerpt_chars=excerpt_chars,
        profile=profile,
        get_server_config_func=get_server_config,
        load_law_bundle_chunks_func=load_law_bundle_chunks,
        build_law_chunk_index_func=_build_law_chunk_index_cached,
        select_chunks_func=_select_law_qa_chunks,
        score_chunk_func=_score_law_chunk,
        extract_excerpt_func=_extract_relevant_law_excerpt,
        default_server_code=DEFAULT_SERVER_CODE,
    )


def _build_law_qa_context_blocks(retrieval_result) -> list[str]:
    context_blocks: list[str] = []
    for match in retrieval_result.matches:
        excerpt = match.excerpt or match.chunk.text.strip()
        context_blocks.append(
            (
                f"[\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a: {match.chunk.url}]\n"
                f"[\u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442: {match.chunk.document_title}]\n"
                f"[\u041d\u043e\u0440\u043c\u0430: {match.chunk.article_label}]\n"
                f"{excerpt}"
            )
        )
    return context_blocks


def _build_law_qa_selected_norms(retrieval_result, *, max_excerpt_chars: int = 240) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for match in retrieval_result.matches:
        preview = str(match.excerpt or "").strip()
        if len(preview) > max_excerpt_chars:
            preview = preview[: max_excerpt_chars - 3].rstrip() + "..."
        items.append(
            {
                "source_url": match.chunk.url,
                "document_title": match.chunk.document_title,
                "article_label": match.chunk.article_label,
                "score": int(match.score),
                "excerpt_preview": preview,
            }
        )
    return items


def _server_feature_enabled(server_config: object, feature_name: str) -> bool:
    checker = getattr(server_config, "has_feature", None)
    if callable(checker):
        try:
            return bool(checker(feature_name))
        except Exception:
            return False
    feature_flags = getattr(server_config, "feature_flags", ()) or ()
    return str(feature_name or "").strip() in set(feature_flags)


def _shadow_to_dict(shadow: ShadowComparison) -> dict[str, object]:
    return {
        "enabled": bool(shadow.enabled),
        "profile": shadow.profile,
        "diverged": bool(shadow.diverged),
        "overlap_count": int(shadow.overlap_count),
        "primary_labels": list(shadow.primary_labels),
        "shadow_labels": list(shadow.shadow_labels),
    }


def _build_shadow_retrieval(
    *,
    server_code: str,
    query: str,
    excerpt_chars: int,
    profile: str,
    shadow_profile: str,
) -> ShadowComparison:
    normalized_shadow_profile = str(shadow_profile or "").strip()
    if not normalized_shadow_profile or normalized_shadow_profile == profile:
        return build_shadow_comparison(
            enabled=False,
            profile=normalized_shadow_profile,
            primary_matches=(),
            shadow_matches=(),
        )

    primary_result = _retrieve_law_context(
        server_code=server_code,
        query=query,
        excerpt_chars=excerpt_chars,
        profile=profile,
    )
    shadow_result = _retrieve_law_context(
        server_code=server_code,
        query=query,
        excerpt_chars=excerpt_chars,
        profile=normalized_shadow_profile,
    )
    return build_shadow_comparison(
        enabled=True,
        profile=normalized_shadow_profile,
        primary_matches=primary_result.matches,
        shadow_matches=shadow_result.matches,
    )


def _law_qa_metrics_meta(
    *,
    payload: LawQaPayload,
    result: LawQaAnswerResult,
    used_sources: list[str],
) -> dict[str, object]:
    return {
        "generation_id": result.generation_id,
        "flow": "law_qa",
        "contract_version": result.contract_version,
        "prompt_version": LAW_QA_PROMPT_VERSION,
        "server_code": payload.server_code,
        "model": payload.model,
        "input_chars": len(payload.question or ""),
        "input_hash": short_text_hash(payload.question or ""),
        "input_preview": mask_text_preview(payload.question or "", max_chars=180),
        "output_chars": len(result.text or ""),
        "output_hash": short_text_hash(result.text or ""),
        "output_preview": mask_text_preview(result.text or "", max_chars=220),
        "retrieval_profile": result.retrieval_profile,
        "retrieval_confidence": result.retrieval_confidence,
        "bundle_status": result.bundle_status,
        "bundle_generated_at": result.bundle_generated_at,
        "bundle_fingerprint": result.bundle_fingerprint,
        "guard_status": result.guard_status,
        "guard_warnings": list(result.warnings),
        "budget_status": result.budget_status,
        "budget_warnings": list(result.budget_warnings),
        "budget_policy": result.budget_policy,
        "used_sources_count": len(used_sources),
        "selected_norms_count": len(result.selected_norms),
        **result.telemetry,
        "shadow": result.shadow,
    }


def _suggest_metrics_meta(
    *,
    payload: SuggestPayload,
    result: SuggestTextResult,
    server_code: str,
) -> dict[str, object]:
    prompt_mode = str(getattr(result, "prompt_mode", "legacy") or "legacy").strip().lower()
    retrieval_confidence = str(getattr(result, "retrieval_confidence", "medium") or "medium").strip().lower()
    retrieval_context_mode = str(getattr(result, "retrieval_context_mode", "normal_context") or "normal_context").strip()
    retrieval_profile = str(getattr(result, "retrieval_profile", "suggest") or "suggest").strip()
    bundle_status = str(getattr(result, "bundle_status", "unknown") or "unknown").strip()
    bundle_generated_at = str(getattr(result, "bundle_generated_at", "") or "").strip()
    bundle_fingerprint = str(getattr(result, "bundle_fingerprint", "") or "").strip()
    selected_norms_count = int(getattr(result, "selected_norms_count", 0) or 0)
    policy_mode = str(getattr(result, "policy_mode", "") or "").strip()
    policy_reason = str(getattr(result, "policy_reason", "") or "").strip()
    valid_triggers_count = int(getattr(result, "valid_triggers_count", 0) or 0)
    avg_trigger_confidence = float(getattr(result, "avg_trigger_confidence", 0.0) or 0.0)
    remediation_retries = int(getattr(result, "remediation_retries", 0) or 0)
    safe_fallback_used = bool(getattr(result, "safe_fallback_used", False))
    input_warning_codes = tuple(str(item or "").strip() for item in (getattr(result, "input_warning_codes", ()) or ()) if str(item or "").strip())
    protected_terms = tuple(str(item or "").strip() for item in (getattr(result, "protected_terms", ()) or ()) if str(item or "").strip())
    retrieval_ms = int(getattr(result, "retrieval_ms", 0) or 0)
    openai_ms = int(getattr(result, "openai_ms", 0) or 0)
    total_suggest_ms = int(getattr(result, "total_suggest_ms", 0) or 0)
    telemetry = dict(getattr(result, "telemetry", {}) or {})
    shadow = getattr(result, "shadow", {})
    return {
        "generation_id": result.generation_id,
        "flow": "suggest",
        "contract_version": result.contract_version,
        "prompt_version": SUGGEST_PROMPT_VERSION,
        "prompt_mode": prompt_mode,
        "server_code": server_code,
        "complaint_basis": payload.complaint_basis,
        "main_focus": payload.main_focus,
        "input_chars": len(payload.raw_desc or ""),
        "input_hash": short_text_hash(payload.raw_desc or ""),
        "input_preview": mask_text_preview(payload.raw_desc or "", max_chars=180),
        "output_chars": len(result.text or ""),
        "output_hash": short_text_hash(result.text or ""),
        "output_preview": mask_text_preview(result.text or "", max_chars=220),
        "guard_status": result.guard_status,
        "guard_warnings": list(result.warnings),
        "budget_status": result.budget_status,
        "budget_warnings": list(result.budget_warnings),
        "budget_policy": result.budget_policy,
        "retrieval_confidence": retrieval_confidence,
        "retrieval_context_mode": retrieval_context_mode,
        "retrieval_profile": retrieval_profile,
        "bundle_status": bundle_status,
        "bundle_generated_at": bundle_generated_at,
        "bundle_fingerprint": bundle_fingerprint,
        "selected_norms_count": selected_norms_count,
        "policy_mode": policy_mode,
        "policy_reason": policy_reason,
        "valid_triggers_count": valid_triggers_count,
        "avg_trigger_confidence": avg_trigger_confidence,
        "remediation_retries": remediation_retries,
        "safe_fallback_used": safe_fallback_used,
        "input_warning_codes": list(input_warning_codes),
        "protected_terms": list(protected_terms),
        "retrieval_ms": retrieval_ms,
        "openai_ms": openai_ms,
        "total_suggest_ms": total_suggest_ms,
        **telemetry,
        "shadow": shadow,
    }


def build_law_qa_metrics_meta(*, payload: LawQaPayload, result: LawQaAnswerResult, used_sources: list[str]) -> dict[str, object]:
    return _law_qa_metrics_meta(payload=payload, result=result, used_sources=used_sources)


def build_suggest_metrics_meta(*, payload: SuggestPayload, result: SuggestTextResult, server_code: str) -> dict[str, object]:
    return _suggest_metrics_meta(payload=payload, result=result, server_code=server_code)


def _normalize_suggest_inline(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


_SUGGEST_MASK_TERMS = ("маск", "маскиров", "визор", "капюшон")
_SUGGEST_ENTERTAINMENT_TERMS = (
    "maze bank arena",
    "арена",
    "развлекатель",
    "увеселит",
    "казино",
    "клуб",
    "бар",
)
_SUGGEST_TICKET_SANCTION_TERMS = ("штраф", "тикет")
_SUGGEST_GENERIC_SECONDARY_PROCESSUAL_ARTICLES = {"20", "39", "59"}


_SUGGEST_QUALIFIER_PATTERNS = (
    ("exception", re.compile(r"\bИсключени(?:е|я)\s*:?", flags=re.IGNORECASE)),
    ("note", re.compile(r"\bПримечани(?:е|я)(?:\s+к\s+(?:ч\.?|част[ьи])\s*\d+)?\s*:?", flags=re.IGNORECASE)),
    ("comment", re.compile(r"\bКомментар(?:ий|ии)(?:\s+[IVXLC\d]+)?\s*:?", flags=re.IGNORECASE)),
    ("clarification", re.compile(r"\b(?:Пояснение|Разъяснение)\s*:?", flags=re.IGNORECASE)),
)
_SUGGEST_CROSS_REF_PATTERN = re.compile(
    r"\b(?:ст\.?|стат(?:ья|ьи|ье|ею))\s*\d+(?:\.\d+)?(?:\s*(?:ч\.?|част[ьи])\s*\d+)?(?:\s*(?:п\.?|пункт)\s*[\"«]?[a-zа-яё0-9-]+[\"»]?)?",
    flags=re.IGNORECASE,
)


def _extract_suggest_norm_cross_refs(
    text: str,
    *,
    article_label: str = "",
    max_items: int = 6,
) -> tuple[str, ...]:
    normalized_text = _normalize_suggest_inline(text)
    normalized_article = _normalize_suggest_inline(article_label).lower()
    refs: list[str] = []
    seen: set[str] = set()
    for match in _SUGGEST_CROSS_REF_PATTERN.finditer(normalized_text):
        ref_text = _normalize_suggest_inline(match.group(0))
        ref_key = ref_text.lower()
        if not ref_text or ref_key == normalized_article or ref_key in seen:
            continue
        seen.add(ref_key)
        refs.append(ref_text)
        if len(refs) >= max_items:
            break
    return tuple(refs)


def _extract_suggest_norm_qualifiers(
    text: str,
    *,
    article_label: str = "",
    max_items: int = 6,
    max_chars: int = 360,
) -> tuple[dict[str, object], ...]:
    normalized_text = _normalize_suggest_inline(text)
    if not normalized_text:
        return ()

    matches: list[tuple[int, int, str]] = []
    for kind, pattern in _SUGGEST_QUALIFIER_PATTERNS:
        for match in pattern.finditer(normalized_text):
            matches.append((match.start(), match.end(), kind))
    if not matches:
        return ()

    matches.sort(key=lambda item: item[0])
    qualifiers: list[dict[str, object]] = []
    seen_sections: set[tuple[str, str]] = set()
    for index, (start, _, kind) in enumerate(matches):
        end = matches[index + 1][0] if index + 1 < len(matches) else len(normalized_text)
        section_text = _truncate_suggest_value(normalized_text[start:end].strip(" ,;"), max_chars=max_chars)
        if not section_text:
            continue
        section_key = (kind, section_text.lower())
        if section_key in seen_sections:
            continue
        seen_sections.add(section_key)
        qualifiers.append(
            {
                "kind": kind,
                "text": section_text,
                "related_refs": list(_extract_suggest_norm_cross_refs(section_text, article_label=article_label, max_items=4)),
            }
        )
        if len(qualifiers) >= max_items:
            break
    return tuple(qualifiers)


def _format_suggest_norm_sections(
    *,
    qualifiers: tuple[dict[str, object], ...] | list[dict[str, object]],
    cross_refs: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    lines: list[str] = []
    for qualifier in qualifiers:
        kind = str(qualifier.get("kind", "") or "").strip()
        text = str(qualifier.get("text", "") or "").strip()
        related_refs = tuple(
            str(ref or "").strip()
            for ref in (qualifier.get("related_refs", ()) or ())
            if str(ref or "").strip()
        )
        if not text:
            continue
        label = {
            "exception": "Исключение",
            "note": "Примечание",
            "comment": "Комментарий",
            "clarification": "Разъяснение",
        }.get(kind, "Квалифицирующий фрагмент")
        if text.lower().startswith(label.lower()):
            lines.append(text)
        else:
            lines.append(f"{label}: {text}")
        if related_refs:
            lines.append(f"Связанные нормы: {', '.join(related_refs)}")
    normalized_cross_refs = tuple(str(ref or "").strip() for ref in cross_refs if str(ref or "").strip())
    if normalized_cross_refs:
        lines.append(f"Перекрестные ссылки (supporting only): {', '.join(normalized_cross_refs)}")
    return tuple(lines)


def _suggest_document_priority_weight(document_title: str) -> int:
    thresholds = load_policy_thresholds()
    priority_config = thresholds.get("document_priority", {})
    default_weight = int(priority_config.get("default_weight", 0) or 0)
    normalized_title = _normalize_suggest_inline(document_title).lower()
    for group in priority_config.get("groups", []):
        patterns = tuple(str(item or "").strip().lower() for item in group.get("patterns", ()) if str(item or "").strip())
        if normalized_title and any(pattern in normalized_title for pattern in patterns):
            return int(group.get("weight", default_weight) or default_weight)
    return default_weight


def _suggest_document_group_key(document_title: str) -> str:
    thresholds = load_policy_thresholds()
    normalized_title = _normalize_suggest_inline(document_title).lower()
    for group in thresholds.get("document_priority", {}).get("groups", []):
        patterns = tuple(str(item or "").strip().lower() for item in group.get("patterns", ()) if str(item or "").strip())
        if normalized_title and any(pattern in normalized_title for pattern in patterns):
            return str(group.get("key", "") or "").strip()
    return ""


def _suggest_document_is_applicable(document_title: str, query: str) -> bool:
    group_key = _suggest_document_group_key(document_title)
    if group_key != "judicial_system_law":
        return True
    court_terms = load_policy_thresholds().get("document_priority", {}).get("court_proceedings_terms", ())
    normalized_query = _normalize_suggest_inline(query).lower()
    return any(
        str(term or "").strip().lower() in normalized_query
        for term in court_terms
        if str(term or "").strip()
    )


def _suggest_is_mask_exception_case(text: str) -> bool:
    normalized_text = _normalize_suggest_inline(text).lower()
    return any(term in normalized_text for term in _SUGGEST_MASK_TERMS) and any(
        term in normalized_text for term in _SUGGEST_ENTERTAINMENT_TERMS
    )


def _suggest_primary_article_number(norm_ref: str) -> str:
    numbers = re.findall(r"\b\d{1,4}(?:\.\d+)?\b", _normalize_suggest_inline(norm_ref))
    return numbers[0] if numbers else ""


def _suggest_norm_targets_mask_exception(document_title: str, article_label: str, excerpt: str) -> bool:
    combined = _normalize_suggest_inline(" ".join((document_title, article_label, excerpt))).lower()
    return (
        "статья 18" in combined
        and any(term in combined for term in _SUGGEST_MASK_TERMS)
        and any(term in combined for term in _SUGGEST_ENTERTAINMENT_TERMS)
    )


def _suggest_norm_targets_ticket_sanction(document_title: str, article_label: str, excerpt: str) -> bool:
    combined = _normalize_suggest_inline(" ".join((document_title, article_label, excerpt))).lower()
    return any(term in combined for term in _SUGGEST_TICKET_SANCTION_TERMS)


def _rerank_suggest_matches(matches, query: str):
    reranked = []
    mask_exception_case = _suggest_is_mask_exception_case(query)
    for match in matches:
        title = str(getattr(getattr(match, "chunk", None), "document_title", "") or "")
        article_label = str(getattr(getattr(match, "chunk", None), "article_label", "") or "")
        excerpt = str(getattr(match, "excerpt", "") or getattr(getattr(match, "chunk", None), "text", "") or "")
        adjusted_score = int(getattr(match, "score", 0) or 0) + _suggest_document_priority_weight(title)
        if not _suggest_document_is_applicable(title, query):
            adjusted_score -= 80
        if mask_exception_case:
            if _suggest_norm_targets_mask_exception(title, article_label, excerpt):
                adjusted_score += 45
            elif _suggest_norm_targets_ticket_sanction(title, article_label, excerpt):
                adjusted_score -= 45
        reranked.append((adjusted_score, match))
    reranked.sort(key=lambda item: item[0], reverse=True)
    return reranked


def _build_suggest_forced_norms(*, server_code: str, query: str) -> tuple[dict[str, object], ...]:
    if not _suggest_is_mask_exception_case(query):
        return ()
    try:
        server_config = get_server_config(server_code)
        bundle_path = str(getattr(server_config, "law_qa_bundle_path", "") or "").strip()
        if not bundle_path:
            return ()
        chunks = load_law_bundle_chunks(server_code, bundle_path)
    except Exception:
        return ()

    forced_norms: list[dict[str, object]] = []
    for chunk in chunks:
        if not _suggest_norm_targets_mask_exception(chunk.document_title, chunk.article_label, chunk.text):
            continue
        excerpt = _extract_relevant_law_excerpt(chunk.text, query, max_chars=900) or _truncate_law_excerpt(
            chunk.text,
            max_chars=900,
        )
        qualifiers = _extract_suggest_norm_qualifiers(chunk.text, article_label=str(chunk.article_label or ""))
        cross_refs = _extract_suggest_norm_cross_refs(chunk.text, article_label=str(chunk.article_label or ""))
        forced_norms.append(
            {
                "source_url": chunk.url,
                "document_title": chunk.document_title,
                "article_label": chunk.article_label,
                "excerpt": excerpt,
                "score": 100,
                "qualifiers": list(qualifiers),
                "cross_refs": list(cross_refs),
            }
        )
        break
    return tuple(forced_norms)


def _build_suggest_law_context(*, server_code: str, question: str, max_chunks: int = 4) -> SuggestContextBuildResult:
    retrieval_query = str(question or "").strip()
    if not retrieval_query:
        return SuggestContextBuildResult(
            context_text="",
            retrieval_confidence="low",
            retrieval_context_mode="no_context",
            retrieval_profile="suggest",
            bundle_status="missing",
            bundle_generated_at="",
            bundle_fingerprint="",
            selected_norms_count=0,
            selected_norms=(),
        )

    retrieval_result = _retrieve_law_context(
        server_code=server_code,
        query=retrieval_query,
        excerpt_chars=900,
        profile="suggest",
    )
    if not retrieval_result.indexed_chunk_count:
        return SuggestContextBuildResult(
            context_text="",
            retrieval_confidence=retrieval_result.confidence,
            retrieval_context_mode="no_context",
            retrieval_profile=retrieval_result.profile,
            bundle_status=retrieval_result.bundle_health.status,
            bundle_generated_at=retrieval_result.bundle_health.generated_at,
            bundle_fingerprint=retrieval_result.bundle_health.fingerprint,
            selected_norms_count=0,
            selected_norms=(),
        )

    ranked_matches = _rerank_suggest_matches(retrieval_result.matches, retrieval_query)
    positive = [match for adjusted_score, match in ranked_matches if adjusted_score > 0][:max_chunks]
    selected_matches = list(positive)
    if not selected_matches and ranked_matches:
        selected_matches = [match for _, match in ranked_matches[:max_chunks]]
    if not selected_matches:
        return SuggestContextBuildResult(
            context_text="",
            retrieval_confidence=retrieval_result.confidence,
            retrieval_context_mode="no_context",
            retrieval_profile=retrieval_result.profile,
            bundle_status=retrieval_result.bundle_health.status,
            bundle_generated_at=retrieval_result.bundle_health.generated_at,
            bundle_fingerprint=retrieval_result.bundle_health.fingerprint,
            selected_norms_count=0,
            selected_norms=(),
        )

    parts: list[str] = []
    selected_norms: list[dict[str, object]] = []
    seen_norm_keys: set[tuple[str, str, str]] = set()
    forced_norms = _build_suggest_forced_norms(server_code=server_code, query=retrieval_query)
    for norm in forced_norms:
        key = (
            str(norm.get("source_url", "") or "").strip(),
            str(norm.get("document_title", "") or "").strip(),
            str(norm.get("article_label", "") or "").strip(),
        )
        if key in seen_norm_keys:
            continue
        seen_norm_keys.add(key)
        selected_norms.append(norm)
        parts.append(
            "\n".join(
                (
                    f"Источник: {norm.get('source_url', '')}",
                    f"Документ: {norm.get('document_title', '')}",
                    f"Норма: {norm.get('article_label', '')}",
                    f"Фрагмент: {norm.get('excerpt', '')}",
                    *_format_suggest_norm_sections(
                        qualifiers=tuple(norm.get("qualifiers", ()) or ()),
                        cross_refs=tuple(norm.get("cross_refs", ()) or ()),
                    ),
                )
            ).strip()
        )
    for match in selected_matches:
        excerpt = match.excerpt
        if not excerpt:
            continue
        chunk_text = str(getattr(match.chunk, "text", "") or excerpt)
        qualifiers = _extract_suggest_norm_qualifiers(chunk_text, article_label=str(match.chunk.article_label or ""))
        cross_refs = _extract_suggest_norm_cross_refs(chunk_text, article_label=str(match.chunk.article_label or ""))
        norm_payload = {
            "source_url": match.chunk.url,
            "document_title": match.chunk.document_title,
            "article_label": match.chunk.article_label,
            "excerpt": excerpt,
            "score": match.score,
            "qualifiers": list(qualifiers),
            "cross_refs": list(cross_refs),
        }
        key = (
            str(norm_payload.get("source_url", "") or "").strip(),
            str(norm_payload.get("document_title", "") or "").strip(),
            str(norm_payload.get("article_label", "") or "").strip(),
        )
        if key in seen_norm_keys:
            continue
        seen_norm_keys.add(key)
        selected_norms.append(norm_payload)
        parts.append(
            "\n".join(
                (
                    f"\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a: {match.chunk.url}",
                    f"\u0414\u043e\u043a\u0443\u043c\u0435\u043d\u0442: {match.chunk.document_title}",
                    f"\u041d\u043e\u0440\u043c\u0430: {match.chunk.article_label}",
                    f"\u0424\u0440\u0430\u0433\u043c\u0435\u043d\u0442: {excerpt}",
                    *_format_suggest_norm_sections(qualifiers=qualifiers, cross_refs=cross_refs),
                )
            )
        )
    context_text = "\n\n".join(parts).strip()
    context_mode = "normal_context"
    if retrieval_result.confidence == "low":
        context_mode = "low_confidence_context"
    if not context_text:
        context_mode = "no_context"
    return SuggestContextBuildResult(
        context_text=context_text,
        retrieval_confidence=retrieval_result.confidence,
        retrieval_context_mode=context_mode,
        retrieval_profile=retrieval_result.profile,
        bundle_status=retrieval_result.bundle_health.status,
        bundle_generated_at=retrieval_result.bundle_health.generated_at,
        bundle_fingerprint=retrieval_result.bundle_health.fingerprint,
        selected_norms_count=len(selected_norms),
        selected_norms=tuple(selected_norms),
    )


def _normalize_suggest_retrieval_fragment(value: str, *, max_chars: int | None = None) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "").strip())
    if max_chars is None or max_chars <= 0 or len(normalized) <= max_chars:
        return normalized
    truncated = normalized[: max_chars + 1]
    cutoff = truncated.rfind(" ")
    if cutoff < max(0, int(max_chars * 0.6)):
        cutoff = max_chars
    return truncated[:cutoff].rstrip(" ,;:-") + "…"


def _build_suggest_retrieval_hints(payload: SuggestPayload) -> tuple[str, ...]:
    raw_desc = _normalize_suggest_inline(payload.raw_desc).lower()
    if _suggest_is_mask_exception_case(raw_desc):
        return (
            "статья 18 административный кодекс",
            "допустимость ношения маски",
            "развлекательное учреждение",
            "Maze Bank Arena",
        )
    return ()


def build_suggest_retrieval_query_light(payload: SuggestPayload, *, raw_desc_limit: int = 360) -> str:
    return " ".join(
        part
        for part in (
            _normalize_suggest_retrieval_fragment(payload.complaint_basis),
            _normalize_suggest_retrieval_fragment(payload.main_focus),
            *(_normalize_suggest_retrieval_fragment(item) for item in _build_suggest_retrieval_hints(payload)),
            _normalize_suggest_retrieval_fragment(payload.org),
            _normalize_suggest_retrieval_fragment(payload.subject),
            _normalize_suggest_retrieval_fragment(payload.raw_desc, max_chars=raw_desc_limit),
        )
        if part
    )


def _select_prompt_valid_triggers(valid_triggers, *, max_items: int = 2):
    def is_generic_secondary_support(trigger) -> bool:
        group_key = _suggest_document_group_key(str(getattr(trigger, "document_title", "") or ""))
        if group_key != "processual_code":
            return False
        return _suggest_primary_article_number(str(getattr(trigger, "norm_ref", "") or "")) in _SUGGEST_GENERIC_SECONDARY_PROCESSUAL_ARTICLES

    def trigger_key(trigger):
        generic_secondary = is_generic_secondary_support(trigger)
        return (
            1 if getattr(trigger, "matched_in_input", False) else 0,
            0 if generic_secondary else 1,
            1 if getattr(trigger, "qualifiers", ()) and not generic_secondary else 0,
            float(getattr(trigger, "trigger_confidence", 0.0) or 0.0),
            _suggest_document_priority_weight(str(getattr(trigger, "document_title", "") or "")),
        )

    def deserves_secondary_slot(trigger) -> bool:
        if is_generic_secondary_support(trigger) and not bool(getattr(trigger, "matched_in_input", False)):
            return False
        return (
            bool(getattr(trigger, "matched_in_input", False))
            or bool(getattr(trigger, "qualifiers", ()) or ())
            or not is_generic_secondary_support(trigger)
        )

    ranked = sorted(
        valid_triggers,
        key=trigger_key,
        reverse=True,
    )
    selected = []
    seen: set[tuple[str, str, str]] = set()
    for trigger in ranked:
        key = (
            str(getattr(trigger, "source_url", "") or "").strip(),
            str(getattr(trigger, "document_title", "") or "").strip(),
            str(getattr(trigger, "norm_ref", "") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        if selected and not deserves_secondary_slot(trigger):
            continue
        selected.append(trigger)
        if len(selected) >= max_items:
            break
    return tuple(selected)


def _build_filtered_prompt_law_context(
    *,
    point3_context,
    suggest_context: SuggestContextBuildResult,
    fallback_law_context: str,
) -> str:
    valid_triggers = [item for item in point3_context.triggers if item.is_valid]
    if valid_triggers:
        parts: list[str] = []
        seen: set[tuple[str, str, str]] = set()
        for trigger in valid_triggers:
            key = (
                str(trigger.source_url or "").strip(),
                str(trigger.document_title or "").strip(),
                str(trigger.norm_ref or "").strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            parts.append(
                "\n".join(
                    (
                        f"Источник: {trigger.source_url}",
                        f"Документ: {trigger.document_title}",
                        f"Норма: {trigger.norm_ref}",
                        f"Фрагмент: {trigger.excerpt}",
                    )
                ).strip()
            )
        filtered = "\n\n".join(part for part in parts if part).strip()
        if filtered:
            return filtered

    if suggest_context.selected_norms and point3_context.policy_decision.mode == MODE_FACTUAL_FALLBACK_EXPANDED:
        return ""
    return fallback_law_context


def _build_filtered_prompt_law_context(
    *,
    point3_context,
    suggest_context: SuggestContextBuildResult,
    fallback_law_context: str,
) -> str:
    valid_triggers = [item for item in point3_context.triggers if item.is_valid]
    if valid_triggers:
        parts: list[str] = []
        for trigger in _select_prompt_valid_triggers(valid_triggers, max_items=2):
            parts.append(
                "\n".join(
                    (
                        f"Источник: {trigger.source_url}",
                        f"Документ: {trigger.document_title}",
                        f"Норма: {trigger.norm_ref}",
                        f"Фрагмент: {trigger.excerpt}",
                        *_format_suggest_norm_sections(
                            qualifiers=tuple(
                                {
                                    "kind": getattr(item, "kind", ""),
                                    "text": getattr(item, "text", ""),
                                    "related_refs": list(getattr(item, "related_refs", ()) or ()),
                                }
                                for item in (getattr(trigger, "qualifiers", ()) or ())
                            ),
                            cross_refs=getattr(trigger, "cross_refs", ()) or (),
                        ),
                    )
                ).strip()
            )
        filtered = "\n\n".join(part for part in parts if part).strip()
        if filtered:
            return filtered

    if suggest_context.selected_norms and point3_context.policy_decision.mode == MODE_FACTUAL_FALLBACK_EXPANDED:
        return ""
    return fallback_law_context


def _clean_suggest_text(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ""

    normalized = re.sub(r"```(?:[\w+-]+)?\s*([\s\S]*?)```", lambda match: match.group(1).strip(), normalized)
    normalized = re.sub(
        r"\n?\s*(?:источники|sources)\s*:\s*[\s\S]*$",
        "",
        normalized,
        flags=re.IGNORECASE,
    )

    cleaned_lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        if re.fullmatch(
            r"(?i)(?:пункт\s*3|описательная\s+часть\s+жалобы|текст\s+жалобы|вариант\s+текста|готовый\s+текст)",
            line,
        ):
            continue
        if re.match(r"(?i)^(?:вот|ниже|готовый|обновленный|переписанный)\b.*(?:текст|вариант|пункт\s*3)", line):
            continue
        line = re.sub(r"^[-*•]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _truncate_suggest_value(value: str, *, max_chars: int) -> str:
    normalized = str(value or "").strip()
    if max_chars <= 0 or len(normalized) <= max_chars:
        return normalized
    head = normalized[: max_chars + 1]
    split_index = head.rfind(" ")
    if split_index < max(0, int(max_chars * 0.6)):
        split_index = max_chars
    return head[:split_index].rstrip(" ,;:-") + "..."


def answer_law_question_details(payload: LawQaPayload) -> LawQaAnswerResult:
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0432\u043e\u043f\u0440\u043e\u0441 \u0434\u043b\u044f \u0430\u043d\u0430\u043b\u0438\u0437\u0430."],
        )

    model_name = resolve_law_qa_model(payload.model)
    generation_id = new_generation_id()
    retrieval_result = _retrieve_law_context(
        server_code=payload.server_code or DEFAULT_SERVER_CODE,
        query=question,
        excerpt_chars=1800,
        profile="law_qa",
    )
    if not retrieval_result.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[
                "\u0414\u043b\u044f \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e \u0441\u0435\u0440\u0432\u0435\u0440\u0430 "
                "\u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u044b \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0438 \u0437\u0430\u043a\u043e\u043d\u043e\u0432."
            ],
        )

    if not retrieval_result.indexed_chunk_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[
                "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c "
                "\u0437\u0430\u043a\u043e\u043d\u044b \u0434\u043b\u044f \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e "
                "\u0441\u0435\u0440\u0432\u0435\u0440\u0430. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 "
                "\u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0443 law base."
            ],
        )

    server_config = get_server_config(retrieval_result.server_code)
    shadow = build_shadow_comparison(enabled=False, profile="", primary_matches=retrieval_result.matches, shadow_matches=())
    if _server_feature_enabled(server_config, "legal_pipeline_shadow"):
        shadow_profile = str(getattr(server_config, "shadow_law_qa_profile", "") or "").strip()
        if shadow_profile and shadow_profile != retrieval_result.profile:
            shadow_result = _retrieve_law_context(
                server_code=retrieval_result.server_code,
                query=question,
                excerpt_chars=1800,
                profile=shadow_profile,
            )
            shadow = build_shadow_comparison(
                enabled=True,
                profile=shadow_profile,
                primary_matches=retrieval_result.matches,
                shadow_matches=shadow_result.matches,
            )

    context_attempts = (
        _build_law_qa_context_blocks(retrieval_result),
        _build_law_qa_context_blocks_limited(retrieval_result, max_blocks=8, max_excerpt_chars=900),
        _build_law_qa_context_blocks_limited(retrieval_result, max_blocks=5, max_excerpt_chars=650),
        _build_law_qa_context_blocks_limited(retrieval_result, max_blocks=3, max_excerpt_chars=420),
        _build_law_qa_context_blocks_limited(retrieval_result, max_blocks=2, max_excerpt_chars=280),
    )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    proxy_url = os.getenv("OPENAI_PROXY_URL", "").strip()
    request_started_at = monotonic()
    prompt = ""
    text = ""
    usage = AiUsageSummary()
    compaction_level = 0
    try:
        client = create_openai_client(api_key=api_key, proxy_url=proxy_url)
        for attempt_index, context_blocks in enumerate(context_attempts):
            if not context_blocks:
                continue
            prompt = _build_law_qa_prompt(
                server_name=retrieval_result.server_name,
                server_code=retrieval_result.server_code,
                model_name=model_name,
                question=question,
                max_answer_chars=payload.max_answer_chars,
                context_blocks=context_blocks,
                retrieval_confidence=retrieval_result.confidence,
            )
            try:
                text, usage = _request_law_qa_text(
                    client=client,
                    model_name=model_name,
                    prompt=prompt,
                    max_output_tokens=800,
                )
                compaction_level = attempt_index
                break
            except HTTPException:
                raise
            except Exception as exc:
                if _is_context_window_error(exc) and attempt_index < len(context_attempts) - 1:
                    LOGGER.warning(
                        "Law QA prompt exceeded context window for model %s; retrying with compact context level=%s",
                        model_name,
                        attempt_index + 1,
                    )
                    continue
                raise
        if not text:
            raise RuntimeError("Law QA generation failed without response text after context retries.")
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_ai_exception_details(exc)) from exc

    limited = text[: payload.max_answer_chars].strip()
    latency_ms = int((monotonic() - request_started_at) * 1000)
    telemetry = build_ai_telemetry(
        model_name=model_name,
        prompt_text=prompt,
        output_text=limited,
        usage=usage,
        latency_ms=latency_ms,
        cache_hit=False,
    )
    budget_assessment = evaluate_budget(flow="law_qa", telemetry=telemetry)
    used_sources = list(unique_sources(retrieval_result))
    guard_result = guard_law_qa_answer(
        text=limited,
        allowed_source_urls=used_sources,
        bundle_health=retrieval_result.bundle_health,
    )
    telemetry_meta = telemetry_to_meta(telemetry)
    telemetry_meta.update(
        {
            "context_compaction_level": compaction_level,
            "context_compacted": bool(compaction_level > 0),
        }
    )
    return LawQaAnswerResult(
        text=limited,
        generation_id=generation_id,
        used_sources=used_sources,
        indexed_documents=retrieval_result.indexed_chunk_count,
        retrieval_confidence=retrieval_result.confidence,
        retrieval_profile=retrieval_result.profile,
        guard_status=guard_result.status,
        contract_version=LEGAL_PIPELINE_CONTRACT_VERSION,
        bundle_status=retrieval_result.bundle_health.status,
        bundle_generated_at=retrieval_result.bundle_health.generated_at,
        bundle_fingerprint=retrieval_result.bundle_health.fingerprint,
        warnings=list(
            dict.fromkeys(
                list(retrieval_result.bundle_health.warnings)
                + list(guard_result.warning_codes)
                + list(budget_assessment.warnings)
                + (["law_qa_context_compacted"] if compaction_level > 0 else [])
            )
        ),
        shadow=_shadow_to_dict(shadow),
        selected_norms=_build_law_qa_selected_norms(retrieval_result),
        telemetry=telemetry_meta,
        budget_status=budget_assessment.status,
        budget_warnings=list(budget_assessment.warnings),
        budget_policy=policy_to_meta(budget_assessment.policy),
    )


def answer_law_question(payload: LawQaPayload) -> tuple[str, list[str], int]:
    result = answer_law_question_details(payload)
    return result.text, result.used_sources, result.indexed_documents


def suggest_text_details(payload: SuggestPayload, *, server_code: str = DEFAULT_SERVER_CODE) -> SuggestTextResult:
    total_started_at = monotonic()
    if not payload.victim_name.strip() or not payload.org.strip() or not payload.subject.strip() or not payload.event_dt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Заполните: доверитель, дата/время, организация, объект заявления."],
        )
    if not payload.raw_desc.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Сначала заполните черновик описания событий."],
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    proxy_url = os.getenv("OPENAI_PROXY_URL", "").strip()
    generation_id = new_generation_id()
    server_config = get_server_config(server_code or DEFAULT_SERVER_CODE)
    suggest_prompt_mode = str(getattr(server_config, "suggest_prompt_mode", "legacy") or "legacy").strip().lower()
    low_confidence_policy = str(
        getattr(server_config, "suggest_low_confidence_policy", "controlled_fallback") or "controlled_fallback"
    ).strip().lower()
    shadow = build_shadow_comparison(enabled=False, profile="", primary_matches=(), shadow_matches=())
    suggest_query = build_suggest_retrieval_query_light(payload)
    retrieval_started_at = monotonic()
    suggest_context_raw = _build_suggest_law_context(
        server_code=server_code,
        question=suggest_query,
    )
    if isinstance(suggest_context_raw, SuggestContextBuildResult):
        suggest_context = suggest_context_raw
    else:
        suggest_context = SuggestContextBuildResult(
            context_text=str(suggest_context_raw or "").strip(),
            retrieval_confidence="medium",
            retrieval_context_mode="normal_context" if str(suggest_context_raw or "").strip() else "no_context",
            retrieval_profile="suggest",
            bundle_status="unknown",
            bundle_generated_at="",
            bundle_fingerprint="",
            selected_norms_count=0,
            selected_norms=(),
        )
    retrieval_ms = int((monotonic() - retrieval_started_at) * 1000)
    law_context = suggest_context.context_text
    if suggest_context.retrieval_context_mode == "low_confidence_context" and low_confidence_policy == "controlled_fallback":
        law_context = "\n".join(
            (
                "Статус retrieval: low_confidence_context",
                "Важно: используй только явно подтвержденные нормы из блока ниже. Если прямой нормы нет, не выдумывай ее.",
                law_context,
            )
        ).strip()
    if suggest_context.retrieval_context_mode == "no_context" and low_confidence_policy == "controlled_fallback":
        law_context = "\n".join(
            (
                "Статус retrieval: no_context",
                "Важно: надежный правовой контекст не найден. Пиши только факты из черновика и не выдумывай нормы.",
            )
        )
    if _server_feature_enabled(server_config, "legal_pipeline_shadow"):
        shadow_profile = str(getattr(server_config, "shadow_suggest_profile", "") or "").strip()
        if shadow_profile and shadow_profile != "suggest":
            primary_result = _retrieve_law_context(
                server_code=server_code,
                query=suggest_query,
                excerpt_chars=900,
                profile="suggest",
            )
            shadow_result = _retrieve_law_context(
                server_code=server_code,
                query=suggest_query,
                excerpt_chars=900,
                profile=shadow_profile,
            )
            shadow = build_shadow_comparison(
                enabled=True,
                profile=shadow_profile,
                primary_matches=primary_result.matches,
                shadow_matches=shadow_result.matches,
            )

    victim_name = payload.victim_name.strip()
    org = payload.org.strip()
    subject = payload.subject.strip()
    event_dt = payload.event_dt.strip()
    complaint_basis = payload.complaint_basis.strip()
    main_focus = payload.main_focus.strip()
    raw_desc = payload.raw_desc.strip()
    if low_confidence_policy == "soft_fail" and suggest_context.retrieval_context_mode in {"low_confidence_context", "no_context"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                "Недостаточно надежного правового контекста для генерации. Уточните факты и повторите запрос.",
            ],
        )
    point3_context = build_point3_pipeline_context(
        complainant=victim_name,
        organization=org,
        target_person=subject,
        event_datetime=event_dt,
        draft_text=raw_desc,
        complaint_basis=complaint_basis,
        main_focus=main_focus,
        retrieval_status=suggest_context.retrieval_context_mode,
        retrieval_confidence=suggest_context.retrieval_confidence,
        retrieved_law_context=law_context,
        selected_norms=suggest_context.selected_norms,
    )
    policy_mode = point3_context.policy_decision.mode
    pipeline_context_payload = point3_context.prompt_context_json()
    prompt_law_context = _build_filtered_prompt_law_context(
        point3_context=point3_context,
        suggest_context=suggest_context,
        fallback_law_context=law_context,
    )
    suggest_attempts = (
        (raw_desc, prompt_law_context),
        (raw_desc, _truncate_suggest_value(prompt_law_context, max_chars=2600)),
        (raw_desc, _truncate_suggest_value(prompt_law_context, max_chars=1500)),
        (_truncate_suggest_value(raw_desc, max_chars=8000), _truncate_suggest_value(prompt_law_context, max_chars=1200)),
        (_truncate_suggest_value(raw_desc, max_chars=5000), _truncate_suggest_value(prompt_law_context, max_chars=700)),
    )

    prompt_text = ""
    generation_result: TextGenerationResult | None = None
    openai_ms = 0
    suggest_compaction_level = 0
    request_started_at = monotonic()
    try:
        for attempt_index, (attempt_raw_desc, attempt_law_context) in enumerate(suggest_attempts):
            prompt_text = build_suggest_prompt(
                victim_name=victim_name,
                org=org,
                subject=subject,
                event_dt=event_dt,
                raw_desc=attempt_raw_desc,
                complaint_basis=complaint_basis,
                main_focus=main_focus,
                law_context=attempt_law_context,
                prompt_mode=suggest_prompt_mode,
                policy_mode=policy_mode,
                pipeline_context=pipeline_context_payload,
                retrieval_context_mode=suggest_context.retrieval_context_mode,
            )
            try:
                generation_result = suggest_description_with_proxy_fallback_result(
                    api_key=api_key,
                    proxy_url=proxy_url,
                    victim_name=victim_name,
                    org=org,
                    subject=subject,
                    event_dt=event_dt,
                    raw_desc=attempt_raw_desc,
                    complaint_basis=complaint_basis,
                    main_focus=main_focus,
                    law_context=attempt_law_context,
                    prompt_mode=suggest_prompt_mode,
                    policy_mode=policy_mode,
                    pipeline_context=pipeline_context_payload,
                    retrieval_context_mode=suggest_context.retrieval_context_mode,
                    bundle_fingerprint=suggest_context.bundle_fingerprint,
                    retrieval_profile=suggest_context.retrieval_profile,
                )
                suggest_compaction_level = attempt_index
                break
            except Exception as exc:
                if _is_context_window_error(exc) and attempt_index < len(suggest_attempts) - 1:
                    LOGGER.warning(
                        "Suggest prompt exceeded context window; retrying with compact context level=%s",
                        attempt_index + 1,
                    )
                    continue
                raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_ai_exception_details(exc)) from exc
    openai_ms = int((monotonic() - request_started_at) * 1000)
    if generation_result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=["Не удалось получить ответ модели после повторных попыток."],
        )

    text = generation_result.text
    if not text:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=["Модель вернула пустой ответ. Попробуйте еще раз."],
        )
    cleaned = _clean_suggest_text(text)
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=["Модель вернула некорректный формат ответа. Попробуйте еще раз."],
        )
    remediation = apply_validation_remediation(cleaned, point3_context)
    final_text = remediation.text
    if not final_text:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=["РњРѕРґРµР»СЊ РІРµСЂРЅСѓР»Р° РїСѓСЃС‚РѕР№ РёР»Рё РЅРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ С‚РµРєСЃС‚ РїРѕСЃР»Рµ РІР°Р»РёРґР°С†РёРё."],
        )
    total_suggest_ms = int((monotonic() - total_started_at) * 1000)
    telemetry = build_ai_telemetry(
        model_name=OPENAI_TEXT_MODEL,
        prompt_text=prompt_text,
        output_text=final_text,
        usage=generation_result.usage,
        latency_ms=openai_ms,
        cache_hit=generation_result.cache_hit,
    )
    budget_assessment = evaluate_budget(flow="suggest", telemetry=telemetry)
    validation_result = remediation.validation
    guard_result = guard_suggest_answer(text=final_text)
    combined_guard_status = "fail" if validation_result.blockers else "warn" if (
        guard_result.status == "warn" or validation_result.status == "warn"
    ) else "pass"
    telemetry_meta = telemetry_to_meta(telemetry)
    telemetry_meta.update(
        {
            "attempt_path": generation_result.attempt_path,
            "attempt_duration_ms": generation_result.attempt_duration_ms,
            "route_policy": generation_result.route_policy,
            "context_compaction_level": suggest_compaction_level,
            "context_compacted": bool(suggest_compaction_level > 0),
            "retrieval_context_mode": suggest_context.retrieval_context_mode,
            "policy_mode": policy_mode,
            "policy_reason": point3_context.policy_decision.reason,
            "valid_triggers_count": point3_context.policy_decision.valid_triggers_count,
            "avg_trigger_confidence": point3_context.policy_decision.avg_confidence,
            "validator_warning_codes": list(validation_result.warning_codes),
            "validator_info_codes": list(validation_result.info_codes),
            "input_warning_codes": list(point3_context.input_audit.warning_codes),
            "protected_terms": list(point3_context.input_audit.protected_terms),
            "remediation_retries": remediation.retries_used,
            "safe_fallback_used": remediation.safe_fallback_used,
        }
    )
    return SuggestTextResult(
        text=final_text,
        generation_id=generation_id,
        guard_status=combined_guard_status,
        contract_version=LEGAL_PIPELINE_CONTRACT_VERSION,
        warnings=list(
            dict.fromkeys(
                list(guard_result.warning_codes)
                + list(validation_result.warning_codes)
                + list(budget_assessment.warnings)
                + list(point3_context.input_audit.warning_codes)
                + (
                    ["suggest_low_confidence_context"]
                    if suggest_context.retrieval_context_mode == "low_confidence_context"
                    else []
                )
                + (["suggest_no_context"] if suggest_context.retrieval_context_mode == "no_context" else [])
                + (["suggest_context_compacted"] if suggest_compaction_level > 0 else [])
                + (["suggest_output_remediated"] if remediation.retries_used > 0 else [])
                + (["suggest_safe_fallback_template"] if remediation.safe_fallback_used else [])
                + (
                    ["suggest_factual_fallback_expanded"]
                    if policy_mode == MODE_FACTUAL_FALLBACK_EXPANDED
                    else ["suggest_legal_grounded"]
                )
            )
        ),
        shadow=_shadow_to_dict(shadow),
        telemetry=telemetry_meta,
        budget_status=budget_assessment.status,
        budget_warnings=list(budget_assessment.warnings),
        budget_policy=policy_to_meta(budget_assessment.policy),
        retrieval_ms=retrieval_ms,
        openai_ms=openai_ms,
        total_suggest_ms=total_suggest_ms,
        prompt_mode=suggest_prompt_mode,
        retrieval_confidence=suggest_context.retrieval_confidence,
        retrieval_context_mode=suggest_context.retrieval_context_mode,
        retrieval_profile=suggest_context.retrieval_profile,
        bundle_status=suggest_context.bundle_status,
        bundle_generated_at=suggest_context.bundle_generated_at,
        bundle_fingerprint=suggest_context.bundle_fingerprint,
        selected_norms_count=suggest_context.selected_norms_count,
        policy_mode=policy_mode,
        policy_reason=point3_context.policy_decision.reason,
        valid_triggers_count=point3_context.policy_decision.valid_triggers_count,
        avg_trigger_confidence=point3_context.policy_decision.avg_confidence,
        remediation_retries=remediation.retries_used,
        safe_fallback_used=remediation.safe_fallback_used,
        input_warning_codes=point3_context.input_audit.warning_codes,
        protected_terms=point3_context.input_audit.protected_terms,
    )


def suggest_text(payload: SuggestPayload, *, server_code: str = DEFAULT_SERVER_CODE) -> str:
    return suggest_text_details(payload, server_code=server_code).text


def extract_principal_scan(payload: PrincipalScanPayload) -> PrincipalScanResult:
    image_data_url = payload.image_data_url.strip()
    if not image_data_url.startswith("data:image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Загрузите изображение в формате PNG, JPG, WEBP или GIF."],
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    proxy_url = os.getenv("OPENAI_PROXY_URL", "").strip()

    try:
        data = extract_principal_fields_with_proxy_fallback(
            api_key=api_key,
            proxy_url=proxy_url,
            image_data_url=image_data_url,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_ai_exception_details(exc)) from exc

    try:
        result = PrincipalScanResult.model_validate(data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=[f"Модель вернула ответ в неожиданном формате: {exc}"],
        ) from exc

    if not result.principal_address.strip():
        result.principal_address = "-"

    return result
