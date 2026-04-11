from __future__ import annotations

import os
import re
from html.parser import HTMLParser

import httpx

from fastapi import HTTPException, status

from ogp_web.schemas import LawQaPayload, PrincipalScanPayload, PrincipalScanResult, SuggestPayload
from ogp_web.services.law_qa_catalog import get_law_sources
from ogp_web.storage.law_qa_store import LawQaStore
from shared.ogp_ai import (
    create_openai_client,
    extract_principal_fields_with_proxy_fallback,
    suggest_description_with_proxy_fallback,
)


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


class _LawHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._links: list[str] = []

    @property
    def text(self) -> str:
        merged = " ".join(chunk.strip() for chunk in self._chunks if chunk and chunk.strip())
        return re.sub(r"\s+", " ", merged).strip()

    @property
    def links(self) -> list[str]:
        return self._links

    def handle_data(self, data: str) -> None:
        if data:
            self._chunks.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self._links.append(str(value))
                break


def _extract_keywords(question: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Zа-яА-Я0-9_]{4,}", question.lower())
        if token not in {"когда", "если", "или", "тогда", "where", "what", "which", "with"}
    }


def _fetch_source_text(url: str, *, max_doc_chars: int = 12000) -> str:
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
    content_type = (response.headers.get("content-type") or "").lower()
    if "text/html" not in content_type:
        return ""
    parser = _LawHtmlParser()
    parser.feed(response.text)
    return parser.text[:max_doc_chars].strip()


def _ensure_law_documents_loaded(store: LawQaStore, server_code: str) -> list[dict[str, str]]:
    existing = store.list_documents(server_code)
    if existing:
        return existing
    sources = get_law_sources(server_code)
    if not sources:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Для выбранного сервера база законов не настроена."])
    documents: list[dict[str, str]] = []
    for source in sources:
        try:
            text = _fetch_source_text(source.url)
        except Exception:
            continue
        if not text:
            continue
        documents.append({"title": source.title, "source_url": source.url, "content": text})
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=["Не удалось загрузить законодательную базу сервера. Попробуйте позже или обратитесь к администратору."],
        )
    store.replace_server_documents(server_code, documents)
    return store.list_documents(server_code)


def answer_law_question(payload: LawQaPayload, law_qa_store: LawQaStore) -> tuple[str, list[str], int]:
    server_code = str(payload.server_code or "blackberry").strip().lower()
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Введите вопрос для анализа."])

    documents = _ensure_law_documents_loaded(law_qa_store, server_code)
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["Законодательная база сервера не содержит документов для анализа."],
        )

    keywords = _extract_keywords(question)

    def score(item: dict[str, str]) -> int:
        lower_text = item["text"].lower()
        return sum(1 for keyword in keywords if keyword in lower_text)

    ranked = sorted(documents, key=score, reverse=True)
    selected = ranked[:4]
    context_blocks = [f"[Источник: {item['title']} — {item['url']}]\n{item['text'][:2500]}" for item in selected]
    prompt = (
        "Ты юридический ассистент игрового сервера. Отвечай только на основе переданной законодательной базы.\n"
        "Если данных недостаточно, прямо так и скажи и попроси дополнительные ссылки.\n"
        "Обязательно укажи ссылки на нормы (URL источников) в конце каждого смыслового абзаца.\n"
        "Ответ должен быть полным по существу, но без воды.\n\n"
        f"Вопрос:\n{question}\n\n"
        f"Ограничение длины ответа: не более {payload.max_answer_chars} символов.\n\n"
        "Законодательная база:\n"
        + "\n\n".join(context_blocks)
    )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    proxy_url = os.getenv("OPENAI_PROXY_URL", "").strip()
    try:
        client = create_openai_client(api_key=api_key, proxy_url=proxy_url)
        response = client.responses.create(
            model=os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini"),
            input=prompt,
            max_output_tokens=800,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_ai_exception_details(exc)) from exc

    text = (response.output_text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=["Модель вернула пустой ответ."])
    limited = text[: payload.max_answer_chars].strip()
    return limited, [item["url"] for item in selected], len(documents)


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
