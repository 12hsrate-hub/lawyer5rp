from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.point3_pipeline import (
    apply_validation_remediation,
    build_point3_pipeline_context,
    build_safe_fallback_paragraph,
    validate_generated_paragraph,
)


def test_validator_flags_new_entity_and_url() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text="Доверитель сообщает о задержании и просит проверить обстоятельства.",
        retrieval_status="no_context",
        retrieval_confidence="low",
        retrieved_law_context="",
        selected_norms=(),
    )

    result = validate_generated_paragraph(
        "Ivan Petrov сообщил дополнительные сведения, ссылка: https://bad.example",
        context,
    )

    assert "new_entity" in result.blocker_codes
    assert "new_url" in result.blocker_codes


def test_remediator_softens_danger_phrase_without_full_regeneration() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text="Доверитель сообщает о задержании и просит проверить обстоятельства.",
        retrieval_status="no_context",
        retrieval_confidence="low",
        retrieved_law_context="",
        selected_norms=(),
    )

    outcome = apply_validation_remediation("Действия незаконны и без оснований.", context)

    assert outcome.validation.status != "fail"
    assert "требуют правовой оценки" in outcome.text or "вызывает сомнения" in outcome.text


def test_safe_fallback_template_is_one_paragraph_with_four_sentences() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text="Доверитель сообщает о задержании. В черновике указано на спорность оснований.",
        retrieval_status="no_context",
        retrieval_confidence="low",
        retrieved_law_context="",
        selected_norms=(),
    )

    paragraph = build_safe_fallback_paragraph(context)

    assert "\n" not in paragraph
    assert paragraph.count(".") >= 4
    assert "ст." not in paragraph.lower()


def test_remediation_adds_document_titles_to_article_references() -> None:
    context = build_point3_pipeline_context(
        complainant="Test Principal",
        organization="LSPD",
        target_person="Test Officer",
        event_datetime="12.04.2026 18:10",
        draft_text=(
            "Человека задержали на территории Maze Bank Arena из-за ношения маски, "
            "а затем провели обыск и изъяли имущество."
        ),
        retrieval_status="normal_context",
        retrieval_confidence="high",
        retrieved_law_context="Источник: https://laws.example/mixed\nНормы: Статья 18, Статья 29",
        selected_norms=(
            {
                "source_url": "https://laws.example/admin",
                "document_title": "Административный кодекс штата Сан-Андреас",
                "article_label": "Статья 18",
                "excerpt": "Ношение маски допускается на территории Maze Bank Arena.",
                "score": 95,
                "qualifiers": (
                    {
                        "kind": "exception",
                        "text": "Ношение маски допускается на территории Maze Bank Arena.",
                    },
                ),
            },
            {
                "source_url": "https://laws.example/processual",
                "document_title": "Процессуальный кодекс штата Сан-Андреас",
                "article_label": "Статья 29",
                "excerpt": "Порядок проведения личного обыска и изъятия имущества.",
                "score": 91,
            },
        ),
    )

    outcome = apply_validation_remediation(
        "Действия требуют проверки на соответствие статье 18 и статье 29.",
        context,
    )

    lowered = outcome.text.lower()
    assert "статье 18 (административный кодекс штата сан-андреас)" in lowered
    assert "статье 29 (процессуальный кодекс штата сан-андреас)" in lowered


def test_remediation_explicitly_states_mask_exception_rule() -> None:
    context = build_point3_pipeline_context(
        complainant="Test Principal",
        organization="LSPD",
        target_person="Test Officer",
        event_datetime="12.04.2026 18:10",
        draft_text=(
            "Человека задержали на территории Maze Bank Arena из-за ношения маски, "
            "потребовали снять её без внятного основания, а после отказа оформили задержание."
        ),
        retrieval_status="normal_context",
        retrieval_confidence="high",
        retrieved_law_context="Источник: https://laws.example/admin\nНорма: Статья 18",
        selected_norms=(
            {
                "source_url": "https://laws.example/admin",
                "document_title": "Административный кодекс штата Сан-Андреас",
                "article_label": "Статья 18",
                "excerpt": "Ношение маски допускается в развлекательных учреждениях.",
                "score": 96,
                "qualifiers": (
                    {
                        "kind": "exception",
                        "text": "Ношение маски на территории Maze Bank Arena допускается как исключение.",
                    },
                ),
            },
        ),
    )

    outcome = apply_validation_remediation(
        "Требуется проверить действия сотрудника на соответствие статье 18 с учетом указанного исключения.",
        context,
    )

    lowered = outcome.text.lower()
    assert "maze bank arena" in lowered
    assert "допуска" in lowered
