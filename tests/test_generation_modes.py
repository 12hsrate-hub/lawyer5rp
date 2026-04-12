from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from shared.ogp_ai_prompts import SUGGEST_PROMPT_MODE_DATA_DRIVEN, build_suggest_prompt


def test_data_driven_prompt_includes_legal_grounded_mode_section() -> None:
    prompt = build_suggest_prompt(
        victim_name="Victim",
        org="FIB",
        subject="Pavel Clayton",
        event_dt="02.04.2026 06:57",
        raw_desc="Draft facts",
        law_context="Источник: https://laws.example/processual\nНорма: ст. 23",
        prompt_mode=SUGGEST_PROMPT_MODE_DATA_DRIVEN,
        policy_mode="legal_grounded",
        pipeline_context='{"policy_decision":{"mode":"legal_grounded"}}',
        retrieval_context_mode="normal_context",
    )

    assert "Mode: legal_grounded" in prompt
    assert "[pipeline_context]" in prompt
    assert "valid triggers" in prompt


def test_data_driven_prompt_includes_fallback_mode_section() -> None:
    prompt = build_suggest_prompt(
        victim_name="Victim",
        org="FIB",
        subject="Pavel Clayton",
        event_dt="02.04.2026 06:57",
        raw_desc="Draft facts",
        law_context="",
        prompt_mode=SUGGEST_PROMPT_MODE_DATA_DRIVEN,
        policy_mode="factual_fallback_expanded",
        pipeline_context='{"policy_decision":{"mode":"factual_fallback_expanded"}}',
        retrieval_context_mode="no_context",
    )

    assert "Mode: factual_fallback_expanded" in prompt
    assert "Do not cite article numbers" in prompt
    assert "один связный текст" in prompt
