from __future__ import annotations

from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_retry_policy_caps_retries_at_one() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "retry_policy.yaml").read_text(encoding="utf-8"))
    assert payload["retry_policy"]["max_retries"] == 2


def test_validator_blocker_retries_and_falls_back_to_expanded_mode() -> None:
    retry_payload = yaml.safe_load((ROOT_DIR / "config" / "retry_policy.yaml").read_text(encoding="utf-8"))
    quality_payload = yaml.safe_load((ROOT_DIR / "config" / "quality_gates.yaml").read_text(encoding="utf-8"))

    assert "validator_blocker" in retry_payload["retryable_failures"]
    assert retry_payload["fallbacks"]["validator_blocker"] == "factual_fallback_expanded"
    assert quality_payload["gates"]["factual_integrity"]["retry_allowed"] is True
    assert quality_payload["gates"]["factual_integrity"]["max_retries"] == 2
