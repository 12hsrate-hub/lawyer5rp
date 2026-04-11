from __future__ import annotations

import json
import re
import threading
from contextlib import contextmanager
from typing import Callable

from shared.ogp_ai_cache import get_ai_cache
from shared.ogp_ai_cache import AiCache
from shared.ogp_ai_config import load_openai_config
from shared.ogp_ai_prompts import (
    EXAM_BATCH_SCORING_PROMPT_VERSION,
    EXAM_SCORING_PROMPT_VERSION,
    PRINCIPAL_SCAN_PROMPT_VERSION,
    SUGGEST_PROMPT_VERSION,
    build_batch_exam_scoring_prompt,
    build_exam_scoring_prompt,
    build_principal_scan_prompt,
    build_suggest_prompt,
)
from shared.ogp_core import is_valid_http_url

_OPENAI_CONFIG = load_openai_config()
OPENAI_TEXT_MODEL = _OPENAI_CONFIG.text_model
OPENAI_OCR_MODEL = _OPENAI_CONFIG.ocr_model
OPENAI_EXAM_SCORING_MODEL = _OPENAI_CONFIG.exam_scoring_model
OPENAI_TIMEOUT_SECONDS = _OPENAI_CONFIG.timeout_seconds
OPENAI_CONNECT_TIMEOUT_SECONDS = _OPENAI_CONFIG.connect_timeout_seconds
DEFAULT_EXAM_RATIONALE = "Оценка получена без пояснения."
DEFAULT_INVALID_BATCH_RATIONALE = "Модель не вернула корректную оценку по этому пункту."
_JSON_DECODER = json.JSONDecoder()
_MIN_SUBSTRING_MATCH_LENGTH = 12
_HIGH_JACCARD_THRESHOLD = 0.8
_VERY_HIGH_JACCARD_THRESHOLD = 0.94
_BATCH_SCORING_CHUNK_SIZE = 12
OPENAI_PROXY_ONLY = _OPENAI_CONFIG.proxy_only
_OPENAI_CONCURRENCY_LIMITS = {
    "text": max(1, _OPENAI_CONFIG.text_max_concurrency),
    "ocr": max(1, _OPENAI_CONFIG.ocr_max_concurrency),
    "exam_single": max(1, _OPENAI_CONFIG.exam_single_max_concurrency),
    "exam_batch": max(1, _OPENAI_CONFIG.exam_batch_max_concurrency),
}
_OPENAI_SEMAPHORES = {
    key: threading.BoundedSemaphore(value=limit)
    for key, limit in _OPENAI_CONCURRENCY_LIMITS.items()
}


@contextmanager
def _openai_operation_slot(operation_kind: str):
    semaphore = _OPENAI_SEMAPHORES.get(operation_kind)
    if semaphore is None:
        raise RuntimeError(f"Unknown OpenAI operation kind: {operation_kind!r}")
    semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()


def create_openai_client(api_key: str, proxy_url: str = ""):
    try:
        import httpx  # type: ignore
        from openai import DefaultHttpxClient, OpenAI  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Не найдены пакеты 'openai' и/или 'httpx'. Установите: python -m pip install openai httpx"
        ) from exc

    if not api_key:
        raise RuntimeError("OpenAI API key не задан.")
    if proxy_url and not is_valid_http_url(proxy_url):
        raise RuntimeError("Прокси должен быть указан в формате http://... или https://...")

    timeout = httpx.Timeout(
        OPENAI_TIMEOUT_SECONDS,
        connect=OPENAI_CONNECT_TIMEOUT_SECONDS,
        read=OPENAI_TIMEOUT_SECONDS,
        write=OPENAI_CONNECT_TIMEOUT_SECONDS,
    )
    http_client = DefaultHttpxClient(proxy=proxy_url or None, timeout=timeout, trust_env=False)
    return OpenAI(api_key=api_key, max_retries=0, http_client=http_client)


def _extract_json_object(raw_text: str) -> dict[str, object]:
    text = (raw_text or "").strip()
    if not text:
        return {}

    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced_match:
        text = fenced_match.group(1).strip()
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise RuntimeError("Модель вернула JSON не в формате объекта.")
        return payload

    for match in re.finditer(r"\{", text):
        try:
            payload, _ = _JSON_DECODER.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    raise RuntimeError("Модель не вернула корректный JSON-объект.")


def _response_part_value(item: object, key: str, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _sanitize_response_text(text: str) -> str:
    lines = [line.strip() for line in str(text or "").replace("\r", "").split("\n")]
    filtered = [
        line
        for line in lines
        if line and line.lower() not in {"reasoning", "empty reasoning item"}
    ]
    return "\n".join(filtered).strip()


def extract_response_text(response: object) -> str:
    direct = _sanitize_response_text(_response_part_value(response, "output_text", "") or "")
    if direct:
        return direct

    output_items = _response_part_value(response, "output", None) or []
    message_chunks: list[str] = []
    for output_item in output_items:
        if str(_response_part_value(output_item, "type", "") or "").lower() != "message":
            continue
        for content_item in _response_part_value(output_item, "content", None) or []:
            content_type = str(_response_part_value(content_item, "type", "") or "").lower()
            if content_type == "reasoning":
                continue
            text = _response_part_value(content_item, "text", None)
            if isinstance(text, str):
                cleaned = _sanitize_response_text(text)
                if cleaned:
                    message_chunks.append(cleaned)
                continue
            nested_value = _response_part_value(text, "value", None)
            if isinstance(nested_value, str):
                cleaned = _sanitize_response_text(nested_value)
                if cleaned:
                    message_chunks.append(cleaned)
                continue
            fallback_text = _response_part_value(content_item, "output_text", None)
            if isinstance(fallback_text, str):
                cleaned = _sanitize_response_text(fallback_text)
                if cleaned:
                    message_chunks.append(cleaned)
                continue
            refusal_text = _response_part_value(content_item, "refusal", None)
            if isinstance(refusal_text, str):
                cleaned = _sanitize_response_text(refusal_text)
                if cleaned:
                    message_chunks.append(cleaned)
                continue
            if isinstance(text, list):
                for nested_item in text:
                    nested_value = _response_part_value(nested_item, "text", None) or _response_part_value(
                        nested_item, "value", None
                    )
                    if isinstance(nested_value, str):
                        cleaned = _sanitize_response_text(nested_value)
                        if cleaned:
                            message_chunks.append(cleaned)

    return "\n".join(chunk for chunk in message_chunks if chunk).strip()


def _coerce_exam_score(raw_score: object, *, fallback: int = 1) -> int:
    try:
        if isinstance(raw_score, bool):
            value = int(raw_score)
        elif isinstance(raw_score, int):
            value = raw_score
        elif isinstance(raw_score, float):
            value = int(round(raw_score))
        else:
            text = str(raw_score or "").strip().replace(",", ".")
            if not text:
                return fallback
            value = int(round(float(text)))
    except (TypeError, ValueError):
        return fallback
    return max(1, min(100, value))


def _normalize_exam_result(payload: dict[str, object] | None, *, fallback_rationale: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {"score": 1, "rationale": fallback_rationale}

    rationale = str(payload.get("rationale", "") or "").strip() or fallback_rationale
    return {
        "score": _coerce_exam_score(payload.get("score", 1)),
        "rationale": rationale,
    }


def _extract_batch_results_map(raw_payload: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not isinstance(raw_payload, dict):
        return {}

    results = raw_payload.get("results")
    if isinstance(results, list):
        mapped: dict[str, dict[str, object]] = {}
        for item in results:
            if not isinstance(item, dict):
                continue
            column = str(item.get("column") or "").strip().upper()
            if not column:
                continue
            mapped[column] = item
        if mapped:
            return mapped

    fallback: dict[str, dict[str, object]] = {}
    for key, value in raw_payload.items():
        column = str(key or "").strip().upper()
        if not column:
            continue
        if not isinstance(value, dict):
            continue
        fallback[column] = value
    return fallback


def _run_with_proxy_fallback(
    *,
    api_key: str,
    proxy_url: str,
    operation_name: str,
    operation_kind: str,
    operation: Callable[[object], object],
    status_callback: Callable[[str], None] | None = None,
    direct_status: str | None = None,
    proxy_status: str | None = None,
) -> object:
    with _openai_operation_slot(operation_kind):
        first_error: Exception | None = None

        if not OPENAI_PROXY_ONLY:
            if status_callback and direct_status:
                status_callback(direct_status)
            try:
                client = create_openai_client(api_key=api_key, proxy_url="")
                return operation(client)
            except Exception as exc:
                first_error = exc
                if not proxy_url:
                    raise

        if status_callback and proxy_status:
            status_callback(proxy_status)

        try:
            client = create_openai_client(api_key=api_key, proxy_url=proxy_url)
            return operation(client)
        except Exception as proxy_exc:
            if first_error is None:
                raise
            raise RuntimeError(
                f"OpenAI failed during {operation_name} both directly and via proxy.\n"
                f"Direct error: {first_error}\n"
                f"Proxy error: {proxy_exc}"
            ) from proxy_exc


def _build_suggest_prompt(
    victim_name: str,
    org: str,
    subject: str,
    event_dt: str,
    raw_desc: str,
    complaint_basis: str = "",
    main_focus: str = "",
    law_context: str = "",
) -> str:
    return build_suggest_prompt(
        victim_name=victim_name,
        org=org,
        subject=subject,
        event_dt=event_dt,
        raw_desc=raw_desc,
        complaint_basis=complaint_basis,
        main_focus=main_focus,
        law_context=law_context,
    )


def suggest_description(
    client,
    victim_name: str,
    org: str,
    subject: str,
    event_dt: str,
    raw_desc: str,
    complaint_basis: str = "",
    main_focus: str = "",
    law_context: str = "",
) -> str:
    prompt = _build_suggest_prompt(
        victim_name=victim_name,
        org=org,
        subject=subject,
        event_dt=event_dt,
        raw_desc=raw_desc,
        complaint_basis=complaint_basis,
        main_focus=main_focus,
        law_context=law_context,
    )
    cache = get_ai_cache()
    cache_key = cache.build_key(
        operation="suggest_description",
        model=OPENAI_TEXT_MODEL,
        payload={
            "prompt_version": SUGGEST_PROMPT_VERSION,
            "victim_name": victim_name,
            "org": org,
            "subject": subject,
            "event_dt": event_dt,
            "raw_desc": raw_desc,
            "complaint_basis": complaint_basis,
            "main_focus": main_focus,
            "law_context": law_context,
        },
    )
    cached = cache.get(cache_key)
    if isinstance(cached, dict) and isinstance(cached.get("text"), str):
        return cached["text"].strip()

    response = client.responses.create(model=OPENAI_TEXT_MODEL, input=prompt)
    text = extract_response_text(response)
    cache.set(cache_key, {"text": text})
    return text


def extract_principal_fields(
    client,
    *,
    image_data_url: str,
) -> dict[str, object]:
    cache = get_ai_cache()
    cache_key = cache.build_key(
        operation="extract_principal_fields",
        model=OPENAI_OCR_MODEL,
        payload={"prompt_version": PRINCIPAL_SCAN_PROMPT_VERSION, "image_data_url": image_data_url},
    )
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    response = client.responses.create(
        model=OPENAI_OCR_MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": build_principal_scan_prompt()},
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }
        ],
    )
    payload = _extract_json_object(extract_response_text(response))
    cache.set(cache_key, payload)
    return payload


def _normalize_exam_answer(value: str) -> str:
    normalized = re.sub(r"[^\w\s]+", " ", str(value or "").lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _tokenize_exam_answer(value: str) -> list[str]:
    return [token for token in _normalize_exam_answer(value).split() if token]


def _extract_numeric_tokens(value: str) -> set[str]:
    return set(re.findall(r"\d+", _normalize_exam_answer(value)))


def _token_jaccard(left_tokens: set[str], right_tokens: set[str]) -> float:
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


def _build_exam_score_cache_key(
    cache: AiCache,
    *,
    user_answer: str,
    correct_answer: str,
    column: str = "",
    question: str = "",
    exam_type: str = "",
    key_points: list[str] | None = None,
) :
    return cache.build_key(
        operation="score_exam_answer",
        model=OPENAI_EXAM_SCORING_MODEL,
        payload={
            "prompt_version": EXAM_SCORING_PROMPT_VERSION,
            "column": column,
            "question": question,
            "exam_type": exam_type,
            "key_points": [str(item).strip() for item in (key_points or []) if str(item).strip()],
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "normalized_user_answer": _normalize_exam_answer(user_answer),
            "normalized_correct_answer": _normalize_exam_answer(correct_answer),
        },
    )


def _estimate_exam_score_without_llm(*, user_answer: str, correct_answer: str) -> dict[str, object] | None:
    normalized_user = _normalize_exam_answer(user_answer)
    normalized_correct = _normalize_exam_answer(correct_answer)
    if not normalized_user:
        return {
            "score": 1,
            "rationale": "Ответ в строке отсутствует или не содержит содержательной формулировки.",
        }
    if normalized_user == normalized_correct:
        return {
            "score": 100,
            "rationale": "Ответ полностью совпадает с правильной логикой и формулировкой.",
        }

    user_tokens = _tokenize_exam_answer(user_answer)
    correct_tokens = _tokenize_exam_answer(correct_answer)
    if not user_tokens or not correct_tokens:
        return None

    user_token_set = set(user_tokens)
    correct_token_set = set(correct_tokens)
    shared_numbers = _extract_numeric_tokens(user_answer) == _extract_numeric_tokens(correct_answer)
    jaccard = _token_jaccard(user_token_set, correct_token_set)

    if (
        shared_numbers
        and min(len(normalized_user), len(normalized_correct)) >= _MIN_SUBSTRING_MATCH_LENGTH
        and (normalized_user in normalized_correct or normalized_correct in normalized_user)
    ):
        return {
            "score": 96,
            "rationale": "Ответ почти дословно совпадает с правильным смыслом и не требует дополнительной проверки моделью.",
        }

    if shared_numbers and len(user_token_set) >= 3 and len(correct_token_set) >= 3:
        if jaccard >= _VERY_HIGH_JACCARD_THRESHOLD:
            return {
                "score": 95,
                "rationale": "Ответ очень близок к правильному по ключевым словам и общей логике.",
            }
        if jaccard >= _HIGH_JACCARD_THRESHOLD:
            return {
                "score": 88,
                "rationale": "Ответ в основном совпадает с правильной логикой по ключевым словам.",
            }

    return None


def _score_exam_answer_cached_or_estimated(
    client,
    *,
    cache: AiCache,
    user_answer: str,
    correct_answer: str,
    column: str = "",
    question: str = "",
    exam_type: str = "",
    key_points: list[str] | None = None,
) -> tuple[dict[str, object], bool]:
    use_heuristic = not (str(question).strip() or str(exam_type).strip() or list(key_points or []))
    heuristic = _estimate_exam_score_without_llm(user_answer=user_answer, correct_answer=correct_answer) if use_heuristic else None
    if heuristic is not None:
        return heuristic, False

    cache_key = _build_exam_score_cache_key(
        cache,
        user_answer=user_answer,
        correct_answer=correct_answer,
        column=column,
        question=question,
        exam_type=exam_type,
        key_points=key_points,
    )
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return _normalize_exam_result(cached, fallback_rationale=DEFAULT_EXAM_RATIONALE), False

    response = client.responses.create(
        model=OPENAI_EXAM_SCORING_MODEL,
        input=build_exam_scoring_prompt(
            user_answer=user_answer,
            correct_answer=correct_answer,
            column=column,
            question=question,
            exam_type=exam_type,
            key_points=key_points,
        ),
    )
    payload = _extract_json_object(extract_response_text(response))
    result = _normalize_exam_result(payload, fallback_rationale=DEFAULT_EXAM_RATIONALE)
    cache.set(cache_key, result)
    return result, True


def _empty_exam_batch_stats() -> dict[str, int]:
    return {
        "answer_count": 0,
        "heuristic_count": 0,
        "cache_hit_count": 0,
        "llm_count": 0,
        "llm_calls": 0,
    }


def score_exam_answer(
    client,
    *,
    user_answer: str,
    correct_answer: str,
    column: str = "",
    question: str = "",
    exam_type: str = "",
    key_points: list[str] | None = None,
) -> dict[str, object]:
    cache = get_ai_cache()
    result, _ = _score_exam_answer_cached_or_estimated(
        client,
        cache=cache,
        user_answer=user_answer,
        correct_answer=correct_answer,
        column=column,
        question=question,
        exam_type=exam_type,
        key_points=key_points,
    )
    return result


def extract_principal_fields_with_proxy_fallback(
    *,
    api_key: str,
    proxy_url: str,
    image_data_url: str,
    status_callback: Callable[[str], None] | None = None,
) -> dict[str, object]:
    return _run_with_proxy_fallback(
        api_key=api_key,
        proxy_url=proxy_url,
        operation_name="principal field extraction",
        operation_kind="ocr",
        operation=lambda client: extract_principal_fields(client=client, image_data_url=image_data_url),
        status_callback=status_callback,
        direct_status="Подключение к OpenAI без прокси...",
        proxy_status="Прямой запрос не прошел, пробую через прокси...",
    )


def suggest_description_with_proxy_fallback(
    api_key: str,
    proxy_url: str,
    victim_name: str,
    org: str,
    subject: str,
    event_dt: str,
    raw_desc: str,
    complaint_basis: str = "",
    main_focus: str = "",
    law_context: str = "",
    *,
    status_callback: Callable[[str], None] | None = None,
) -> str:
    return _run_with_proxy_fallback(
        api_key=api_key,
        proxy_url=proxy_url,
        operation_name="description suggestion",
        operation_kind="text",
        operation=lambda client: suggest_description(
            client=client,
            victim_name=victim_name,
            org=org,
            subject=subject,
            event_dt=event_dt,
            raw_desc=raw_desc,
            complaint_basis=complaint_basis,
            main_focus=main_focus,
            law_context=law_context,
        ),
        status_callback=status_callback,
        direct_status="Подключение к OpenAI без прокси...",
        proxy_status="Прямой запрос не прошел, пробую через прокси...",
    )


def score_exam_answer_with_proxy_fallback(
    *,
    api_key: str,
    proxy_url: str,
    user_answer: str,
    correct_answer: str,
    column: str = "",
    question: str = "",
    exam_type: str = "",
    key_points: list[str] | None = None,
) -> dict[str, object]:
    return _run_with_proxy_fallback(
        api_key=api_key,
        proxy_url=proxy_url,
        operation_name="single exam scoring",
        operation_kind="exam_single",
        operation=lambda client: score_exam_answer(
            client=client,
            user_answer=user_answer,
            correct_answer=correct_answer,
            column=column,
            question=question,
            exam_type=exam_type,
            key_points=key_points,
        ),
    )


def score_exam_answers_batch_with_proxy_fallback(
    *,
    api_key: str,
    proxy_url: str,
    items: list[dict[str, object]],
    return_stats: bool = False,
) -> dict[str, dict[str, object]] | tuple[dict[str, dict[str, object]], dict[str, int]]:
    stats = _empty_exam_batch_stats()
    stats["answer_count"] = len(items)
    if not items:
        return ({}, stats) if return_stats else {}

    exact_results: dict[str, dict[str, object]] = {}
    pending_items: list[dict[str, str]] = []
    cache = get_ai_cache()
    for item in items:
        column = item["column"]
        user_answer = item["user_answer"]
        correct_answer = item["correct_answer"]
        use_heuristic = not (
            str(item.get("question") or "").strip()
            or str(item.get("exam_type") or "").strip()
            or list(item.get("key_points") or [])
        )
        heuristic = _estimate_exam_score_without_llm(user_answer=user_answer, correct_answer=correct_answer) if use_heuristic else None
        if heuristic is not None:
            exact_results[column] = heuristic
            stats["heuristic_count"] += 1
            continue

        cache_key = _build_exam_score_cache_key(cache, user_answer=user_answer, correct_answer=correct_answer)
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            exact_results[column] = _normalize_exam_result(cached, fallback_rationale=DEFAULT_EXAM_RATIONALE)
            stats["cache_hit_count"] += 1
            continue
        pending_items.append(item)

    if not pending_items:
        return (exact_results, stats) if return_stats else exact_results

    def _chunk_items(chunk_items: list[dict[str, str]]) -> str:
        return "\n".join(
            (
                f'[{item["column"]}]'
                f'\nExam type: {item.get("exam_type", "")}'
                f'\nQuestion: {item.get("question") or item["header"]}'
                f'\nquestion_type: {item.get("question_type", "standard")}'
                f'\ncandidate_answer: {item["user_answer"]}'
                f'\nDraft reference answer: {item["correct_answer"]}'
                f'\nMinimal required points:\n'
                + "\n".join(f'- {point}' for point in (item.get("key_points") or []))
                + f'\nmust_not_include:\n'
                + "\n".join(f'- {point}' for point in (item.get("must_not_include") or []))
                + f'\nfatal_errors:\n'
                + "\n".join(f'- {point}' for point in (item.get("fatal_errors") or []))
            )
            for item in chunk_items
        )

    def run(client):
        all_results: dict[str, dict[str, object]] = {}
        for start in range(0, len(pending_items), _BATCH_SCORING_CHUNK_SIZE):
            chunk_items = pending_items[start : start + _BATCH_SCORING_CHUNK_SIZE]
            cache_key = cache.build_key(
                operation="score_exam_answers_batch",
                model=OPENAI_EXAM_SCORING_MODEL,
                payload={
                    "prompt_version": EXAM_BATCH_SCORING_PROMPT_VERSION,
                    "items": [
                        {
                            "column": item["column"],
                            "header": item["header"],
                            "question": item.get("question", ""),
                            "exam_type": item.get("exam_type", ""),
                            "key_points": [str(point).strip() for point in (item.get("key_points") or []) if str(point).strip()],
                            "normalized_user_answer": _normalize_exam_answer(item["user_answer"]),
                            "normalized_correct_answer": _normalize_exam_answer(item["correct_answer"]),
                        }
                        for item in chunk_items
                    ],
                },
            )
            cached_chunk = cache.get(cache_key)
            if isinstance(cached_chunk, dict):
                all_results.update(cached_chunk)
                stats["cache_hit_count"] += len(chunk_items)
                continue

            prompt = build_batch_exam_scoring_prompt(prompt_items=_chunk_items(chunk_items))
            stats["llm_calls"] += 1
            stats["llm_count"] += len(chunk_items)
            response = client.responses.create(model=OPENAI_EXAM_SCORING_MODEL, input=prompt)
            raw = _extract_json_object(extract_response_text(response))
            raw_by_column = _extract_batch_results_map(raw)
            chunk_results: dict[str, dict[str, object]] = {}
            for item in chunk_items:
                column = item["column"]
                payload = raw_by_column.get(str(column or "").upper())
                normalized_result = _normalize_exam_result(payload, fallback_rationale=DEFAULT_INVALID_BATCH_RATIONALE)
                chunk_results[column] = normalized_result
                per_item_cache_key = _build_exam_score_cache_key(
                    cache,
                    user_answer=item["user_answer"],
                    correct_answer=item["correct_answer"],
                    column=str(item.get("column") or ""),
                    question=str(item.get("question") or item.get("header") or ""),
                    exam_type=str(item.get("exam_type") or ""),
                    key_points=[str(point).strip() for point in (item.get("key_points") or []) if str(point).strip()],
                )
                cache.set(per_item_cache_key, normalized_result)
            cache.set(cache_key, chunk_results)
            all_results.update(chunk_results)
        return all_results

    batch_results = _run_with_proxy_fallback(
        api_key=api_key,
        proxy_url=proxy_url,
        operation_name="batch exam scoring",
        operation_kind="exam_batch",
        operation=run,
    )
    exact_results.update(batch_results)
    return (exact_results, stats) if return_stats else exact_results
