from __future__ import annotations

from dataclasses import dataclass

from ogp_web.server_config import PermissionSet, ServerConfig
from ogp_web.services.section_access_service import (
    SectionAccessVerdict,
    ensure_section_access,
    resolve_section_access_verdict,
)
from ogp_web.services.capability_registry_service import CapabilityDefinition, get_capability_definition
from ogp_web.services.law_context_readiness_service import build_law_context_readiness_service
from ogp_web.services.published_runtime_gate_service import (
    PublishedRuntimeRequirementVerdict,
    ensure_published_runtime_requirement,
    resolve_published_runtime_requirement,
)
from ogp_web.services.published_artifact_resolution_service import SectionPublishedArtifactResolution, resolve_section_published_artifacts
from ogp_web.services.selected_server_service import resolve_selected_server_context
from ogp_web.storage.user_store import UserStore


@dataclass(frozen=True)
class SectionCapabilityContext:
    section_code: str
    capability: CapabilityDefinition
    selected_server_code: str
    server_config: ServerConfig
    permissions: PermissionSet
    access_verdict: SectionAccessVerdict
    runtime_resolution_snapshot: dict[str, object]
    runtime_requirement: PublishedRuntimeRequirementVerdict
    published_artifacts: SectionPublishedArtifactResolution | None = None
    law_context_readiness: dict[str, object] | None = None

    def to_payload(self) -> dict[str, object]:
        runtime_pack = self.runtime_resolution_snapshot.get("pack")
        pack_payload = dict(runtime_pack) if isinstance(runtime_pack, dict) else {}
        return {
            "section_code": self.section_code,
            "capability_code": self.capability.capability_code,
            "executor_code": self.capability.executor_code,
            "selected_server_code": self.selected_server_code,
            "server_name": self.server_config.name,
            "required_permission": self.capability.required_permission,
            "permission_codes": sorted(self.permissions.codes),
            "required_artifacts": list(self.capability.required_artifacts),
            "access_resource_key": self.capability.access_resource_key,
            "access_verdict": self.access_verdict.to_payload(),
            "requires_law_context": self.capability.requires_law_context,
            "current_truth": self.capability.current_truth,
            "target_truth": self.capability.target_truth,
            "compatibility_bridge": self.capability.compatibility_bridge,
            "removal_gate": self.capability.removal_gate,
            "migration_owner": self.capability.migration_owner,
            "runtime_resolution": {
                "mode": str(self.runtime_resolution_snapshot.get("resolution_mode") or ""),
                "label": str(self.runtime_resolution_snapshot.get("resolution_label") or ""),
                "is_runtime_addressable": bool(self.runtime_resolution_snapshot.get("is_runtime_addressable")),
                "has_published_pack": bool(self.runtime_resolution_snapshot.get("has_published_pack")),
                "has_bootstrap_pack": bool(self.runtime_resolution_snapshot.get("has_bootstrap_pack")),
                "uses_transitional_fallback": bool(self.runtime_resolution_snapshot.get("uses_transitional_fallback")),
                "requires_explicit_runtime_pack": bool(
                    self.runtime_resolution_snapshot.get("requires_explicit_runtime_pack")
                ),
                "pack_id": int(pack_payload.get("id") or 0) if pack_payload.get("id") is not None else None,
                "pack_version": int(pack_payload.get("version") or 0) if pack_payload.get("version") is not None else None,
                "pack_status": str(pack_payload.get("status") or ""),
            },
            "runtime_requirement": self.runtime_requirement.to_payload(),
            "artifact_resolution": self.published_artifacts.to_payload() if self.published_artifacts is not None else None,
            "law_context_readiness": dict(self.law_context_readiness or {}) if self.law_context_readiness is not None else None,
            "read_inventory": {
                "route_entries": list(self.capability.read_inventory.route_entries),
                "config_reads": list(self.capability.read_inventory.config_reads),
                "law_reads": list(self.capability.read_inventory.law_reads),
                "template_reads": list(self.capability.read_inventory.template_reads),
                "validation_reads": list(self.capability.read_inventory.validation_reads),
                "access_reads": list(self.capability.read_inventory.access_reads),
            },
        }


def resolve_section_capability_context(
    user_store: UserStore,
    username: str,
    *,
    section_code: str,
    explicit_server_code: str = "",
) -> SectionCapabilityContext:
    capability = get_capability_definition(section_code)
    selected_server = resolve_selected_server_context(
        user_store,
        username,
        explicit_server_code=explicit_server_code,
    )
    return SectionCapabilityContext(
        section_code=capability.section_code,
        capability=capability,
        selected_server_code=selected_server.selected_server_code,
        server_config=selected_server.server_config,
        permissions=selected_server.permissions,
        access_verdict=resolve_section_access_verdict(
            capability=capability,
            permissions=selected_server.permissions,
        ),
        runtime_resolution_snapshot=selected_server.runtime_resolution_snapshot,
        runtime_requirement=resolve_published_runtime_requirement(
            capability=capability,
            runtime_resolution_snapshot=selected_server.runtime_resolution_snapshot,
        ),
        published_artifacts=resolve_section_published_artifacts(
            backend=getattr(user_store, "backend", None),
            server_code=selected_server.selected_server_code,
            section_code=capability.section_code,
        ),
        law_context_readiness=(
            build_law_context_readiness_service(backend=getattr(user_store, "backend", None))
            .get_readiness(server_code=selected_server.selected_server_code)
            .to_payload()
            if capability.requires_law_context and getattr(user_store, "backend", None) is not None
            else None
        ),
    )


def ensure_section_permission(context: SectionCapabilityContext) -> SectionCapabilityContext:
    ensure_section_access(context.access_verdict)
    return context


def ensure_section_runtime_requirement(
    context: SectionCapabilityContext,
    *,
    route_path: str = "",
) -> SectionCapabilityContext:
    ensure_published_runtime_requirement(context.runtime_requirement, route_path=route_path)
    return context
