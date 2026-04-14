from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ogp_web.server_config.types import ServerConfig


SEMANTIC_KEY_SPECS: dict[str, str] = {
    "meta.appeal_number": "string",
    "context.organization": "string",
    "context.subject_names": "string",
    "incident.datetime": "datetime",
    "meta.today_date": "string",
    "victim.full_name": "string",
    "victim.passport": "string",
    "victim.address": "string",
    "victim.phone": "string",
    "victim.discord": "string",
    "victim.passport_scan_url": "string",
    "incident.complaint_basis": "string",
    "incident.main_focus": "string",
    "incident.description": "string",
    "incident.violation_summary": "string",
    "evidence.contract_url": "string",
    "evidence.bar_request_url": "string",
    "evidence.official_answer_url": "string",
    "evidence.mail_notice_url": "string",
    "evidence.arrest_record_url": "string",
    "evidence.personnel_file_url": "string",
    "evidence.video_fix_urls": "string_list",
    "evidence.provided_video_urls": "string_list",
    "draft.result": "string",
}

LEGACY_FIELD_ALIASES: dict[str, str] = {
    "appeal_no": "meta.appeal_number",
    "org": "context.organization",
    "subject_names": "context.subject_names",
    "event_dt": "incident.datetime",
    "today_date": "meta.today_date",
    "victim_name": "victim.full_name",
    "victim_passport": "victim.passport",
    "victim_address": "victim.address",
    "victim_phone": "victim.phone",
    "victim_discord": "victim.discord",
    "victim_scan": "victim.passport_scan_url",
    "complaint_basis": "incident.complaint_basis",
    "main_focus": "incident.main_focus",
    "situation_description": "incident.description",
    "violation_short": "incident.violation_summary",
    "contract_url": "evidence.contract_url",
    "bar_request_url": "evidence.bar_request_url",
    "official_answer_url": "evidence.official_answer_url",
    "mail_notice_url": "evidence.mail_notice_url",
    "arrest_record_url": "evidence.arrest_record_url",
    "personnel_file_url": "evidence.personnel_file_url",
    "video_fix_urls": "evidence.video_fix_urls",
    "provided_video_urls": "evidence.provided_video_urls",
    "result": "draft.result",
}

DEFAULT_VALUE_TRANSFORM_RULES: dict[str, str] = {
    "incident.datetime": "normalize_datetime",
    "victim.phone": "digits_only",
    "evidence.video_fix_urls": "trim_string_list",
    "evidence.provided_video_urls": "trim_string_list",
}


@dataclass(frozen=True)
class ComplaintDraftNormalizationResult:
    draft: dict[str, Any]
    unknown_keys: tuple[str, ...] = ()
    actions: dict[str, str] | None = None


@dataclass(frozen=True)
class ComplaintDraftSwitchItem:
    semantic_key: str
    action: str
    detail: str = ""


def _normalize_datetime(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for pattern in ("%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M"):
        try:
            parsed = datetime.strptime(raw, pattern)
            return parsed.strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            continue
    return raw


def _normalize_value(value: Any, *, field_type: str, transform_rule: str) -> Any:
    if field_type == "string_list":
        if isinstance(value, (list, tuple)):
            values = [str(item or "").strip() for item in value]
            return [item for item in values if item]
        return []

    normalized = str(value or "").strip()
    if transform_rule == "digits_only":
        return "".join(ch for ch in normalized if ch.isdigit())
    if transform_rule == "normalize_datetime":
        return _normalize_datetime(normalized)
    return normalized


def get_supported_semantic_keys(config: ServerConfig) -> tuple[str, ...]:
    if config.complaint_supported_keys:
        return config.complaint_supported_keys
    return tuple(SEMANTIC_KEY_SPECS.keys())


def normalize_complaint_draft(raw_draft: dict[str, Any], *, config: ServerConfig) -> ComplaintDraftNormalizationResult:
    aliases = {**LEGACY_FIELD_ALIASES, **(config.complaint_legacy_key_map or {})}
    supported = set(get_supported_semantic_keys(config))
    transforms = {**DEFAULT_VALUE_TRANSFORM_RULES, **(config.complaint_value_transforms or {})}

    normalized: dict[str, Any] = {}
    unknown: list[str] = []
    actions: dict[str, str] = {}

    for raw_key, raw_value in (raw_draft or {}).items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        semantic_key = aliases.get(key, key)
        if semantic_key not in supported:
            unknown.append(key)
            actions[key] = "warn"
            continue

        field_type = SEMANTIC_KEY_SPECS.get(semantic_key, "string")
        transform_rule = transforms.get(semantic_key, "")
        normalized_value = _normalize_value(raw_value, field_type=field_type, transform_rule=transform_rule)
        normalized[semantic_key] = normalized_value

        if semantic_key != key or normalized_value != raw_value:
            actions[semantic_key] = "transform"
        else:
            actions[semantic_key] = "preserve"

    return ComplaintDraftNormalizationResult(
        draft=normalized,
        unknown_keys=tuple(sorted(set(unknown))),
        actions=actions,
    )


def classify_switch_actions(draft: dict[str, Any], *, target_config: ServerConfig) -> tuple[ComplaintDraftSwitchItem, ...]:
    supported = set(get_supported_semantic_keys(target_config))
    transforms = {**DEFAULT_VALUE_TRANSFORM_RULES, **(target_config.complaint_value_transforms or {})}
    result: list[ComplaintDraftSwitchItem] = []

    for key, value in (draft or {}).items():
        semantic_key = str(key or "").strip()
        if semantic_key not in supported:
            result.append(ComplaintDraftSwitchItem(semantic_key=semantic_key, action="reset", detail="key_not_supported"))
            continue
        if transforms.get(semantic_key):
            result.append(ComplaintDraftSwitchItem(semantic_key=semantic_key, action="transform", detail=transforms[semantic_key]))
            continue
        if value in (None, "", []):
            result.append(ComplaintDraftSwitchItem(semantic_key=semantic_key, action="reset", detail="empty_value"))
            continue
        result.append(ComplaintDraftSwitchItem(semantic_key=semantic_key, action="preserve", detail=""))

    if not result:
        result.append(ComplaintDraftSwitchItem(semantic_key="*", action="warn", detail="empty_draft"))
    return tuple(result)
