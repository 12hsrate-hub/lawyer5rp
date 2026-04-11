from __future__ import annotations

from functools import lru_cache
import logging
import os
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from ipaddress import ip_address
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status

from ogp_web.schemas import LawQaPayload, PrincipalScanPayload, PrincipalScanResult, SuggestPayload
from ogp_web.server_config import DEFAULT_SERVER_CODE, get_server_config
from shared.ogp_ai import (
    create_openai_client,
    extract_response_text,
    extract_principal_fields_with_proxy_fallback,
    suggest_description_with_proxy_fallback,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _LawChunk:
    url: str
    document_title: str
    article_label: str
    text: str


LAW_QA_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "освобождение": ("освободить", "освобождения", "выпустить", "отпустить", "release"),
    "задержанный": ("задержание", "задержанного", "detention", "detainee", "удержание"),
    "основания": ("условия", "случаи", "поводы", "когда"),
    "адвокат": ("защитник", "защита"),
    "обыск": ("досмотр", "осмотр"),
    "залог": ("залога", "bail"),
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
    return ("gpt-5.4", "gpt-5-mini", "gpt-4.1-mini")


def get_default_law_qa_model() -> str:
    configured = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.4").strip() or "gpt-5.4"
    choices = get_law_qa_model_choices()
    if configured in choices:
        return configured
    return choices[0]


def resolve_law_qa_model(requested_model: str) -> str:
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


def _extract_keywords(question: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\w{4,}", question.lower(), flags=re.UNICODE)
        if token not in {"когда", "если", "или", "тогда", "where", "what", "which", "with"}
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
        for token in normalized_question.split()
        if len(token) >= 3 and token not in {"что", "это", "для", "как", "или", "при", "нет"}
    }
    expanded = set(tokens)
    for token in list(tokens):
        for key, aliases in LAW_QA_QUERY_ALIASES.items():
            alias_terms = {_normalize_law_text(key), *(_normalize_law_text(item) for item in aliases)}
            if token in alias_terms or any(token in alias for alias in alias_terms):
                expanded.update(alias_terms)
    return {item for item in expanded if item}


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
    normalized_text = _normalize_law_text(f"{chunk.document_title} {chunk.article_label} {chunk.text}")
    normalized_label = _normalize_law_text(chunk.article_label)
    terms = _expand_question_terms(question)
    score = 0
    for term in terms:
        if not term:
            continue
        if term in normalized_label:
            score += 16
        if f" {term} " in f" {normalized_text} ":
            score += 10
        elif term in normalized_text:
            score += 5

    for article_number in _extract_article_numbers(question):
        if re.search(rf"(?i)(?:article|ст\.?|статья)\s*{re.escape(article_number)}\b", normalized_text):
            score += 40

    if terms:
        score += sum(1 for term in terms if term in normalized_text) * 3
        score += sum(1 for term in terms if term in normalized_label) * 8
    return score


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

    keywords = sorted(_extract_keywords(question), key=len, reverse=True)
    if not keywords:
        return normalized_text[:max_chars].strip()

    lower_text = normalized_text.lower()
    hit_positions: list[int] = []
    for keyword in keywords[:6]:
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


def _request_law_qa_text(*, client, model_name: str, prompt: str, max_output_tokens: int) -> str:
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
            return text
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


def answer_law_question(payload: LawQaPayload) -> tuple[str, list[str], int]:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Введите вопрос для анализа."])

    model_name = resolve_law_qa_model(payload.model)
    server_code = payload.server_code or DEFAULT_SERVER_CODE
    server_config = get_server_config(server_code)
    law_sources = [str(item or "").strip() for item in server_config.law_qa_sources if str(item or "").strip()]
    if not law_sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Для выбранного сервера не настроены источники законов."],
        )

    chunks = list(_build_law_chunk_index_cached(tuple(law_sources)))
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Не удалось загрузить законы для выбранного сервера. Проверьте настройку law base."],
        )

    ranked = sorted(chunks, key=lambda item: _score_law_chunk(item, question), reverse=True)
    selected = [item for item in ranked[:6] if _score_law_chunk(item, question) > 0] or ranked[:4]
    context_blocks = [
        (
            f"[Источник: {item.url}]\n"
            f"[Документ: {item.document_title}]\n"
            f"[Норма: {item.article_label}]\n"
            f"{_extract_relevant_law_excerpt(item.text, question, max_chars=1800)}"
        )
        for item in selected
    ]
    prompt = (
        "Ты юридический ассистент игрового сервера. Отвечай только на основе переданной внутриигровой законодательной базы.\n"
        "Если данных недостаточно, прямо так и скажи.\n"
        "Не добавляй никакие реальные законы, нормы, судебную практику или фоновые знания из внешнего мира.\n"
        "Если во внутриигровой законодательной базе нет оснований для ответа, так и напиши.\n"
        "Обязательно укажи ссылки на источники в конце каждого смыслового абзаца.\n"
        "Ответ должен быть точным, прикладным и без воды.\n\n"
        f"Сервер: {server_config.name} ({server_config.code})\n"
        f"Модель: {model_name}\n\n"
        f"Вопрос:\n{question}\n\n"
        f"Ограничение длины ответа: не более {payload.max_answer_chars} символов.\n\n"
        "Законодательная база:\n"
        + "\n\n".join(context_blocks)
    )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    proxy_url = os.getenv("OPENAI_PROXY_URL", "").strip()
    try:
        client = create_openai_client(api_key=api_key, proxy_url=proxy_url)
        text = _request_law_qa_text(
            client=client,
            model_name=model_name,
            prompt=prompt,
            max_output_tokens=800,
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_ai_exception_details(exc)) from exc

    limited = text[: payload.max_answer_chars].strip()
    unique_sources = list(dict.fromkeys(item.url for item in selected))
    return limited, unique_sources, len(chunks)


def suggest_text(payload: SuggestPayload) -> str:
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

    try:
        text = suggest_description_with_proxy_fallback(
            api_key=api_key,
            proxy_url=proxy_url,
            victim_name=payload.victim_name.strip(),
            org=payload.org.strip(),
            subject=payload.subject.strip(),
            event_dt=payload.event_dt.strip(),
            raw_desc=payload.raw_desc.strip(),
            complaint_basis=payload.complaint_basis.strip(),
            main_focus=payload.main_focus.strip(),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_ai_exception_details(exc)) from exc

    if not text:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=["Модель вернула пустой ответ. Попробуйте еще раз."],
        )
    return text


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
