from __future__ import annotations

from copy import deepcopy
from typing import Any

from ogp_web.services.published_artifact_resolution_service import resolve_section_published_artifacts


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


def build_document_builder_bundle(*, server_id: str, document_type: str, backend: Any | None = None) -> dict[str, Any]:
    normalized_server = str(server_id or "").strip().lower()
    normalized_document_type = str(document_type or "").strip().lower()
    if not normalized_server:
        raise ValueError("server_id is required")
    if not normalized_document_type:
        raise ValueError("document_type is required")
    if normalized_document_type not in _DOCUMENT_TYPE_OVERRIDES:
        raise KeyError(f"Unknown document_type: {normalized_document_type}")

    artifacts = resolve_section_published_artifacts(
        backend=backend,
        server_code=normalized_server,
        section_code="court_claim",
    )
    schema = dict(_BASE_SCHEMA)
    if artifacts.document_builder_overlay:
        schema = _deep_merge(schema, artifacts.document_builder_overlay)
    schema = _deep_merge(schema, _DOCUMENT_TYPE_OVERRIDES[normalized_document_type])
    if artifacts.template is not None:
        template_payload = dict(artifacts.template.payload_json or {})
        template_name = str(template_payload.get("template_code") or artifacts.template.content_key or "").strip()
        if template_name:
            schema["template"] = _deep_merge(
                dict(schema.get("template") or {}),
                {
                    "name": template_name,
                    "source": artifacts.template.source,
                    "published_version_id": artifacts.template.published_version_id,
                    "published_version_number": artifacts.template.version_number,
                },
            )
    if artifacts.validation is not None:
        ruleset = dict((artifacts.validation.payload_json or {}).get("ruleset") or {})
        validators = dict(ruleset.get("validators") or {})
        if validators:
            schema["validators"] = _deep_merge(dict(schema.get("validators") or {}), validators)
        schema["status"] = _deep_merge(
            dict(schema.get("status") or {}),
            {
                "artifact_resolution": {
                    "pack_resolution_mode": artifacts.pack_resolution_mode,
                    "template": artifacts.template.to_payload() if artifacts.template is not None else None,
                    "validation": artifacts.validation.to_payload(),
                    "form": artifacts.form.to_payload() if artifacts.form is not None else None,
                }
            },
        )
    return {
        "bundle_version": BUNDLE_VERSION,
        "server": normalized_server,
        "document_type": normalized_document_type,
        **schema,
    }
