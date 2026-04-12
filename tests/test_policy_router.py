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
        draft_text="В черновике указывается на спорность квалификации и недостаточность подтверждающих процессуальных материалов.",
        retrieval_status="low_confidence_context",
        retrieval_confidence="low",
        retrieved_law_context="Источник: https://laws.example/processual\nНорма: ст. 49",
        selected_norms=(
            {
                "source_url": "https://laws.example/processual",
                "document_title": "Административный кодекс",
                "article_label": "ст. 49",
                "excerpt": "Норма описывает общий порядок оформления процессуальных материалов и действий.",
                "score": 38,
            },
        ),
    )

    assert context.policy_decision.mode == MODE_FACTUAL_FALLBACK_EXPANDED
    assert context.policy_decision.reason == "low_confidence_context_borderline_triggers"


def test_policy_router_does_not_validate_judicial_system_law_without_court_terms() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text="Подписал с человеком договор, после чего был сделан адвокатский запрос, но запись не поступила.",
        retrieval_status="normal_context",
        retrieval_confidence="high",
        retrieved_law_context="Источник: https://laws.example/judicial\nНорма: Статья 2",
        selected_norms=(
            {
                "source_url": "https://laws.example/judicial",
                "document_title": 'Закон "О судебной системе и судопроизводстве"',
                "article_label": "Статья 2",
                "excerpt": "Представитель истца может выступать при наличии заключенного договора.",
                "score": 99,
            },
        ),
    )

    assert context.policy_decision.mode == MODE_FACTUAL_FALLBACK_EXPANDED
    assert context.policy_decision.valid_triggers_count == 0


def test_policy_router_still_validates_advocate_law_for_attorney_request() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text="Был сделан адвокатский запрос, но в ответ запись не поступила.",
        retrieval_status="normal_context",
        retrieval_confidence="high",
        retrieved_law_context="Источник: https://laws.example/advocate\nНорма: Статья 5",
        selected_norms=(
            {
                "source_url": "https://laws.example/advocate",
                "document_title": 'Закон "Об адвокатуре и адвокатской деятельности"',
                "article_label": "Статья 5",
                "excerpt": "Адвокат вправе направлять адвокатский запрос для получения необходимых документов.",
                "score": 99,
            },
        ),
    )

    assert context.policy_decision.mode == MODE_LEGAL_GROUNDED
    assert context.policy_decision.valid_triggers_count == 1


def test_policy_router_prioritizes_article_18_mask_exception_for_maze_bank_arena() -> None:
    context = build_point3_pipeline_context(
        complainant="Test Principal 1",
        organization="LSPD",
        target_person="Test Officer 1",
        event_datetime="12.04.2026 18:10",
        draft_text=(
            "Человека задержали на территории Maze Bank Arena из-за ношения маски, "
            "потребовали снять её без внятного основания, а после отказа оформили задержание."
        ),
        complaint_basis="procedural_violation",
        main_focus="Спорность оснований задержания",
        retrieval_status="normal_context",
        retrieval_confidence="high",
        retrieved_law_context="Источник: https://laws.example/admin\nНорма: Статья 18",
        selected_norms=(
            {
                "source_url": "https://laws.example/admin",
                "document_title": "Административный кодекс",
                "article_label": "Статья 18",
                "excerpt": "Использование маски допустимо на территории Maze Bank Arena и иных развлекательных учреждений.",
                "score": 92,
            },
            {
                "source_url": "https://laws.example/processual",
                "document_title": "Процессуальный кодекс",
                "article_label": "Статья 23.1 Порядок наложения штрафа (тикета)",
                "excerpt": "Сотрудник обязан подготовить тикет и указать сумму штрафа.",
                "score": 35,
            },
        ),
    )

    assert context.policy_decision.mode == MODE_LEGAL_GROUNDED
    assert context.policy_decision.valid_triggers_count == 1
    valid_refs = {item.norm_ref for item in context.triggers if item.is_valid}
    assert "Статья 18" in valid_refs
    assert all("23.1" not in item.norm_ref for item in context.triggers if item.is_valid)


def test_policy_router_requires_state_service_trigger_for_article_19() -> None:
    context = build_point3_pipeline_context(
        complainant="Test Principal 3",
        organization="LSPD",
        target_person="Test Officer 3",
        event_datetime="12.04.2026 18:30",
        draft_text=(
            "Между человеком и сотрудником сначала произошёл личный конфликт, "
            "а спустя короткое время тот же сотрудник уже в служебном статусе вернулся и оформил задержание."
        ),
        retrieval_status="normal_context",
        retrieval_confidence="high",
        retrieved_law_context="Источник: https://laws.example/processual\nНорма: Статья 19",
        selected_norms=(
            {
                "source_url": "https://laws.example/processual",
                "document_title": "Процессуальный кодекс",
                "article_label": "Статья 19",
                "excerpt": "Статья 19. Порядок уведомления и процедуры при задержании сотрудников государственной службы.",
                "score": 95,
            },
        ),
    )

    assert context.policy_decision.mode == MODE_FACTUAL_FALLBACK_EXPANDED
    assert context.policy_decision.valid_triggers_count == 0


def test_policy_router_falls_back_for_personal_conflict_with_only_generic_processual_triggers() -> None:
    context = build_point3_pipeline_context(
        complainant="Test Principal 3",
        organization="LSPD",
        target_person="Test Officer 3",
        event_datetime="12.04.2026 18:30",
        draft_text=(
            "Между человеком и сотрудником сначала произошёл личный конфликт, "
            "а спустя короткое время тот же сотрудник уже в служебном статусе вернулся и оформил задержание."
        ),
        retrieval_status="normal_context",
        retrieval_confidence="high",
        retrieved_law_context="Источник: https://laws.example/processual\nНорма: Статья 17",
        selected_norms=(
            {
                "source_url": "https://laws.example/processual",
                "document_title": "Процессуальный кодекс",
                "article_label": "Статья 17",
                "excerpt": "Статья 17. Общий порядок задержания и разъяснения оснований задержания.",
                "score": 92,
            },
        ),
    )

    assert context.policy_decision.mode == MODE_FACTUAL_FALLBACK_EXPANDED
    assert context.policy_decision.reason == "personal_conflict_requires_factual_fallback"
