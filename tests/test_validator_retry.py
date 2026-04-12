from __future__ import annotations

from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_retry_policy_caps_retries_at_one() -> None:
    payload = yaml.safe_load((ROOT_DIR / "config" / "retry_policy.yaml").read_text(encoding="utf-8"))
    assert payload["retry_policy"]["max_retries"] == 1


def test_factual_integrity_fail_is_non_retryable_everywhere() -> None:
    retry_payload = yaml.safe_load((ROOT_DIR / "config" / "retry_policy.yaml").read_text(encoding="utf-8"))
    quality_payload = yaml.safe_load((ROOT_DIR / "config" / "quality_gates.yaml").read_text(encoding="utf-8"))

    assert "factual_integrity_fail" in retry_payload["non_retryable_failures"]
    assert retry_payload["fallbacks"]["factual_integrity_fail"] == "factual_only"
    assert quality_payload["gates"]["factual_integrity"]["retry_allowed"] is False
    assert quality_payload["gates"]["factual_integrity"]["max_retries"] == 0

