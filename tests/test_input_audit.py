from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.point3_pipeline import build_point3_pipeline_context


def test_input_audit_collects_safe_warning_codes() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text=(
            "По словам доверителя, его тупо закрыли ни за что. "
            "Возможно, видео есть, но запись не предоставили. "
            "Человек заявил, что его задержали."
        ),
        retrieval_status="no_context",
        retrieval_confidence="low",
        retrieved_law_context="",
        selected_norms=(),
    )

    warning_codes = set(context.input_audit.warning_codes)

    assert "input_reported_speech_detected" in warning_codes
    assert "input_assumption_language_detected" in warning_codes
    assert "input_conflicting_video_status" in warning_codes
    assert "input_ambiguous_actor_reference" in warning_codes


def test_input_audit_tracks_protected_terms_for_prompt_context() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text="Был сделан адвокатский запрос, затем проведен досмотр и задержание, видеозапись отсутствует.",
        retrieval_status="normal_context",
        retrieval_confidence="medium",
        retrieved_law_context="",
        selected_norms=(),
    )

    payload = json.loads(context.prompt_context_json())

    assert "input_audit" in payload
    assert "advocate_request" in payload["input_audit"]["protected_terms"]
    assert "inspection" in payload["input_audit"]["protected_terms"]
    assert "detention" in payload["input_audit"]["protected_terms"]
    assert "video_recording" in payload["input_audit"]["protected_terms"]


def test_input_audit_detects_conflicting_dates() -> None:
    context = build_point3_pipeline_context(
        complainant="Moya Reggroundov",
        organization="FIB",
        target_person="Pavel Clayton",
        event_datetime="02.04.2026 06:57",
        draft_text="Задержание произошло 28.03.2026 02:44, а ниже указано, что арест оформлен 26.03.2026 06:57.",
        retrieval_status="normal_context",
        retrieval_confidence="medium",
        retrieved_law_context="",
        selected_norms=(),
    )

    assert "input_conflicting_dates" in context.input_audit.warning_codes
