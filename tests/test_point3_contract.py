from __future__ import annotations

from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_prompt_contract_has_required_modes() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "prompt_contract.yaml").read_text(encoding="utf-8"))
    assert payload["modes"] == ["factual_only", "factual_plus_legal"]
    assert payload["global_rules"]["weak_context_mode"] == "factual_only"


def test_quality_gates_have_factual_integrity_fallback() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "quality_gates.yaml").read_text(encoding="utf-8"))
    gate = payload["gates"]["factual_integrity"]
    assert gate["target"] == 1.00
    assert gate["on_fail"] == "fallback_factual_only"
    assert gate["retry_allowed"] is False
    assert gate["max_retries"] == 0

