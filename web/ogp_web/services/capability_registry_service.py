from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityReadInventory:
    route_entries: tuple[str, ...]
    config_reads: tuple[str, ...]
    law_reads: tuple[str, ...]
    template_reads: tuple[str, ...]
    validation_reads: tuple[str, ...]
    access_reads: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityDefinition:
    section_code: str
    capability_code: str
    executor_code: str
    required_permission: str
    required_artifacts: tuple[str, ...]
    access_resource_key: str
    requires_law_context: bool
    current_truth: str
    target_truth: str
    bootstrap_compatibility_policy: str
    default_strict_cutover: bool
    compatibility_bridge: str
    removal_gate: str
    migration_owner: str
    read_inventory: CapabilityReadInventory


_REGISTRY: dict[str, CapabilityDefinition] = {
    "complaint": CapabilityDefinition(
        section_code="complaint",
        capability_code="complaint.compose",
        executor_code="complaint",
        required_permission="",
        required_artifacts=("form", "template", "validation", "access"),
        access_resource_key="sections.complaint",
        requires_law_context=False,
        current_truth="hybrid",
        target_truth="published_pack",
        bootstrap_compatibility_policy="staged",
        default_strict_cutover=False,
        compatibility_bridge="pilot_runtime_adapter",
        removal_gate="complaint runtime reads form/template/validation only through shared published resolvers.",
        migration_owner="complaint-runtime",
        read_inventory=CapabilityReadInventory(
            route_entries=("/complaint", "/complaint-test", "/api/complaint-draft", "/api/generate"),
            config_reads=(
                "resolve_user_server_context(...) in pages",
                "build_generation_context_snapshot(...) via shared runtime pack reader",
                "pilot_runtime_adapter(...) via shared runtime pack reader",
            ),
            law_reads=(),
            template_reads=(
                "generate_bbcode_text(...) legacy template path",
                "pilot_runtime_adapter published template snapshot",
            ),
            validation_reads=(
                "normalize_complaint_draft(...) base schema validation",
                "ValidationService bridge via complaint runtime service",
            ),
            access_reads=(
                "requires_permission()/require_user auth guard",
                "ensure_section_permission(...) shared section access verdict",
            ),
        ),
    ),
    "court_claim": CapabilityDefinition(
        section_code="court_claim",
        capability_code="court_claim.build",
        executor_code="document_builder",
        required_permission="court_claims",
        required_artifacts=("form", "template", "validation", "access"),
        access_resource_key="sections.court_claim",
        requires_law_context=False,
        current_truth="legacy",
        target_truth="published_pack",
        bootstrap_compatibility_policy="staged",
        default_strict_cutover=True,
        compatibility_bridge="document_builder_bundle_service",
        removal_gate="document builder bundle resolves form/template/validation metadata through shared published bindings.",
        migration_owner="court-claim-runtime",
        read_inventory=CapabilityReadInventory(
            route_entries=("/court-claim-test", "/api/document-builder/bundle"),
            config_reads=(
                "resolve_user_server_context(...) in pages",
                "published_artifact_resolution(...) via shared runtime pack reader",
                "document_builder_bundle_service base schema + pack overlay merge",
            ),
            law_reads=(),
            template_reads=("document_builder_bundle_service._DOCUMENT_TYPE_OVERRIDES",),
            validation_reads=("document_builder bundle validators payload",),
            access_reads=(
                "require_user auth guard",
                "ensure_section_permission(...) shared section access verdict",
            ),
        ),
    ),
    "law_qa": CapabilityDefinition(
        section_code="law_qa",
        capability_code="law_qa.ask",
        executor_code="law_qa",
        required_permission="court_claims",
        required_artifacts=("law", "ai", "validation", "access"),
        access_resource_key="sections.law_qa",
        requires_law_context=True,
        current_truth="hybrid",
        target_truth="published_pack",
        bootstrap_compatibility_policy="staged",
        default_strict_cutover=True,
        compatibility_bridge="law_context_readiness_bridge",
        removal_gate="law QA resolves selected-server law context and provenance through one shared readiness path.",
        migration_owner="law-runtime",
        read_inventory=CapabilityReadInventory(
            route_entries=("/law-qa-test", "/api/ai/law-qa-test"),
            config_reads=(
                "resolve_user_server_context(...) in pages",
                "payload.server_code or selected server in complaint law_qa route",
            ),
            law_reads=(
                "build_law_qa_test_page_data(...)",
                "run_retrieval(...)",
                "server law bundle/source resolution in ai_service path",
            ),
            template_reads=(),
            validation_reads=(
                "maybe_validate_law_qa_result(...)",
                "citations_required and validation_gate_v1 feature flags",
            ),
            access_reads=(
                "require_user auth guard",
                "ensure_section_permission(...) shared section access verdict",
            ),
        ),
    ),
}


def list_capability_definitions() -> tuple[CapabilityDefinition, ...]:
    return tuple(_REGISTRY.values())


def get_capability_definition(section_code: str) -> CapabilityDefinition:
    normalized = str(section_code or "").strip().lower()
    try:
        return _REGISTRY[normalized]
    except KeyError as exc:
        raise KeyError(f"Unknown section capability: {normalized}") from exc
