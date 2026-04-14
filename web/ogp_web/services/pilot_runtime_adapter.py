from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass
from typing import Any

from ogp_web.server_config import effective_server_pack, get_server_config
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.complaint_draft_schema import normalize_complaint_draft
from ogp_web.services.law_bundle_service import load_law_bundle_meta
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository
from ogp_web.storage.user_store import UserStore
from shared.ogp_core import build_bbcode, validate_complaint_input


PILOT_SERVER_CODE = "blackberry"
PILOT_PROCEDURE_CODE = "complaint"
PILOT_PROCEDURE_CONTENT_KEY = "complaint"
PILOT_FORM_CONTENT_KEY = "complaint_form"
PILOT_VALIDATION_CONTENT_KEY = "complaint_default"
PILOT_TEMPLATE_CONTENT_KEY = "complaint_v1"
PILOT_LAWS_CONTENT_KEY = "law_sources_manifest"


@dataclass(frozen=True)
class PilotComplaintRuntimeContext:
    server_code: str
    server_config_version: dict[str, Any]
    procedure_version: dict[str, Any]
    form_version: dict[str, Any]
    validation_rule_version: dict[str, Any]
    template_version: dict[str, Any]
    law_set_version: dict[str, Any]
    source_of_truth: str

    def to_generation_context_snapshot(self) -> dict[str, Any]:
        effective_config_snapshot = {
            "server_pack_version": str(self.server_config_version.get("version") or "0"),
            "procedure_version": str(self.procedure_version.get("version") or "1"),
            "form_version": str(self.form_version.get("version") or "1"),
            "law_set_version": str(self.law_set_version.get("hash") or "unknown"),
            "template_version": str(self.template_version.get("id") or "unknown"),
            "validation_version": str(self.validation_rule_version.get("hash") or "unknown"),
        }
        return {
            "server": {
                "id": self.server_code,
                "code": self.server_code,
            },
            "procedure_version": dict(self.procedure_version),
            "form_version": dict(self.form_version),
            "template_version": dict(self.template_version),
            "law_version_set": dict(self.law_set_version),
            "validation_rules_version": dict(self.validation_rule_version),
            "effective_config_snapshot": effective_config_snapshot,
            "content_workflow": {
                "applied_published_versions": dict(effective_config_snapshot),
                "rollback_safe": True,
            },
            "runtime_adapter": {
                "mode": "pilot_runtime_adapter_v1",
                "source_of_truth": self.source_of_truth,
                "server_config_version_id": self.server_config_version.get("id"),
                "procedure_version_id": self.procedure_version.get("id"),
                "form_version_id": self.form_version.get("id"),
                "validation_rule_version_id": self.validation_rule_version.get("id"),
                "template_version_id": self.template_version.get("id"),
                "law_set_version_id": self.law_set_version.get("id"),
            },
        }


def _short_hash(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _template_hash() -> str:
    return _short_hash(inspect.getsource(build_bbcode))


def _validation_hash() -> str:
    return _short_hash(inspect.getsource(validate_complaint_input))


def _form_hash() -> str:
    return _short_hash(inspect.getsource(normalize_complaint_draft))


def supports_pilot_runtime_adapter(*, server_code: str, document_kind: str) -> bool:
    normalized_server = str(server_code or "").strip().lower()
    normalized_kind = str(document_kind or "").strip().lower()
    return normalized_server == PILOT_SERVER_CODE and normalized_kind == PILOT_PROCEDURE_CODE


def _load_published_content_version(
    repository: ContentWorkflowRepository,
    *,
    server_code: str,
    content_type: str,
    content_key: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        item = repository.get_content_item_by_identity(
            server_scope="server",
            server_id=server_code,
            content_type=content_type,
            content_key=content_key,
        )
    except Exception:  # noqa: BLE001
        return None, None
    if not item:
        return None, None
    published_version_id = item.get("current_published_version_id")
    if not published_version_id:
        return item, None
    try:
        version = repository.get_content_version(version_id=int(published_version_id))
    except Exception:  # noqa: BLE001
        return item, None
    return item, version


def resolve_pilot_complaint_runtime_context(store: UserStore, user: AuthUser) -> PilotComplaintRuntimeContext:
    server_code = str(user.server_code or store.get_server_code(user.username) or "").strip().lower()
    if not supports_pilot_runtime_adapter(server_code=server_code, document_kind=PILOT_PROCEDURE_CODE):
        raise ValueError("pilot_runtime_adapter_not_supported")

    repository = ContentWorkflowRepository(store.backend)
    server_config = get_server_config(server_code)
    server_pack = effective_server_pack(server_code)
    bundle_meta = load_law_bundle_meta(server_code, server_config.law_qa_bundle_path)
    procedure_item, procedure_version = _load_published_content_version(
        repository,
        server_code=server_code,
        content_type="procedures",
        content_key=PILOT_PROCEDURE_CONTENT_KEY,
    )
    form_item, form_version = _load_published_content_version(
        repository,
        server_code=server_code,
        content_type="forms",
        content_key=PILOT_FORM_CONTENT_KEY,
    )
    validation_item, validation_version = _load_published_content_version(
        repository,
        server_code=server_code,
        content_type="validation_rules",
        content_key=PILOT_VALIDATION_CONTENT_KEY,
    )
    template_item, template_version = _load_published_content_version(
        repository,
        server_code=server_code,
        content_type="templates",
        content_key=PILOT_TEMPLATE_CONTENT_KEY,
    )
    law_item, law_version = _load_published_content_version(
        repository,
        server_code=server_code,
        content_type="laws",
        content_key=PILOT_LAWS_CONTENT_KEY,
    )

    server_pack_version = str(server_pack.get("version") or "1")
    bundle_hash = str(getattr(bundle_meta, "fingerprint", "") or "").strip()
    procedure_payload = dict((procedure_version or {}).get("payload_json") or {})
    form_payload = dict((form_version or {}).get("payload_json") or {})
    validation_payload = dict((validation_version or {}).get("payload_json") or {})
    template_payload = dict((template_version or {}).get("payload_json") or {})
    law_payload = dict((law_version or {}).get("payload_json") or {})

    source_of_truth = "legacy_adapter_seed"
    if all((procedure_version, form_version, validation_version, template_version)):
        source_of_truth = "content_workflow_published"
    elif any((procedure_version, form_version, validation_version, template_version, law_version)):
        source_of_truth = "hybrid_workflow_seed"

    return PilotComplaintRuntimeContext(
        server_code=server_code,
        server_config_version={
            "id": f"server_config:{server_code}:v{server_pack_version}",
            "version": server_pack_version,
            "status": "published",
        },
        procedure_version={
            "id": (procedure_version or {}).get("id") or f"procedure:{server_code}:{PILOT_PROCEDURE_CODE}:v1",
            "procedure_code": str(procedure_payload.get("procedure_code") or PILOT_PROCEDURE_CODE),
            "version": str((procedure_version or {}).get("version_number") or "1"),
            "status": "published" if procedure_version else "seeded",
            "document_kind": str(procedure_payload.get("document_kind") or PILOT_PROCEDURE_CODE),
            "content_item_id": (procedure_item or {}).get("id"),
        },
        form_version={
            "id": (form_version or {}).get("id") or f"form:{server_code}:{PILOT_PROCEDURE_CODE}:{_form_hash()}",
            "form_key": str(form_payload.get("form_code") or "complaint_draft_semantic"),
            "version": str((form_version or {}).get("version_number") or "1"),
            "hash": _form_hash(),
            "status": "published" if form_version else "seeded",
            "content_item_id": (form_item or {}).get("id"),
        },
        validation_rule_version={
            "id": (validation_version or {}).get("id") or f"validation:{server_code}:{PILOT_PROCEDURE_CODE}:{_validation_hash()}",
            "rule_set_key": str(validation_payload.get("rule_code") or PILOT_VALIDATION_CONTENT_KEY),
            "version": str((validation_version or {}).get("version_number") or "1"),
            "hash": _validation_hash(),
            "status": "published" if validation_version else "seeded",
            "content_item_id": (validation_item or {}).get("id"),
        },
        template_version={
            "id": (template_version or {}).get("id") or "complaint_bbcode_v1",
            "template_code": str(template_payload.get("template_code") or PILOT_TEMPLATE_CONTENT_KEY),
            "version": str((template_version or {}).get("version_number") or "1"),
            "hash": _template_hash(),
            "status": "published" if template_version else "seeded",
            "content_item_id": (template_item or {}).get("id"),
        },
        law_set_version={
            "id": (law_version or {}).get("id") or f"law_set:{server_code}:{bundle_hash or 'unknown'}",
            "law_set_key": str(law_payload.get("key") or PILOT_LAWS_CONTENT_KEY),
            "version": str((law_version or {}).get("version_number") or "1"),
            "hash": bundle_hash,
            "status": "published" if law_version else "seeded",
            "content_item_id": (law_item or {}).get("id"),
        },
        source_of_truth=source_of_truth,
    )


def compare_generation_context_snapshots(*, legacy_snapshot: dict[str, Any], adapter_snapshot: dict[str, Any]) -> dict[str, Any]:
    comparisons = {
        "server_id": (
            str(((legacy_snapshot.get("server") or {}).get("id") or "")),
            str(((adapter_snapshot.get("server") or {}).get("id") or "")),
        ),
        "template_version": (
            str(((legacy_snapshot.get("template_version") or {}).get("id") or "")),
            str(((adapter_snapshot.get("template_version") or {}).get("id") or "")),
        ),
        "law_set_version": (
            str(((legacy_snapshot.get("law_version_set") or {}).get("hash") or "")),
            str(((adapter_snapshot.get("law_version_set") or {}).get("hash") or "")),
        ),
        "validation_version": (
            str(legacy_snapshot.get("validation_rules_version") or ""),
            str(
                ((adapter_snapshot.get("validation_rules_version") or {}).get("hash") or "")
                if isinstance(adapter_snapshot.get("validation_rules_version"), dict)
                else adapter_snapshot.get("validation_rules_version") or ""
            ),
        ),
    }
    mismatches = {
        key: {"legacy": pair[0], "adapter": pair[1]}
        for key, pair in comparisons.items()
        if pair[0] != pair[1]
    }
    return {
        "enabled": True,
        "matched_keys": [key for key, pair in comparisons.items() if pair[0] == pair[1]],
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "source_of_truth": str(((adapter_snapshot.get("runtime_adapter") or {}).get("source_of_truth") or "legacy_adapter_seed")),
    }
