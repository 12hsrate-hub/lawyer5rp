from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.services.runtime_pack_reader_service import read_runtime_pack_snapshot
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository


COMPLAINT_FORM_CONTENT_KEY = "complaint_form"
COMPLAINT_VALIDATION_CONTENT_KEY = "complaint_default"
COMPLAINT_TEMPLATE_CONTENT_KEY = "complaint_v1"
COURT_CLAIM_FORM_CONTENT_KEY = "court_claim_form"
COURT_CLAIM_VALIDATION_CONTENT_KEY = "court_claim_default"
COURT_CLAIM_TEMPLATE_CONTENT_KEY = "court_claim_bbcode_v1"


@dataclass(frozen=True)
class PublishedArtifactRef:
    artifact_type: str
    content_type: str
    content_key: str
    source: str
    published_version_id: int | None
    version_number: int | None
    payload_json: dict[str, Any]
    content_item_id: int | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = dict(self.payload_json or {})
        return {
            "artifact_type": self.artifact_type,
            "content_type": self.content_type,
            "content_key": self.content_key,
            "source": self.source,
            "published_version_id": self.published_version_id,
            "version_number": self.version_number,
            "content_item_id": self.content_item_id,
            "payload": payload,
        }


@dataclass(frozen=True)
class SectionPublishedArtifactResolution:
    section_code: str
    server_code: str
    pack_version: int | None
    pack_resolution_mode: str
    form: PublishedArtifactRef | None
    template: PublishedArtifactRef | None
    validation: PublishedArtifactRef | None
    document_builder_overlay: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "section_code": self.section_code,
            "server_code": self.server_code,
            "pack_version": self.pack_version,
            "pack_resolution_mode": self.pack_resolution_mode,
            "form": self.form.to_payload() if self.form is not None else None,
            "template": self.template.to_payload() if self.template is not None else None,
            "validation": self.validation.to_payload() if self.validation is not None else None,
            "document_builder_overlay": dict(self.document_builder_overlay or {}),
        }


def _load_published_content_ref(
    repository: ContentWorkflowRepository,
    *,
    server_code: str,
    content_type: str,
    content_key: str,
    source: str,
) -> PublishedArtifactRef:
    try:
        item = repository.get_content_item_by_identity(
            server_scope="server",
            server_id=server_code,
            content_type=content_type,
            content_key=content_key,
        )
    except Exception:  # noqa: BLE001
        item = None
    if not item:
        return PublishedArtifactRef(
            artifact_type=content_type,
            content_type=content_type,
            content_key=content_key,
            source=source,
            published_version_id=None,
            version_number=None,
            payload_json={},
            content_item_id=None,
        )
    published_version_id = item.get("current_published_version_id")
    if not published_version_id:
        return PublishedArtifactRef(
            artifact_type=content_type,
            content_type=content_type,
            content_key=content_key,
            source=source,
            published_version_id=None,
            version_number=None,
            payload_json={},
            content_item_id=int(item.get("id") or 0) or None,
        )
    try:
        version = repository.get_content_version(version_id=int(published_version_id))
    except Exception:  # noqa: BLE001
        version = None
    return PublishedArtifactRef(
        artifact_type=content_type,
        content_type=content_type,
        content_key=content_key,
        source=source,
        published_version_id=int(published_version_id),
        version_number=int((version or {}).get("version_number") or 0) or None,
        payload_json=dict((version or {}).get("payload_json") or {}),
        content_item_id=int(item.get("id") or 0) or None,
    )


def _pack_declares_mapping(*, server_pack_metadata: dict[str, Any], key: str) -> bool:
    return key in server_pack_metadata and isinstance(server_pack_metadata.get(key), dict)


def resolve_section_artifact_specs(*, section_code: str, server_pack_metadata: dict[str, Any]) -> dict[str, tuple[str, str]]:
    template_bindings = dict(server_pack_metadata.get("template_bindings") or {})
    validation_profiles = dict(server_pack_metadata.get("validation_profiles") or {})
    normalized_section = str(section_code or "").strip().lower()
    if normalized_section == "complaint":
        complaint_binding = dict(template_bindings.get("complaint") or {})
        template_key = COMPLAINT_TEMPLATE_CONTENT_KEY
        if _pack_declares_mapping(server_pack_metadata=server_pack_metadata, key="template_bindings"):
            template_key = str(complaint_binding.get("template_key") or "").strip()
        elif str(complaint_binding.get("template_key") or "").strip():
            template_key = str(complaint_binding.get("template_key") or "").strip()

        validation_key = COMPLAINT_VALIDATION_CONTENT_KEY
        if _pack_declares_mapping(server_pack_metadata=server_pack_metadata, key="validation_profiles") and not validation_profiles:
            validation_key = ""
        elif validation_key not in validation_profiles:
            for candidate in validation_profiles:
                normalized = str(candidate or "").strip()
                if normalized:
                    validation_key = normalized
                    break
        return {
            "form": ("forms", COMPLAINT_FORM_CONTENT_KEY),
            "template": ("templates", template_key),
            "validation": ("validation_rules", validation_key),
        }
    if normalized_section == "court_claim":
        court_claim_binding = dict(template_bindings.get("court_claim") or {})
        template_key = COURT_CLAIM_TEMPLATE_CONTENT_KEY
        if _pack_declares_mapping(server_pack_metadata=server_pack_metadata, key="template_bindings"):
            template_key = str(court_claim_binding.get("template_key") or "").strip()
        elif str(court_claim_binding.get("template_key") or "").strip():
            template_key = str(court_claim_binding.get("template_key") or "").strip()

        validation_key = ""
        if _pack_declares_mapping(server_pack_metadata=server_pack_metadata, key="validation_profiles") and not validation_profiles:
            validation_key = ""
        elif COURT_CLAIM_VALIDATION_CONTENT_KEY in validation_profiles:
            validation_key = COURT_CLAIM_VALIDATION_CONTENT_KEY
        elif validation_profiles:
            for candidate in validation_profiles:
                normalized = str(candidate or "").strip()
                if normalized:
                    validation_key = normalized
                    break
        return {
            "form": ("forms", COURT_CLAIM_FORM_CONTENT_KEY),
            "template": ("templates", template_key),
            "validation": ("validation_rules", validation_key),
        }
    return {}


def resolve_section_published_artifacts(
    *,
    backend: Any | None,
    server_code: str,
    section_code: str,
) -> SectionPublishedArtifactResolution:
    normalized_server = str(server_code or "").strip().lower()
    normalized_section = str(section_code or "").strip().lower()
    pack_snapshot = read_runtime_pack_snapshot(server_code=normalized_server)
    server_pack_metadata = dict(pack_snapshot.metadata or {})
    specs = resolve_section_artifact_specs(section_code=normalized_section, server_pack_metadata=server_pack_metadata)
    repository = ContentWorkflowRepository(backend) if backend is not None else None

    def _resolve(entry_name: str) -> PublishedArtifactRef | None:
        if repository is None:
            return None
        spec = specs.get(entry_name)
        if not spec:
            return None
        content_type, content_key = spec
        if not str(content_key or "").strip():
            return None
        return _load_published_content_ref(
            repository,
            server_code=normalized_server,
            content_type=content_type,
            content_key=content_key,
            source="published_content_workflow",
        )

    document_builder_overlay = {}
    if normalized_section == "court_claim":
        document_builder_overlay = dict(server_pack_metadata.get("document_builder") or {})

    return SectionPublishedArtifactResolution(
        section_code=normalized_section,
        server_code=normalized_server,
        pack_version=pack_snapshot.pack_version,
        pack_resolution_mode=pack_snapshot.resolution_mode,
        form=_resolve("form"),
        template=_resolve("template"),
        validation=_resolve("validation"),
        document_builder_overlay=document_builder_overlay,
    )
