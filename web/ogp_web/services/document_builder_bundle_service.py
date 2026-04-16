from __future__ import annotations

from copy import deepcopy
from typing import Any

from ogp_web.server_config.registry import resolve_document_builder_config


BUNDLE_VERSION = "1.0.0"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
            continue
        result[key] = deepcopy(value)
    return result


_BASE_SCHEMA: dict[str, Any] = {
    "sections": [
        {"id": "params", "label": "Параметры обращения"},
        {"id": "parties", "label": "Сведения о сторонах"},
        {"id": "facts", "label": "Фактические обстоятельства"},
        {"id": "evidence", "label": "Доказательства и материалы"},
        {"id": "request", "label": "Просительная часть"},
        {"id": "result", "label": "Результат"},
    ],
    "fields": {
        "court_type": {"label": "Судебная инстанция", "type": "select"},
        "claim_kind": {"label": "Вид обращения", "type": "select"},
        "plaintiff_name": {"label": "Доверитель: ФИО", "type": "text"},
        "defendant_name": {"label": "Ответчик: ФИО", "type": "text"},
        "situation_description": {"label": "Изложение обстоятельств дела", "type": "textarea"},
        "closing_request": {"label": "Сформулируйте требования к суду", "type": "textarea"},
    },
    "choice_sets": {
        "court_types": [
            {"value": "supreme", "label": "Верховный суд"},
            {"value": "appeal", "label": "Апелляционный суд"},
            {"value": "federal", "label": "Федеральный суд"},
        ],
        "claim_kind_by_court_type": {},
    },
    "validators": {
        "required_fields_by_claim_kind": {},
    },
    "template": {
        "format": "bbcode",
        "timezone": "Europe/Moscow",
    },
    "ai_profile": {
        "enabled": False,
        "profile": "",
    },
    "features": {
        "draft_storage": True,
        "plaintiff_ocr": True,
    },
    "status": {
        "state": "active",
    },
    "allowed_actions": ["build", "copy", "clear", "save_draft", "load_draft"],
}


_DOCUMENT_TYPE_OVERRIDES: dict[str, dict[str, Any]] = {
    "court_claim": {
        "template": {
            "name": "court_claim_bbcode_v1",
        },
        "ai_profile": {
            "enabled": False,
            "profile": "manual_builder",
        },
    }
}


def build_document_builder_bundle(*, server_id: str, document_type: str) -> dict[str, Any]:
    normalized_server = str(server_id or "").strip().lower()
    normalized_document_type = str(document_type or "").strip().lower()
    if not normalized_server:
        raise ValueError("server_id is required")
    if not normalized_document_type:
        raise ValueError("document_type is required")
    if normalized_document_type not in _DOCUMENT_TYPE_OVERRIDES:
        raise KeyError(f"Unknown document_type: {normalized_document_type}")

    schema = _deep_merge(_BASE_SCHEMA, resolve_document_builder_config(normalized_server))
    schema = _deep_merge(schema, _DOCUMENT_TYPE_OVERRIDES[normalized_document_type])
    return {
        "bundle_version": BUNDLE_VERSION,
        "server": normalized_server,
        "document_type": normalized_document_type,
        **schema,
    }
