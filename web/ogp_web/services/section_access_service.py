from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status

from ogp_web.server_config import PermissionSet
from ogp_web.services.capability_registry_service import CapabilityDefinition


@dataclass(frozen=True)
class SectionAccessVerdict:
    section_code: str
    access_resource_key: str
    required_permission: str
    permission_codes: tuple[str, ...]
    status: str
    reason_code: str
    reason_detail: str

    @property
    def is_allowed(self) -> bool:
        return self.status == "allowed"

    def to_payload(self) -> dict[str, object]:
        return {
            "section_code": self.section_code,
            "access_resource_key": self.access_resource_key,
            "required_permission": self.required_permission,
            "permission_codes": list(self.permission_codes),
            "status": self.status,
            "is_allowed": self.is_allowed,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
        }


def resolve_section_access_verdict(
    *,
    capability: CapabilityDefinition,
    permissions: PermissionSet,
) -> SectionAccessVerdict:
    required_permission = str(capability.required_permission or "").strip().lower()
    permission_codes = tuple(sorted(str(code or "").strip().lower() for code in permissions.codes if str(code or "").strip()))
    if not required_permission:
        return SectionAccessVerdict(
            section_code=capability.section_code,
            access_resource_key=capability.access_resource_key,
            required_permission="",
            permission_codes=permission_codes,
            status="allowed",
            reason_code="no_explicit_permission_required",
            reason_detail="Section is available to any authenticated user on the selected server.",
        )
    if permissions.has(required_permission):
        return SectionAccessVerdict(
            section_code=capability.section_code,
            access_resource_key=capability.access_resource_key,
            required_permission=required_permission,
            permission_codes=permission_codes,
            status="allowed",
            reason_code="permission_granted",
            reason_detail=f"Required permission '{required_permission}' is granted for the selected server.",
        )
    return SectionAccessVerdict(
        section_code=capability.section_code,
        access_resource_key=capability.access_resource_key,
        required_permission=required_permission,
        permission_codes=permission_codes,
        status="blocked",
        reason_code="permission_missing",
        reason_detail=f"Required permission '{required_permission}' is missing for the selected server.",
    )


def ensure_section_access(verdict: SectionAccessVerdict) -> None:
    if verdict.is_allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=[f"Недостаточно прав: требуется permission '{verdict.required_permission}'."],
    )
