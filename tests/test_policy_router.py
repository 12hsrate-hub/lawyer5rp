from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.point3_pipeline import (
    MODE_FACTUAL_FALLBACK_EXPANDED,
    MODE_LEGAL_GROUNDED,
    build_point3_pipeline_context,
)


def test_policy_router_selects_legal_grounded_for_confirmed_trigger() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text="Доверитель сообщает о задержании и о том, что видеозапись задержания отсутствует.",
        retrieval_status="normal_context",
        retrieval_confidence="high",
        retrieved_law_context="Источник: https://laws.example/processual\nНорма: ст. 23",
        selected_norms=(
            {
                "source_url": "https://laws.example/processual",
                "document_title": "Процессуальный кодекс",
                "article_label": "ст. 23",
                "excerpt": "Сотрудник обязан обеспечить видеозапись задержания.",
                "score": 88,
            },
        ),
    )

    assert context.policy_decision.mode == MODE_LEGAL_GROUNDED
    assert context.policy_decision.valid_triggers_count >= 1
    assert context.policy_decision.avg_confidence >= 0.70


def test_policy_router_selects_fallback_for_low_confidence_borderline_trigger() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text="В черновике указывается на спорность квалификации и недостаточность подтверждающих материалов.",
        retrieval_status="low_confidence_context",
        retrieval_confidence="low",
        retrieved_law_context="Источник: https://laws.example/processual\nНорма: ст. 49",
        selected_norms=(
            {
                "source_url": "https://laws.example/processual",
                "document_title": "Административный кодекс",
                "article_label": "ст. 49",
                "excerpt": "Норма описывает общий порядок оформления процессуальных действий.",
                "score": 75,
            },
        ),
    )

    assert context.policy_decision.mode == MODE_FACTUAL_FALLBACK_EXPANDED
    assert context.policy_decision.reason == "low_confidence_context_borderline_triggers"
