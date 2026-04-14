from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NavItemConfig:
    key: str
    label: str
    href: str
    permission: str = ""


@dataclass(frozen=True)
class ComplaintBasisConfig:
    code: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class EvidenceFieldConfig:
    field_name: str
    label: str
    required: bool = False


@dataclass(frozen=True)
class ServerConfig:
    code: str
    name: str
    app_title: str
    organizations: tuple[str, ...] = ()
    complaint_bases: tuple[ComplaintBasisConfig, ...] = ()
    evidence_fields: tuple[EvidenceFieldConfig, ...] = ()
    page_nav_items: tuple[NavItemConfig, ...] = ()
    complaint_nav_items: tuple[NavItemConfig, ...] = ()
    enabled_pages: frozenset[str] = field(default_factory=frozenset)
    feature_flags: frozenset[str] = field(default_factory=frozenset)
    law_qa_sources: tuple[str, ...] = ()
    law_qa_bundle_path: str = ""
    law_qa_bundle_max_age_hours: int = 168
    shadow_law_qa_profile: str = ""
    shadow_suggest_profile: str = ""
    suggest_prompt_mode: str = "legacy"
    suggest_low_confidence_policy: str = "controlled_fallback"
    exam_sheet_url: str = ""
    complaint_forum_url: str = ""
    complaint_test_preset: dict[str, object] = field(default_factory=dict)
    complaint_supported_keys: tuple[str, ...] = ()
    complaint_legacy_key_map: dict[str, str] = field(default_factory=dict)
    complaint_value_transforms: dict[str, str] = field(default_factory=dict)

    def has_feature(self, feature_name: str) -> bool:
        return feature_name in self.feature_flags

    def supports_page(self, page_key: str) -> bool:
        return page_key in self.enabled_pages

    def complaint_basis_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.complaint_bases)
