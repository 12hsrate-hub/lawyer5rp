from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CANONICAL_CONTENT_TYPES: tuple[str, ...] = (
    "procedures",
    "bb_catalogs",
    "forms",
    "validation_rules",
    "templates",
    "features",
)

LEGACY_IMPORT_TYPE_MAP: dict[str, str] = {
    "laws": "procedures",
    "servers": "bb_catalogs",
    "rules": "validation_rules",
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: list[str]


@dataclass(frozen=True)
class SchemaContract:
    content_type: str
    schema_version: int
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()


CONTENT_SCHEMA_CONTRACTS: dict[str, SchemaContract] = {
    "procedures": SchemaContract(
        content_type="procedures",
        schema_version=1,
        required_fields=("procedure_code", "title", "steps"),
        optional_fields=("notes", "status"),
    ),
    "bb_catalogs": SchemaContract(
        content_type="bb_catalogs",
        schema_version=1,
        required_fields=("catalog_code", "title", "entries"),
        optional_fields=("notes", "status"),
    ),
    "forms": SchemaContract(
        content_type="forms",
        schema_version=1,
        required_fields=("form_code", "title", "fields"),
        optional_fields=("notes", "status"),
    ),
    "validation_rules": SchemaContract(
        content_type="validation_rules",
        schema_version=1,
        required_fields=("rule_code", "title", "ruleset"),
        optional_fields=("notes", "status"),
    ),
    "templates": SchemaContract(
        content_type="templates",
        schema_version=1,
        required_fields=("template_code", "title", "body"),
        optional_fields=("format", "status", "notes"),
    ),
    "features": SchemaContract(
        content_type="features",
        schema_version=1,
        required_fields=("feature_code", "title", "enabled"),
        optional_fields=("rollout", "owner", "notes"),
    ),
}


def normalize_content_type(content_type: str, *, allow_legacy_import_alias: bool = False) -> str:
    normalized = str(content_type or "").strip().lower()
    if allow_legacy_import_alias:
        normalized = LEGACY_IMPORT_TYPE_MAP.get(normalized, normalized)
    if normalized not in CANONICAL_CONTENT_TYPES:
        raise ValueError("unsupported_content_type")
    return normalized


def validate_payload_contract(*, content_type: str, payload_json: dict[str, Any]) -> ValidationResult:
    contract = CONTENT_SCHEMA_CONTRACTS.get(content_type)
    if contract is None:
        return ValidationResult(ok=False, errors=["unsupported_content_type"])
    if not isinstance(payload_json, dict):
        return ValidationResult(ok=False, errors=["payload_must_be_object"])

    errors: list[str] = []
    for field in contract.required_fields:
        value = payload_json.get(field)
        if value is None:
            errors.append(f"missing_required_field:{field}")
            continue
        if isinstance(value, str) and not value.strip():
            errors.append(f"empty_required_field:{field}")

    if content_type == "features" and "enabled" in payload_json and not isinstance(payload_json.get("enabled"), bool):
        errors.append("invalid_field_type:enabled:boolean_required")
    if content_type == "templates" and "body" in payload_json and not isinstance(payload_json.get("body"), str):
        errors.append("invalid_field_type:body:string_required")
    if content_type == "forms" and "fields" in payload_json and not isinstance(payload_json.get("fields"), list):
        errors.append("invalid_field_type:fields:list_required")
    if content_type == "procedures" and "steps" in payload_json and not isinstance(payload_json.get("steps"), list):
        errors.append("invalid_field_type:steps:list_required")
    if content_type == "bb_catalogs" and "entries" in payload_json and not isinstance(payload_json.get("entries"), list):
        errors.append("invalid_field_type:entries:list_required")
    if content_type == "validation_rules" and "ruleset" in payload_json and not isinstance(payload_json.get("ruleset"), dict):
        errors.append("invalid_field_type:ruleset:object_required")

    return ValidationResult(ok=not errors, errors=errors)
