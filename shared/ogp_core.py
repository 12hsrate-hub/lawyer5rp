from __future__ import annotations

from shared.ogp_builders import build_ai_prompt, build_bbcode, build_rehab_bbcode
from shared.ogp_constants import (
    BASE_EVIDENCE_FIELDS,
    DATE_PATTERN,
    DEFAULT_SITUATION_PLACEHOLDER,
    DEFAULT_VIOLATION_PLACEHOLDER,
    DT_PATTERN,
    PHONE_DIGITS_PATTERN,
    VIDEO_FIXED_LABEL,
    VIDEO_PROVIDED_LABEL,
)
from shared.ogp_formatting import (
    bb_url,
    build_evidence_line,
    collect_evidence_items,
    escape_bbcode_text,
    format_phone_for_bbcode,
    is_valid_http_url,
    normalize_discord_to_email,
    normalize_phone_digits,
    sanitize_url,
)
from shared.ogp_models import Representative, Victim
from shared.ogp_types import ComplaintInput, RehabInput
from shared.ogp_validation import (
    validate_appeal_no,
    validate_complaint_input,
    validate_date_only,
    validate_event_dt,
    validate_passport_value,
    validate_phone_value,
    validate_rehab_input,
)

__all__ = [
    "BASE_EVIDENCE_FIELDS",
    "DATE_PATTERN",
    "DEFAULT_SITUATION_PLACEHOLDER",
    "DEFAULT_VIOLATION_PLACEHOLDER",
    "DT_PATTERN",
    "PHONE_DIGITS_PATTERN",
    "VIDEO_FIXED_LABEL",
    "VIDEO_PROVIDED_LABEL",
    "Representative",
    "Victim",
    "ComplaintInput",
    "RehabInput",
    "normalize_discord_to_email",
    "is_valid_http_url",
    "sanitize_url",
    "escape_bbcode_text",
    "normalize_phone_digits",
    "format_phone_for_bbcode",
    "bb_url",
    "build_evidence_line",
    "collect_evidence_items",
    "validate_event_dt",
    "validate_date_only",
    "validate_appeal_no",
    "validate_passport_value",
    "validate_phone_value",
    "validate_complaint_input",
    "validate_rehab_input",
    "build_bbcode",
    "build_rehab_bbcode",
    "build_ai_prompt",
]
