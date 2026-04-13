from __future__ import annotations

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
