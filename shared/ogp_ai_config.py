from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OpenAIConfig:
    text_model: str
    ocr_model: str
    exam_scoring_model: str
    timeout_seconds: float
    connect_timeout_seconds: float
    failfast_connect_timeout_seconds: float
    proxy_only: bool
    route_policy: str
    text_max_concurrency: int
    ocr_max_concurrency: int
    exam_single_max_concurrency: int
    exam_batch_max_concurrency: int


def _read_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _read_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def _resolve_route_policy(raw: str, *, proxy_only: bool) -> str:
    if proxy_only:
        return "proxy_only"
    normalized = str(raw or "").strip().lower()
    if normalized in {"proxy_only", "proxy_first", "direct_first"}:
        return normalized
    return "direct_first"


def load_openai_config() -> OpenAIConfig:
    proxy_only = _read_bool_env("OPENAI_PROXY_ONLY", False)
    return OpenAIConfig(
        text_model=os.getenv("OPENAI_TEXT_MODEL", "gpt-5.4").strip() or "gpt-5.4",
        ocr_model=os.getenv("OPENAI_OCR_MODEL", "gpt-5-mini").strip() or "gpt-5-mini",
        exam_scoring_model=os.getenv("OPENAI_EXAM_SCORING_MODEL", "gpt-5-mini").strip() or "gpt-5-mini",
        timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "120").strip() or "120"),
        connect_timeout_seconds=float(os.getenv("OPENAI_CONNECT_TIMEOUT_SECONDS", "30").strip() or "30"),
        failfast_connect_timeout_seconds=float(
            os.getenv("OPENAI_FAILFAST_CONNECT_TIMEOUT_SECONDS", "5").strip() or "5"
        ),
        proxy_only=proxy_only,
        route_policy=_resolve_route_policy(os.getenv("OPENAI_ROUTE_POLICY", ""), proxy_only=proxy_only),
        text_max_concurrency=_read_positive_int_env("OPENAI_TEXT_MAX_CONCURRENCY", 2),
        ocr_max_concurrency=_read_positive_int_env("OPENAI_OCR_MAX_CONCURRENCY", 1),
        exam_single_max_concurrency=_read_positive_int_env("OPENAI_EXAM_SINGLE_MAX_CONCURRENCY", 2),
        exam_batch_max_concurrency=_read_positive_int_env("OPENAI_EXAM_BATCH_MAX_CONCURRENCY", 1),
    )
