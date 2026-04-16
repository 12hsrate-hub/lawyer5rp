from __future__ import annotations

import pytest

from shared import ogp_ai


def test_canonicalize_exam_item_sets_rubric_and_normalizes_quotes():
    item = ogp_ai._canonicalize_exam_item(
        {
            "column": "F",
            "question": "  Что такое «Поправка—7»?  ",
            "user_answer": "  Ссылка на “Поправка 7”. ",
            "correct_answer": "Поправка 7",
            "question_type": "EXACT_REF",
        }
    )
    assert item["rubric_version"] == "gta5rp_legal_v3"
    assert item["question_type"] == "exact_ref"
    assert item["question"] == 'Что такое "Поправка-7"?'
    assert item["candidate"] == 'Ссылка на "Поправка 7".'


def test_precheck_marks_empty_and_fatal_only():
    empty_item = ogp_ai._canonicalize_exam_item({"column": "A", "user_answer": " - "})
    empty = ogp_ai._precheck_exam_item(empty_item)
    assert empty["auto_decision"] == "empty"
    assert int(empty["result"]["score"]) == 1

    na_item = ogp_ai._canonicalize_exam_item({"column": "A2", "user_answer": "N/A"})
    na_result = ogp_ai._precheck_exam_item(na_item)
    assert na_result["auto_decision"] == "empty"

    fatal_item = ogp_ai._canonicalize_exam_item(
        {
            "column": "B",
            "user_answer": "Нужно нарушить ст. 7 прямо сейчас.",
            "fatal_errors": ["нарушить ст. 7"],
        }
    )
    fatal = ogp_ai._precheck_exam_item(fatal_item)
    assert fatal["auto_decision"] == "fatal_conflict"
    assert fatal["result"]["fatal_conflict"] is True

    negated_item = ogp_ai._canonicalize_exam_item(
        {
            "column": "C",
            "user_answer": "Нельзя, не Поправка 7.",
            "fatal_errors": ["Поправка 7"],
        }
    )
    negated = ogp_ai._precheck_exam_item(negated_item)
    assert negated["auto_decision"] == "llm"

    broader_negation_item = ogp_ai._canonicalize_exam_item(
        {
            "column": "D",
            "user_answer": "Нельзя нарушить ст. 7 ни при каких условиях.",
            "fatal_errors": ["нарушить ст. 7"],
        }
    )
    broader_negation = ogp_ai._precheck_exam_item(broader_negation_item)
    assert broader_negation["auto_decision"] == "llm"


def test_build_exam_batches_by_budget_separates_long_cases():
    short_item = ogp_ai._canonicalize_exam_item(
        {"column": "F", "question": "Q", "user_answer": "короткий ответ", "correct_answer": "короткий эталон"}
    )
    long_text = " ".join(["длинный"] * 1200)
    long_item = ogp_ai._canonicalize_exam_item(
        {"column": "G", "question": "Q2", "user_answer": long_text, "correct_answer": "эталон"}
    )
    batches = ogp_ai._build_exam_batches_by_budget([short_item, long_item], hard_item_limit=10)
    assert len(batches) >= 2
    assert any(batch[0]["column"] == "F" for batch in batches)
    assert any(batch[0]["column"] == "G" for batch in batches)


def test_exam_score_cache_key_changes_with_rubric_metadata():
    cache = ogp_ai.get_ai_cache()
    base_key = ogp_ai._build_exam_score_cache_key(
        cache,
        user_answer="alpha",
        correct_answer="beta",
        column="F",
        question="question",
        exam_type="remote",
        question_type="standard",
        rubric_version="gta5rp_legal_v3",
        key_points=["k1"],
        must_not_include=[],
        fatal_errors=[],
    )
    changed_key = ogp_ai._build_exam_score_cache_key(
        cache,
        user_answer="alpha",
        correct_answer="beta",
        column="F",
        question="question",
        exam_type="remote",
        question_type="exact_ref",
        rubric_version="gta5rp_legal_v4",
        key_points=["k1"],
        must_not_include=["wrong ref"],
        fatal_errors=["fatal"],
    )

    assert base_key != changed_key


@pytest.mark.parametrize(
    ("user_answer", "expected_min"),
    [
        ("Это 23 ПК п.в), п.б)", 82),
        ("ст.23 ПК", 55),
        ("23ПК", 55),
    ],
)
def test_exact_ref_partial_and_compact_reference_get_reasonable_floor(user_answer: str, expected_min: int):
    item = ogp_ai._canonicalize_exam_item(
        {
            "column": "F",
            "question_type": "exact_ref",
            "user_answer": user_answer,
            "correct_answer": 'п. "в" ст. 23 Процессуального Кодекса (ПК)',
        }
    )
    calibrated = ogp_ai._calibrate_exam_result(item, {"score": 20, "rationale": "low"})
    assert int(calibrated["score"]) >= expected_min


def test_exact_ref_wrong_reference_does_not_get_partial_exact_floor():
    item = ogp_ai._canonicalize_exam_item(
        {
            "column": "F",
            "question_type": "exact_ref",
            "user_answer": "ст.24 АК",
            "correct_answer": 'п. "в" ст. 23 ПК',
        }
    )
    calibrated = ogp_ai._calibrate_exam_result(item, {"score": 20, "rationale": "low"})
    assert int(calibrated["score"]) == 20


def test_standard_question_partial_key_points_not_collapsing_to_zero_like_band():
    item = ogp_ai._canonicalize_exam_item(
        {
            "column": "G",
            "question_type": "standard",
            "user_answer": "обязан назвать основания при обыске/досмотре, по остановке ТС сотрудник объявляет требование",
            "correct_answer": "ч.2 ст.3 ДК и ч.4 ст.29 ПК",
            "key_points": ["остановке ТС", "обыске либо досмотре", "ч. 2 ст. 3 ДК"],
        }
    )
    calibrated = ogp_ai._calibrate_exam_result(item, {"score": 10, "rationale": "low"})
    assert int(calibrated["score"]) >= 45


def test_abbreviations_and_compact_legal_notation_are_normalized_for_matching():
    item = ogp_ai._canonicalize_exam_item(
        {
            "column": "H",
            "question_type": "standard",
            "user_answer": "когда задержан по приказу губера вице-губера ЗПВС ПВС ЗГП ГП и по решению суда",
            "correct_answer": "когда задержан по приказу губернатора, вице-губернатора, председателя ВС, зампреда ВС, генпрокурора, замгенпрокурора и по решению суда",
            "key_points": ["приказу губернатора", "председатель", "генерального прокурора", "решению суда"],
        }
    )
    calibrated = ogp_ai._calibrate_exam_result(item, {"score": 25, "rationale": "low"})
    assert int(calibrated["score"]) >= 45


def test_compact_article_part_notation_keeps_partial_credit_for_principle_plus_exception():
    item = ogp_ai._canonicalize_exam_item(
        {
            "column": "I",
            "question_type": "standard",
            "user_answer": "невиновен пока не доказано, 16ч4 ПК - боло-розыск",
            "correct_answer": "презумпция невиновности по ст. 6 ПК и исключение bolo-розыск по ст. 16 ч. 4 ПК",
            "key_points": ["невиновен пока не доказано", "ст. 16 ч. 4 ПК", "bolo-розыск"],
        }
    )
    calibrated = ogp_ai._calibrate_exam_result(item, {"score": 30, "rationale": "low"})
    assert int(calibrated["score"]) >= 60


def test_correct_core_action_with_nonfatal_extra_details_gets_moderate_penalty_only():
    item = ogp_ai._canonicalize_exam_item(
        {
            "column": "J",
            "question_type": "standard",
            "user_answer": "16ч3 попросить разрешения на ношение, затем проверить и уже потом решать по задержанию",
            "correct_answer": "запросить документы/основание по ч.3 ст.16 ПК, не переходить сразу к задержанию",
            "key_points": ["ч.3 ст.16", "запросить документы", "не переходить сразу к задержанию"],
        }
    )
    calibrated = ogp_ai._calibrate_exam_result(item, {"score": 25, "rationale": "low"})
    assert int(calibrated["score"]) >= 55


def test_correct_main_conclusion_with_imperfect_explanation_gets_partial_credit():
    item = ogp_ai._canonicalize_exam_item(
        {
            "column": "K",
            "question_type": "standard",
            "user_answer": "ч1 после штрафа на протяжении 3-х дней можно выписывать ч2. после ареста 20 дней.",
            "correct_answer": "ч.1 ст.48 АК, так как через 4 дня после штрафа рецидива нет",
            "key_points": ["ч.1 ст.48", "через 4 дня", "рецидива нет"],
        }
    )
    calibrated = ogp_ai._calibrate_exam_result(item, {"score": 35, "rationale": "low"})
    assert int(calibrated["score"]) >= 45


def test_list_all_one_correct_variant_with_omissions_gets_non_trivial_partial_credit():
    item = ogp_ai._canonicalize_exam_item(
        {
            "column": "L",
            "question_type": "list_all",
            "user_answer": "72 часа через суд, остальное не помню",
            "correct_answer": "48 часов через ОГП; 72 часа через суд; 7 дней в исключительных случаях",
            "key_points": ["48 часов через ОГП", "72 часа через суд", "7 дней в исключительных случаях"],
        }
    )
    calibrated = ogp_ai._calibrate_exam_result(item, {"score": 10, "rationale": "low"})
    assert int(calibrated["score"]) >= 35


def test_reference_only_without_required_content_gets_partial_but_not_high_score():
    item = ogp_ai._canonicalize_exam_item(
        {
            "column": "M",
            "question_type": "standard",
            "user_answer": "ст.6 ПК",
            "correct_answer": "презумпция невиновности + исключение bolo-розыск (ст.16 ч.4 ПК)",
            "key_points": ["презумпция невиновности", "исключение bolo-розыск"],
        }
    )
    calibrated = ogp_ai._calibrate_exam_result(item, {"score": 25, "rationale": "low"})
    assert 25 <= int(calibrated["score"]) <= 45
