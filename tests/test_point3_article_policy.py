from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.schemas import SuggestPayload
from ogp_web.services.ai_service import SuggestContextBuildResult, suggest_text_details
from ogp_web.services.law_bundle_service import LawChunk
from ogp_web.services.law_retrieval_service import LawRetrievalMatch
from ogp_web.services import ai_service
from ogp_web.services.point3_policy_service import (
    build_safe_factual_fallback,
    select_applicable_articles,
    validate_suggest_output,
)
from shared.ogp_ai_prompts import build_suggest_prompt_spec


FIXTURE_PATH = ROOT_DIR / "tests" / "fixtures" / "point3_legal_conflicts.jsonl"


def _make_match(item: dict[str, str]) -> LawRetrievalMatch:
    return LawRetrievalMatch(
        chunk=LawChunk(
            url=item["url"],
            document_title=item["document_title"],
            article_label=item["article_label"],
            text=item["excerpt"],
        ),
        score=100,
        excerpt=item["excerpt"],
    )


def test_point3_conflict_fixture_cases() -> None:
    rows = [json.loads(line) for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 3

    for row in rows:
        payload = SuggestPayload(**row["payload"])
        if "matches" in row:
            result = select_applicable_articles(
                server_code="blackberry",
                payload=payload,
                matches=[_make_match(item) for item in row["matches"]],
            )
            assert result.mode == row["expected_mode"]
            assert list(result.allowed_article_numbers) == row["expected_articles"]
        else:
            validation = validate_suggest_output(
                text=row["output"],
                payload=payload,
                server_code="blackberry",
                allowed_article_numbers=row["allowed_articles"],
                allow_article_citations=bool(row["allow_article_citations"]),
            )
            assert validation.status == "fail"
            assert list(validation.error_codes) == row["expected_validation_errors"]


def test_safe_factual_fallback_returns_single_plain_paragraph() -> None:
    payload = SuggestPayload(
        victim_name="Иван Иванов",
        org="LSPD",
        subject="Officer North",
        event_dt="08.04.2026 14:30",
        raw_desc="- Мне не дали адвоката.\n- Затем https://example.com/hidden",
        complaint_basis="wrongful_article",
        main_focus="допуск адвоката",
    )
    text = build_safe_factual_fallback(payload)
    assert "\n\n" not in text
    assert "http" not in text.lower()
    assert "ст." not in text.lower()


def test_data_driven_prompt_forces_article_trigger_contract() -> None:
    spec = build_suggest_prompt_spec(
        victim_name="Иван Иванов",
        org="LSPD",
        subject="Officer North",
        event_dt="08.04.2026 14:30",
        raw_desc="После задержания мне не дали адвоката.",
        complaint_basis="wrongful_article",
        main_focus="допуск адвоката",
        law_context="Норма: Статья 17",
        prompt_mode="data_driven",
        applicability_notes="Применимые нормы: статья 17 только по триггеру не дали адвоката.",
        force_factual_only=True,
    )
    assert "[applicability_notes]" in spec.text
    assert "упоминать статью можно только при прямом факт-триггере" in spec.text
    assert "если прямых триггеров нет, пиши один абзац без ссылок на статьи" in spec.text
    assert "режим factual_only обязателен" in spec.text


def test_suggest_text_retries_once_after_validation_failure() -> None:
    original_suggest = ai_service.suggest_description_with_proxy_fallback_result
    original_build_context = ai_service._build_suggest_law_context
    calls: list[dict[str, object]] = []

    def fake_context(**kwargs):
        return SuggestContextBuildResult(
            context_text="Источник: https://laws.example\nНорма: Статья 17\nФрагмент: Право на адвоката.",
            retrieval_confidence="high",
            retrieval_context_mode="normal_context",
            retrieval_profile="suggest",
            bundle_status="fresh",
            bundle_generated_at="2026-04-12T10:00:00+00:00",
            bundle_fingerprint="bundle-1",
            selected_norms_count=1,
            applicability_mode="factual_plus_legal",
            applicability_notes="Применимые нормы по прямым факт-триггерам во входе:\n- Процессуальный кодекс, статьи 17: использовать только потому, что во входе есть триггеры [не дали адвоката].",
            allowed_article_numbers=("17",),
        )

    def fake_suggest(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return ai_service.TextGenerationResult(
                text="Сотрудник нарушил ст. 74 и скрыл материалы дела 09.04.2026.",
                usage=ai_service.AiUsageSummary(input_tokens=20, output_tokens=10, total_tokens=30),
                cache_hit=False,
                attempt_path="direct",
                attempt_duration_ms=120,
                route_policy="direct_first",
            )
        return ai_service.TextGenerationResult(
            text="После задержания сотрудник не обеспечил право на адвоката, что подтверждается изложенными в черновике обстоятельствами и требует проверки законности его действий по указанному эпизоду.",
            usage=ai_service.AiUsageSummary(input_tokens=24, output_tokens=12, total_tokens=36),
            cache_hit=False,
            attempt_path="direct_retry",
            attempt_duration_ms=140,
            route_policy="direct_first",
        )

    ai_service._build_suggest_law_context = fake_context
    ai_service.suggest_description_with_proxy_fallback_result = fake_suggest
    try:
        result = suggest_text_details(
            SuggestPayload(
                victim_name="Иван Иванов",
                org="LSPD",
                subject="Officer North",
                event_dt="08.04.2026 14:30",
                raw_desc="После задержания мне не дали адвоката.",
                complaint_basis="wrongful_article",
                main_focus="допуск адвоката",
            ),
            server_code="blackberry",
        )
    finally:
        ai_service.suggest_description_with_proxy_fallback_result = original_suggest
        ai_service._build_suggest_law_context = original_build_context

    assert len(calls) == 2
    assert result.validation_status == "pass_after_retry"
    assert result.validation_retry_count == 1
    assert "suggest_validation_retry" in result.warnings
    assert "new_fact_detected" in result.validation_errors
    assert calls[1]["validation_error"]


def test_suggest_text_uses_safe_fallback_after_second_validation_failure() -> None:
    original_suggest = ai_service.suggest_description_with_proxy_fallback_result
    original_build_context = ai_service._build_suggest_law_context

    def fake_context(**kwargs):
        return SuggestContextBuildResult(
            context_text="",
            retrieval_confidence="medium",
            retrieval_context_mode="low_confidence_context",
            retrieval_profile="suggest",
            bundle_status="fresh",
            bundle_generated_at="2026-04-12T10:00:00+00:00",
            bundle_fingerprint="bundle-1",
            selected_norms_count=0,
            applicability_mode="factual_only",
            applicability_notes="Прямые факт-триггеры для статей во входе не найдены. Пиши только нейтральный фактический абзац без ссылок на статьи.",
            allowed_article_numbers=(),
        )

    def fake_suggest(**kwargs):
        return ai_service.TextGenerationResult(
            text="Сотрудник нарушил ст. 74 и 09.04.2026 составил новый протокол.\n\nИсточник: https://laws.example",
            usage=ai_service.AiUsageSummary(input_tokens=20, output_tokens=10, total_tokens=30),
            cache_hit=False,
            attempt_path="direct",
            attempt_duration_ms=120,
            route_policy="direct_first",
        )

    ai_service._build_suggest_law_context = fake_context
    ai_service.suggest_description_with_proxy_fallback_result = fake_suggest
    try:
        result = suggest_text_details(
            SuggestPayload(
                victim_name="Иван Иванов",
                org="LSPD",
                subject="Officer North",
                event_dt="08.04.2026 14:30",
                raw_desc="Сотрудник отказался представиться.",
                complaint_basis="wrongful_article",
                main_focus="описание обстоятельств",
            ),
            server_code="blackberry",
        )
    finally:
        ai_service.suggest_description_with_proxy_fallback_result = original_suggest
        ai_service._build_suggest_law_context = original_build_context

    assert result.safe_fallback_used is True
    assert result.validation_status == "fallback"
    assert "suggest_safe_factual_fallback" in result.warnings
    assert "ст. 74" not in result.text.lower()
