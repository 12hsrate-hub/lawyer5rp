from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OpenAIConfig:
    text_model: str
    ocr_model: str
    exam_scoring_model: str
    exam_scoring_prompt_mode: str
    timeout_seconds: float
    connect_timeout_seconds: float
    failfast_connect_timeout_seconds: float
    proxy_only: bool
    route_policy: str
    text_max_concurrency: int
    ocr_max_concurrency: int
    exam_single_max_concurrency: int
    exam_batch_max_concurrency: int


_DEFAULT_EXAM_SCORING_PROMPT_MODE_FILE = (
    Path(__file__).resolve().parents[1] / "web" / "data" / "exam_scoring_prompt_mode.override"
)


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


def _resolve_exam_scoring_prompt_mode(raw: str) -> str:
    normalized = str(raw or "").strip().lower()
    if normalized == "compact":
        return "compact"
    return "full"


def _resolve_exam_scoring_prompt_mode_file(raw: str) -> str:
    value = str(raw or "").strip()
    if value:
        return value
    return str(_DEFAULT_EXAM_SCORING_PROMPT_MODE_FILE)


def _read_prompt_mode_override(path: str) -> str:
    raw_path = str(path or "").strip()
    if not raw_path:
        return ""
    file_path = Path(raw_path)
    try:
        if not file_path.exists():
            return ""
        return file_path.read_text(encoding="utf-8").splitlines()[0].strip()
    except OSError:
        return ""


def get_runtime_exam_scoring_prompt_mode() -> str:
    env_mode = _resolve_exam_scoring_prompt_mode(os.getenv("OPENAI_EXAM_SCORING_PROMPT_MODE", ""))
    override_path = _resolve_exam_scoring_prompt_mode_file(os.getenv("OPENAI_EXAM_SCORING_PROMPT_MODE_FILE", ""))
    override_raw = _read_prompt_mode_override(override_path)
    if override_raw:
        return _resolve_exam_scoring_prompt_mode(override_raw)
    return env_mode


def load_openai_config() -> OpenAIConfig:
    proxy_only = _read_bool_env("OPENAI_PROXY_ONLY", False)
    return OpenAIConfig(
        text_model=os.getenv("OPENAI_TEXT_MODEL", "gpt-5.4-mini").strip() or "gpt-5.4-mini",
        ocr_model=os.getenv("OPENAI_OCR_MODEL", "gpt-5.4-mini").strip() or "gpt-5.4-mini",
        exam_scoring_model=os.getenv("OPENAI_EXAM_SCORING_MODEL", "gpt-5-mini").strip() or "gpt-5-mini",
        exam_scoring_prompt_mode=_resolve_exam_scoring_prompt_mode(os.getenv("OPENAI_EXAM_SCORING_PROMPT_MODE", "")),
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
