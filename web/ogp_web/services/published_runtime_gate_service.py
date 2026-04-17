from __future__ import annotations

from dataclasses import dataclass
import os

from fastapi import HTTPException, status

from ogp_web.services.capability_registry_service import CapabilityDefinition


@dataclass(frozen=True)
class PublishedRuntimeRequirementVerdict:
    section_code: str
    target_truth: str
    resolution_mode: str
    requires_explicit_runtime_pack: bool
    has_published_pack: bool
    is_runtime_addressable: bool
    uses_transitional_fallback: bool
    compatibility_mode: bool
    bootstrap_compatibility_policy: str
    strict_cutover_enabled: bool
    status: str
    reason_code: str
    reason_detail: str

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"

    def to_payload(self) -> dict[str, object]:
        return {
            "section_code": self.section_code,
            "target_truth": self.target_truth,
            "status": self.status,
            "is_ready": self.is_ready,
            "resolution_mode": self.resolution_mode,
            "requires_explicit_runtime_pack": self.requires_explicit_runtime_pack,
            "has_published_pack": self.has_published_pack,
            "is_runtime_addressable": self.is_runtime_addressable,
            "uses_transitional_fallback": self.uses_transitional_fallback,
            "compatibility_mode": self.compatibility_mode,
            "bootstrap_compatibility_policy": self.bootstrap_compatibility_policy,
            "strict_cutover_enabled": self.strict_cutover_enabled,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
        }


def _strict_published_runtime_sections() -> set[str]:
    raw_value = str(os.getenv("OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS", "") or "").strip()
    if not raw_value:
        return set()
    items = {
        str(item or "").strip().lower()
        for item in raw_value.replace(";", ",").split(",")
    }
    normalized = {item for item in items if item}
    if "*" in normalized:
        return {"*"}
    return normalized


def _relaxed_published_runtime_sections() -> set[str]:
    raw_value = str(os.getenv("OGP_RELAXED_PUBLISHED_RUNTIME_SECTIONS", "") or "").strip()
    if not raw_value:
        return set()
    items = {
        str(item or "").strip().lower()
        for item in raw_value.replace(";", ",").split(",")
    }
    normalized = {item for item in items if item}
    if "*" in normalized:
        return {"*"}
    return normalized


def _is_strict_cutover_enabled(*, capability: CapabilityDefinition) -> bool:
    relaxed_sections = _relaxed_published_runtime_sections()
    normalized_section = str(capability.section_code or "").strip().lower()
    if "*" in relaxed_sections or normalized_section in relaxed_sections:
        return False
    if bool(getattr(capability, "default_strict_cutover", False)):
        return True
    enabled_sections = _strict_published_runtime_sections()
    if not enabled_sections:
        return False
    return "*" in enabled_sections or normalized_section in enabled_sections


def resolve_published_runtime_requirement(
    *,
    capability: CapabilityDefinition,
    runtime_resolution_snapshot: dict[str, object],
) -> PublishedRuntimeRequirementVerdict:
    target_truth = str(capability.target_truth or "").strip().lower()
    resolution_mode = str(runtime_resolution_snapshot.get("resolution_mode") or "neutral_fallback").strip().lower()
    requires_explicit_runtime_pack = bool(runtime_resolution_snapshot.get("requires_explicit_runtime_pack"))
    has_published_pack = bool(runtime_resolution_snapshot.get("has_published_pack"))
    is_runtime_addressable = bool(runtime_resolution_snapshot.get("is_runtime_addressable"))
    uses_transitional_fallback = bool(runtime_resolution_snapshot.get("uses_transitional_fallback"))
    bootstrap_compatibility_policy = str(capability.bootstrap_compatibility_policy or "allowed").strip().lower() or "allowed"
    strict_cutover_enabled = _is_strict_cutover_enabled(capability=capability)

    if target_truth != "published_pack":
        return PublishedRuntimeRequirementVerdict(
            section_code=capability.section_code,
            target_truth=target_truth,
            resolution_mode=resolution_mode,
            requires_explicit_runtime_pack=requires_explicit_runtime_pack,
            has_published_pack=has_published_pack,
            is_runtime_addressable=is_runtime_addressable,
            uses_transitional_fallback=uses_transitional_fallback,
            compatibility_mode=False,
            bootstrap_compatibility_policy=bootstrap_compatibility_policy,
            strict_cutover_enabled=strict_cutover_enabled,
            status="ready",
            reason_code="target_truth_not_published_pack",
            reason_detail="Capability does not require published-pack runtime truth.",
        )

    if resolution_mode == "published_pack" and has_published_pack:
        return PublishedRuntimeRequirementVerdict(
            section_code=capability.section_code,
            target_truth=target_truth,
            resolution_mode=resolution_mode,
            requires_explicit_runtime_pack=requires_explicit_runtime_pack,
            has_published_pack=has_published_pack,
            is_runtime_addressable=is_runtime_addressable,
            uses_transitional_fallback=uses_transitional_fallback,
            compatibility_mode=False,
            bootstrap_compatibility_policy=bootstrap_compatibility_policy,
            strict_cutover_enabled=strict_cutover_enabled,
            status="ready",
            reason_code="published_pack_ready",
            reason_detail="Runtime path is backed by a published server pack.",
        )

    if resolution_mode == "bootstrap_pack" and bootstrap_compatibility_policy == "blocked":
        return PublishedRuntimeRequirementVerdict(
            section_code=capability.section_code,
            target_truth=target_truth,
            resolution_mode=resolution_mode,
            requires_explicit_runtime_pack=requires_explicit_runtime_pack,
            has_published_pack=has_published_pack,
            is_runtime_addressable=is_runtime_addressable,
            uses_transitional_fallback=uses_transitional_fallback,
            compatibility_mode=False,
            bootstrap_compatibility_policy=bootstrap_compatibility_policy,
            strict_cutover_enabled=True,
            status="blocked",
            reason_code="bootstrap_pack_disallowed",
            reason_detail="Capability no longer allows bootstrap-pack compatibility and requires a published server pack.",
        )

    if resolution_mode == "bootstrap_pack" and bootstrap_compatibility_policy == "staged" and strict_cutover_enabled:
        return PublishedRuntimeRequirementVerdict(
            section_code=capability.section_code,
            target_truth=target_truth,
            resolution_mode=resolution_mode,
            requires_explicit_runtime_pack=requires_explicit_runtime_pack,
            has_published_pack=has_published_pack,
            is_runtime_addressable=is_runtime_addressable,
            uses_transitional_fallback=uses_transitional_fallback,
            compatibility_mode=False,
            bootstrap_compatibility_policy=bootstrap_compatibility_policy,
            strict_cutover_enabled=strict_cutover_enabled,
            status="blocked",
            reason_code="published_pack_cutover_required",
            reason_detail="Staged cutover is enabled for this capability, so bootstrap-pack compatibility is no longer allowed.",
        )

    if resolution_mode == "bootstrap_pack" and not requires_explicit_runtime_pack and is_runtime_addressable:
        return PublishedRuntimeRequirementVerdict(
            section_code=capability.section_code,
            target_truth=target_truth,
            resolution_mode=resolution_mode,
            requires_explicit_runtime_pack=requires_explicit_runtime_pack,
            has_published_pack=has_published_pack,
            is_runtime_addressable=is_runtime_addressable,
            uses_transitional_fallback=uses_transitional_fallback,
            compatibility_mode=True,
            bootstrap_compatibility_policy=bootstrap_compatibility_policy,
            strict_cutover_enabled=strict_cutover_enabled,
            status="ready",
            reason_code="bootstrap_pack_compatibility",
            reason_detail="Runtime still uses bootstrap-pack compatibility instead of a published server pack.",
        )

    if not is_runtime_addressable:
        return PublishedRuntimeRequirementVerdict(
            section_code=capability.section_code,
            target_truth=target_truth,
            resolution_mode=resolution_mode,
            requires_explicit_runtime_pack=requires_explicit_runtime_pack,
            has_published_pack=has_published_pack,
            is_runtime_addressable=is_runtime_addressable,
            uses_transitional_fallback=uses_transitional_fallback,
            compatibility_mode=False,
            bootstrap_compatibility_policy=bootstrap_compatibility_policy,
            strict_cutover_enabled=strict_cutover_enabled,
            status="blocked",
            reason_code="server_not_runtime_addressable",
            reason_detail="Selected server is not runtime-addressable for published-pack execution.",
        )

    return PublishedRuntimeRequirementVerdict(
        section_code=capability.section_code,
        target_truth=target_truth,
        resolution_mode=resolution_mode,
        requires_explicit_runtime_pack=requires_explicit_runtime_pack,
        has_published_pack=has_published_pack,
        is_runtime_addressable=is_runtime_addressable,
        uses_transitional_fallback=uses_transitional_fallback,
        compatibility_mode=False,
        bootstrap_compatibility_policy=bootstrap_compatibility_policy,
        strict_cutover_enabled=strict_cutover_enabled,
        status="blocked",
        reason_code="explicit_runtime_pack_required",
        reason_detail="Selected server still depends on neutral fallback and needs an explicit runtime pack.",
    )


def ensure_published_runtime_requirement(
    requirement: PublishedRuntimeRequirementVerdict,
    *,
    route_path: str = "",
) -> None:
    if requirement.is_ready:
        return
    route_suffix = f" for route '{route_path}'" if str(route_path or "").strip() else ""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=[
            f"Published runtime requirement failed{route_suffix}: {requirement.reason_code}.",
            requirement.reason_detail,
        ],
    )
