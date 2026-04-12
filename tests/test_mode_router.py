from __future__ import annotations

from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_relevance_thresholds_define_t1_t2_routing() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "relevance_thresholds.yaml").read_text(encoding="utf-8"))
    assert payload["thresholds"]["t1_high_relevance"]["mode"] == "factual_plus_legal"
    assert payload["thresholds"]["t2_low_relevance"]["mode"] == "factual_only"
    assert payload["routing_rules"]["at_or_above_t1"] == "factual_plus_legal"
    assert payload["routing_rules"]["below_t2"] == "factual_only"


def test_feature_flags_define_rollout_force_and_emergency_controls() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "feature_flags.yaml").read_text(encoding="utf-8"))
    flag = payload["flags"]["rollout_legal_mode"]
    assert flag["enabled"] is True
    assert "force_mode" in flag
    assert "emergency_off" in flag

