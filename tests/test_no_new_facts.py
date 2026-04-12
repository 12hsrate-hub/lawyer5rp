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
