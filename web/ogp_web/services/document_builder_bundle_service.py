from __future__ import annotations

from copy import deepcopy
from typing import Any


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


_SERVER_OVERRIDES: dict[str, dict[str, Any]] = {
    "blackberry": {
        "choice_sets": {
            "claim_kind_by_court_type": {
                "supreme": [
                    {
                        "value": "supreme_admin_civil_with_representative",
                        "label": "Административно-гражданское исковое заявление с участием представителя",
                        "title": "Административно-гражданское исковое заявление с участием представителя",
                        "description": "Шаблон обращения в Верховный суд, подготовленный для ситуации, когда документ подается представителем в интересах доверителя.",
                        "ready": True,
                    },
                    {
                        "value": "supreme_admin_civil",
                        "label": "Административно-гражданское исковое заявление",
                        "title": "Административно-гражданское исковое заявление",
                        "description": "Шаблон административно-гражданского искового заявления для подачи в Верховный суд.",
                        "ready": True,
                    },
                    {
                        "value": "supreme_cassation",
                        "label": "Кассационная жалоба",
                        "title": "Кассационная жалоба",
                        "description": "Шаблон кассационной жалобы для обжалования вступившего в силу судебного акта.",
                        "ready": True,
                    },
                    {
                        "value": "supreme_interpretation",
                        "label": "Заявление о толковании и разъяснении правовых норм",
                        "title": "Толкование и разъяснение правовых норм",
                        "description": "Шаблон заявления о толковании и официальном разъяснении применимых правовых норм.",
                        "ready": True,
                    },
                    {
                        "value": "supreme_ai_warrant",
                        "label": "Заявление о получении ордера AI",
                        "title": "Получение ордера AI",
                        "description": "Шаблон заявления о выдаче ордера AI в пределах компетенции Верховного суда.",
                        "ready": True,
                    },
                ],
                "appeal": [
                    {
                        "value": "appeal_admin_civil_with_representative",
                        "label": "Административно-гражданское исковое заявление с участием представителя",
                        "title": "Административно-гражданское исковое заявление с участием представителя",
                        "description": "Базовый шаблон обращения в Апелляционный суд с участием представителя.",
                        "ready": False,
                    }
                ],
                "federal": [
                    {
                        "value": "federal_admin_civil_with_representative",
                        "label": "Административно-гражданское исковое заявление с участием представителя",
                        "title": "Административно-гражданское исковое заявление с участием представителя",
                        "description": "Базовый шаблон обращения в Федеральный суд с участием представителя.",
                        "ready": False,
                    }
                ],
            }
        },
        "validators": {
            "required_fields_by_claim_kind": {
                "supreme_interpretation": ["situation_description", "closing_request"],
                "supreme_admin_civil": ["defendant_name", "situation_description", "closing_request"],
                "__default__": ["plaintiff_name", "defendant_name", "situation_description", "closing_request"],
            }
        },
    }
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

    schema = _deep_merge(_BASE_SCHEMA, _SERVER_OVERRIDES.get(normalized_server, {}))
    schema = _deep_merge(schema, _DOCUMENT_TYPE_OVERRIDES[normalized_document_type])
    return {
        "bundle_version": BUNDLE_VERSION,
        "server": normalized_server,
        "document_type": normalized_document_type,
        **schema,
    }
