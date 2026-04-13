from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.point3_pipeline import build_point3_pipeline_context, validate_generated_paragraph


def test_validator_blocks_articles_dates_and_strong_qualifications_without_valid_trigger() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text="Доверитель сообщает о задержании и спорности оснований.",
        retrieval_status="no_context",
        retrieval_confidence="low",
        retrieved_law_context="",
        selected_norms=(),
    )

    result = validate_generated_paragraph(
        "02.04.2026 действия незаконны, что подтверждается ст. 20, а ссылка приведена здесь: https://bad.example",
        context,
    )

    assert result.status == "fail"
    assert "new_url" in result.blocker_codes
    assert "article_without_valid_trigger" in result.blocker_codes
    assert "strong_unconfirmed_qualification" in result.blocker_codes


def test_validator_warns_when_mask_exception_anchor_is_lost() -> None:
    context = build_point3_pipeline_context(
        complainant="Test Principal 1",
        organization="LSPD",
        target_person="Test Officer 1",
        event_datetime="12.04.2026 18:10",
        draft_text=(
            "Человека задержали на территории Maze Bank Arena из-за ношения маски, "
            "после отказа снять её оформили задержание."
        ),
        retrieval_status="normal_context",
        retrieval_confidence="high",
        retrieved_law_context="Источник: https://laws.example/admin\nНорма: Статья 18",
        selected_norms=(
            {
                "source_url": "https://laws.example/admin",
                "document_title": "Административный кодекс",
                "article_label": "Статья 18",
                "excerpt": "Использование маски допускается в Maze Bank Arena.",
                "score": 92,
            },
        ),
    )

    result = validate_generated_paragraph(
        "На территории арены были совершены спорные действия, которые требуют проверки по представленным материалам.",
        context,
    )

    assert "missing_mask_exception_anchor" in result.warning_codes
