from __future__ import annotations

from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_relevance_thresholds_define_t1_t2_routing() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "policy_thresholds.yaml").read_text(encoding="utf-8"))
    assert payload["thresholds"]["min_valid_trigger_confidence"] == 0.70
    assert payload["thresholds"]["borderline_trigger_confidence_min"] == 0.65
    assert payload["routing"]["valid_trigger_mode"] == "legal_grounded"
    assert payload["routing"]["fallback_mode"] == "factual_fallback_expanded"


def test_feature_flags_define_rollout_force_and_emergency_controls() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "feature_flags.yaml").read_text(encoding="utf-8"))
    flag = payload["flags"]["rollout_legal_mode"]
    assert flag["enabled"] is True
    assert flag["default_mode"] == "factual_fallback_expanded"
    assert "force_mode" in flag
    assert "emergency_off" in flag
