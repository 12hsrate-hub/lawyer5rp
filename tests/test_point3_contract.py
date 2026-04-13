from __future__ import annotations

from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_prompt_contract_has_required_modes() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "prompt_contract.yaml").read_text(encoding="utf-8"))
    assert payload["modes"] == ["legal_grounded", "factual_fallback_expanded"]
    assert payload["global_rules"]["weak_context_mode"] == "factual_fallback_expanded"
    assert payload["global_rules"]["sentence_range"] == {"min": 4, "max": 7}


def test_quality_gates_have_factual_integrity_fallback() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "quality_gates.yaml").read_text(encoding="utf-8"))
    gate = payload["gates"]["factual_integrity"]
    assert gate["target"] == 1.00
    assert gate["on_fail"] == "fallback_factual_fallback_expanded"
    assert gate["retry_allowed"] is True
    assert gate["max_retries"] == 2


def test_validator_rules_define_blockers_and_assessment_phrases() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "validator_rules.yaml").read_text(encoding="utf-8"))
    assert "article_without_valid_trigger" in payload["blockers"]
    assert "strong_unconfirmed_qualification" in payload["blockers"]
    assert "требует проверки" in payload["employee_assessment_phrases"]
