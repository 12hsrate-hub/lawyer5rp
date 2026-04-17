from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.services.auth_service import AuthUser
from ogp_web.services.complaint_draft_schema import form_version_hash
from ogp_web.services.complaint_service import _template_hash as complaint_template_hash
from ogp_web.services.complaint_service import _validation_rules_version as complaint_validation_rules_version
from ogp_web.services.generation_snapshot_schema_service import (
    build_content_workflow_snapshot,
    build_effective_generation_config_snapshot,
    build_generation_server_snapshot,
)
from ogp_web.services.law_bundle_service import load_law_bundle_meta
from ogp_web.services.published_artifact_resolution_service import (
    COMPLAINT_FORM_CONTENT_KEY,
    COMPLAINT_TEMPLATE_CONTENT_KEY,
    COMPLAINT_VALIDATION_CONTENT_KEY,
    resolve_section_artifact_specs,
    resolve_section_published_artifacts,
)
from ogp_web.services.runtime_pack_reader_service import read_runtime_pack_snapshot
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository
from ogp_web.storage.user_store import UserStore


PILOT_PROCEDURE_CODE = "complaint"
PILOT_PROCEDURE_CONTENT_KEY = "complaint"
PILOT_FORM_CONTENT_KEY = COMPLAINT_FORM_CONTENT_KEY
PILOT_VALIDATION_CONTENT_KEY = COMPLAINT_VALIDATION_CONTENT_KEY
PILOT_TEMPLATE_CONTENT_KEY = COMPLAINT_TEMPLATE_CONTENT_KEY
PILOT_LAWS_CONTENT_KEY = "law_sources_manifest"


@dataclass(frozen=True)
class PilotComplaintRuntimeContext:
    server_code: str
    feature_flags: tuple[str, ...]
    server_config_version: dict[str, Any]
    procedure_version: dict[str, Any]
    form_version: dict[str, Any]
    validation_rule_version: dict[str, Any]
    template_version: dict[str, Any]
    law_set_version: dict[str, Any]

    def to_generation_context_snapshot(self) -> dict[str, Any]:
        effective_config_snapshot = build_effective_generation_config_snapshot(
            server_pack_version=str(self.server_config_version.get("version") or "0"),
            procedure_version=str(self.procedure_version.get("version") or "1"),
            form_version=str(self.form_version.get("version") or "1"),
            law_set_hash=str(self.law_set_version.get("hash") or "unknown"),
            template_version_id=str(self.template_version.get("id") or "unknown"),
            validation_rules_version=str(self.validation_rule_version.get("hash") or "unknown"),
        )
        return {
            "server": build_generation_server_snapshot(server_code=self.server_code),
            "procedure_version": dict(self.procedure_version),
            "form_version": dict(self.form_version),
            "template_version": dict(self.template_version),
            "law_version_set": dict(self.law_set_version),
            "validation_rules_version": dict(self.validation_rule_version),
            "effective_config_snapshot": effective_config_snapshot,
            "content_workflow": build_content_workflow_snapshot(effective_config_snapshot),
            "feature_flags": list(self.feature_flags),
        }


def _resolve_content_version_specs(*, server_pack_metadata: dict[str, Any]) -> dict[str, tuple[str, str]]:
    shared_specs = resolve_section_artifact_specs(
        section_code=PILOT_PROCEDURE_CODE,
        server_pack_metadata=server_pack_metadata,
    )
    validation_spec = shared_specs.get("validation", ("validation_rules", PILOT_VALIDATION_CONTENT_KEY))
    template_spec = shared_specs.get("template", ("templates", PILOT_TEMPLATE_CONTENT_KEY))
    return {
        "procedure": ("procedures", PILOT_PROCEDURE_CONTENT_KEY),
        "form": shared_specs.get("form", ("forms", PILOT_FORM_CONTENT_KEY)),
        "validation": validation_spec,
        "template": template_spec,
        "laws": ("laws", PILOT_LAWS_CONTENT_KEY),
    }


def _has_complaint_template_binding(*, server_pack_metadata: dict[str, Any]) -> bool:
    template_bindings = dict(server_pack_metadata.get("template_bindings") or {}) if isinstance(server_pack_metadata, dict) else {}
    complaint_binding = dict(template_bindings.get(PILOT_PROCEDURE_CODE) or {})
    return bool(str(complaint_binding.get("template_key") or "").strip())


def supports_pilot_runtime_adapter(*, server_code: str, document_kind: str) -> bool:
    normalized_server = str(server_code or "").strip().lower()
    normalized_kind = str(document_kind or "").strip().lower()
    if not normalized_server or normalized_kind != PILOT_PROCEDURE_CODE:
        return False
    try:
        pack_snapshot = read_runtime_pack_snapshot(server_code=normalized_server)
    except Exception:  # noqa: BLE001
        return False
    return _has_complaint_template_binding(server_pack_metadata=pack_snapshot.metadata)


def _load_published_content_version(
    repository: ContentWorkflowRepository,
    *,
    server_code: str,
    content_type: str,
    content_key: str,
) -> dict[str, Any] | None:
    try:
        item = repository.get_content_item_by_identity(
            server_scope="server",
            server_id=server_code,
            content_type=content_type,
            content_key=content_key,
        )
    except Exception:  # noqa: BLE001
        return None
    if not item:
        return None
    published_version_id = item.get("current_published_version_id")
    if not published_version_id:
        return None
    try:
        version = repository.get_content_version(version_id=int(published_version_id))
    except Exception:  # noqa: BLE001
        return None
    return version


def _load_published_content_versions(
    repository: ContentWorkflowRepository,
    *,
    server_code: str,
    version_specs: dict[str, tuple[str, str]],
) -> dict[str, dict[str, Any] | None]:
    return {
        entry_name: _load_published_content_version(
            repository,
            server_code=server_code,
            content_type=content_type,
            content_key=content_key,
        )
        for entry_name, (content_type, content_key) in version_specs.items()
    }


def _payload_json(version: dict[str, Any] | None) -> dict[str, Any]:
    return dict((version or {}).get("payload_json") or {})


def _published_payloads(versions: dict[str, dict[str, Any] | None]) -> dict[str, dict[str, Any]]:
    return {entry_name: _payload_json(version) for entry_name, version in versions.items()}


def _sorted_feature_flags(server_pack_metadata: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(item).strip()
                for item in (server_pack_metadata.get("feature_flags") or [])
                if str(item).strip()
            }
        )
    )


def _version_number(version: dict[str, Any] | None) -> str:
    return str((version or {}).get("version_number") or "1")


def _build_runtime_version(
    version: dict[str, Any] | None,
    payload: dict[str, Any],
    *,
    fallback_id: str,
    payload_field: str,
    runtime_field: str,
    fallback_payload_value: str,
    extra_fields: dict[str, Any],
) -> dict[str, Any]:
    runtime_version = {
        "id": (version or {}).get("id") or fallback_id,
        runtime_field: str(payload.get(payload_field) or fallback_payload_value),
        "version": _version_number(version),
    }
    runtime_version.update(extra_fields)
    return runtime_version


def resolve_pilot_complaint_runtime_context(store: UserStore, user: AuthUser) -> PilotComplaintRuntimeContext:
    server_code = str(user.server_code or store.get_server_code(user.username) or "").strip().lower()
    if not supports_pilot_runtime_adapter(server_code=server_code, document_kind=PILOT_PROCEDURE_CODE):
        raise ValueError("pilot_runtime_adapter_not_supported")

    repository = ContentWorkflowRepository(store.backend)
    pack_snapshot = read_runtime_pack_snapshot(server_code=server_code)
    server_pack_metadata = dict(pack_snapshot.metadata or {})
    version_specs = _resolve_content_version_specs(server_pack_metadata=server_pack_metadata)
    bundle_meta = load_law_bundle_meta(server_code)
    published_versions = _load_published_content_versions(
        repository,
        server_code=server_code,
        version_specs=version_specs,
    )
    shared_artifacts = resolve_section_published_artifacts(
        backend=store.backend,
        server_code=server_code,
        section_code=PILOT_PROCEDURE_CODE,
    )
    payloads = _published_payloads(published_versions)
    procedure_version = published_versions["procedure"]
    form_version = published_versions["form"]
    validation_version = published_versions["validation"]
    template_version = published_versions["template"]
    law_version = published_versions["laws"]
    procedure_payload = payloads["procedure"]
    form_payload = payloads["form"]
    validation_payload = payloads["validation"]
    template_payload = payloads["template"]
    law_payload = payloads["laws"]

    server_pack_version = str(pack_snapshot.pack_version or "1")
    bundle_hash = str(getattr(bundle_meta, "fingerprint", "") or "").strip()
    form_hash = form_version_hash()
    validation_hash = complaint_validation_rules_version(PILOT_PROCEDURE_CODE)
    template_hash = complaint_template_hash(PILOT_PROCEDURE_CODE)
    validation_content_key = version_specs["validation"][1]
    template_content_key = version_specs["template"][1]
    if shared_artifacts.form is not None and shared_artifacts.form.payload_json:
        form_payload = dict(shared_artifacts.form.payload_json)
        form_version = {
            "id": shared_artifacts.form.published_version_id,
            "version_number": shared_artifacts.form.version_number,
            "payload_json": form_payload,
        }
    if shared_artifacts.validation is not None and shared_artifacts.validation.payload_json:
        validation_payload = dict(shared_artifacts.validation.payload_json)
        validation_version = {
            "id": shared_artifacts.validation.published_version_id,
            "version_number": shared_artifacts.validation.version_number,
            "payload_json": validation_payload,
        }
    if shared_artifacts.template is not None and shared_artifacts.template.payload_json:
        template_payload = dict(shared_artifacts.template.payload_json)
        template_version = {
            "id": shared_artifacts.template.published_version_id,
            "version_number": shared_artifacts.template.version_number,
            "payload_json": template_payload,
        }

    return PilotComplaintRuntimeContext(
        server_code=server_code,
        feature_flags=_sorted_feature_flags(server_pack_metadata),
        server_config_version={
            "id": f"server_config:{server_code}:v{server_pack_version}",
            "version": server_pack_version,
        },
        procedure_version=_build_runtime_version(
            procedure_version,
            procedure_payload,
            fallback_id=f"procedure:{server_code}:{PILOT_PROCEDURE_CODE}:v1",
            payload_field="procedure_code",
            runtime_field="procedure_code",
            fallback_payload_value=PILOT_PROCEDURE_CODE,
            extra_fields={"document_kind": str(procedure_payload.get("document_kind") or PILOT_PROCEDURE_CODE)},
        ),
        form_version=_build_runtime_version(
            form_version,
            form_payload,
            fallback_id=f"form:{server_code}:{PILOT_PROCEDURE_CODE}:{form_hash}",
            payload_field="form_code",
            runtime_field="form_key",
            fallback_payload_value="complaint_draft_semantic",
            extra_fields={
                "hash": form_hash,
            },
        ),
        validation_rule_version=_build_runtime_version(
            validation_version,
            validation_payload,
            fallback_id=f"validation:{server_code}:{PILOT_PROCEDURE_CODE}:{validation_hash}",
            payload_field="rule_code",
            runtime_field="rule_set_key",
            fallback_payload_value=validation_content_key,
            extra_fields={
                "hash": validation_hash,
            },
        ),
        template_version=_build_runtime_version(
            template_version,
            template_payload,
            fallback_id="complaint_bbcode_v1",
            payload_field="template_code",
            runtime_field="template_code",
            fallback_payload_value=template_content_key,
            extra_fields={"hash": template_hash},
        ),
        law_set_version=_build_runtime_version(
            law_version,
            law_payload,
            fallback_id=f"law_set:{server_code}:{bundle_hash or 'unknown'}",
            payload_field="key",
            runtime_field="law_set_key",
            fallback_payload_value=PILOT_LAWS_CONTENT_KEY,
            extra_fields={
                "hash": bundle_hash,
            },
        ),
    )
